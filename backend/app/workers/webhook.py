"""Job arq xử lý webhook Meta.

Mỗi sự kiện trong payload xử lý trong một transaction riêng, bằng tài khoản ứng dụng (bị RLS):

1. `app_route_page(fb_page_id)` → workspace. Trang không ai theo dõi thì bỏ.
2. Đặt `app.workspace_id`, ghi `webhook_events` (chặn lặp theo `dedupe_key`).
3. Gọi nghiệp vụ ở `app.services.inbound`.

Sự kiện lỗi được ghi `failed` (chỉ ghi tên lỗi) và cả job được thử lại có backoff; các sự kiện
đã xử lý xong bị bỏ qua ở lần thử sau nhờ `dedupe_key`.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections import Counter
from typing import Any

from arq import Retry
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.meta.events import (
    Event,
    IgnoredEvent,
    LeadgenEvent,
    MessageEvent,
    ReferralEvent,
    WebhookPayload,
    parse_payload,
)
from app.models import Page, WebhookEvent, WebhookEventStatus
from app.services import inbound
from app.services.inbound import Outcome

log = logging.getLogger(__name__)

MAX_TRIES = 6
UNROUTED = "unrouted"
IGNORED = "ignored"
FAILED = "failed"


def retry_delay_seconds(job_try: int) -> int:
    """10s, 20s, 40s… tối đa 10 phút."""
    return int(min(10 * 2 ** max(job_try - 1, 0), 600))


def _kind(ev: MessageEvent | ReferralEvent | LeadgenEvent) -> str:
    if isinstance(ev, MessageEvent):
        return "message" if ev.kind == "in" else "echo"
    return "referral" if isinstance(ev, ReferralEvent) else "leadgen"


async def _claim(
    db: AsyncSession, workspace_id: uuid.UUID, ev: MessageEvent | ReferralEvent | LeadgenEvent
) -> WebhookEvent | None:
    """Ghi nhận sự kiện. None nếu đã xử lý xong ở lần trước (Meta gửi lặp)."""
    event_id = await db.scalar(
        pg_insert(WebhookEvent)
        .values(
            workspace_id=workspace_id,
            object="page",
            fb_page_id=ev.fb_page_id,
            kind=_kind(ev),
            dedupe_key=ev.dedupe_key,
            payload=ev.raw,
            status=WebhookEventStatus.PROCESSED,
            processed_at=func.now(),
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "dedupe_key"])
        .returning(WebhookEvent.id)
    )
    if event_id is not None:
        return await db.get(WebhookEvent, event_id)
    existing = await db.scalar(
        select(WebhookEvent)
        .where(WebhookEvent.workspace_id == workspace_id, WebhookEvent.dedupe_key == ev.dedupe_key)
        .with_for_update()
    )
    if existing is None or existing.status != WebhookEventStatus.FAILED:
        return None
    existing.attempts += 1
    existing.status = WebhookEventStatus.PROCESSED
    existing.error = None
    existing.processed_at = dt.datetime.now(dt.UTC)
    return existing


async def _record_failure(
    workspace_id: uuid.UUID, ev: MessageEvent | ReferralEvent | LeadgenEvent, exc: BaseException
) -> None:
    async with app_sessionmaker()() as db:
        await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
        stmt = pg_insert(WebhookEvent).values(
            workspace_id=workspace_id,
            object="page",
            fb_page_id=ev.fb_page_id,
            kind=_kind(ev),
            dedupe_key=ev.dedupe_key,
            payload=ev.raw,
            status=WebhookEventStatus.FAILED,
            # Chỉ tên lỗi: thông điệp lỗi có thể chứa nội dung tin nhắn.
            error=type(exc).__name__,
        )
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["workspace_id", "dedupe_key"],
                set_={
                    "status": WebhookEventStatus.FAILED.value,
                    "attempts": WebhookEvent.attempts + 1,
                    "error": stmt.excluded.error,
                    "processed_at": None,
                },
            )
        )
        await db.commit()


async def _route(db: AsyncSession, fb_page_id: str) -> uuid.UUID | None:
    result: uuid.UUID | None = await db.scalar(text("SELECT app_route_page(:p)"), {"p": fb_page_id})
    return result


async def process_event(ev: Event) -> str:
    if isinstance(ev, IgnoredEvent):
        return IGNORED
    async with app_sessionmaker()() as db:
        workspace_id = await _route(db, ev.fb_page_id)
        if workspace_id is None:
            log.info(
                "bỏ sự kiện của Trang không theo dõi",
                extra={"ctx": {"fb_page_id": ev.fb_page_id, "kind": _kind(ev)}},
            )
            return UNROUTED
        await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
        try:
            row = await _claim(db, workspace_id, ev)
            if row is None:
                await db.rollback()
                return Outcome.DUPLICATE
            page = await db.scalar(
                select(Page).where(Page.fb_page_id == ev.fb_page_id, Page.is_tracked.is_(True))
            )
            if page is None:  # Trang vừa bị bỏ theo dõi giữa hai câu lệnh
                await db.rollback()
                return UNROUTED
            rules = await inbound.load_rules(db, workspace_id)
            if isinstance(ev, MessageEvent):
                outcome = await inbound.handle_message(db, page, rules, ev)
            elif isinstance(ev, ReferralEvent):
                outcome = await inbound.handle_referral(db, page, rules, ev)
            else:
                outcome = await inbound.handle_leadgen(db, page, rules, ev)
            if outcome == Outcome.REFERRAL_PENDING:
                row.status = WebhookEventStatus.IGNORED
            await db.commit()
            return outcome
        except Exception as exc:
            await db.rollback()
            log.exception(
                "lỗi xử lý sự kiện webhook",
                extra={"ctx": {"fb_page_id": ev.fb_page_id, "kind": _kind(ev)}},
            )
            await _record_failure(workspace_id, ev, exc)
            raise


async def process_webhook(
    ctx: dict[str, Any], payload: WebhookPayload | dict[str, Any]
) -> dict[str, int]:
    data = payload.data if isinstance(payload, WebhookPayload) else payload
    counts: Counter[str] = Counter()
    for ev in parse_payload(data):
        try:
            counts[await process_event(ev)] += 1
        except Exception:
            counts[FAILED] += 1
    if counts[FAILED]:
        job_try = int(ctx.get("job_try", 1))
        raise Retry(defer=retry_delay_seconds(job_try))
    return dict(counts)
