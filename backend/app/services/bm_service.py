"""Kết nối Business Manager, đồng bộ Trang và tài khoản quảng cáo (Bước 6, decisions.md mục H).

- Chỉ Chủ sở hữu kết nối / đổi mã / ngắt kết nối (quyền `bm.connect`, kiểm ở API).
- Mã BM và mã Trang lưu dạng Fernet; trả ra ngoài chỉ có 4 ký tự cuối.
- Trang workspace khác đang theo dõi: không theo dõi (quyết định #22), không nói workspace nào.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import TokenDecryptError, get_token_cipher, last4
from app.meta.graph import (
    ESSENTIAL_SCOPES,
    REQUIRED_SCOPES,
    WEBHOOK_FIELDS,
    GraphClient,
    GraphError,
    PageInfo,
    get_graph,
)
from app.models import (
    AdAccount,
    BusinessManager,
    ConnectionStatus,
    MemberRole,
    Notification,
    NotificationType,
    Page,
    PageAssignment,
    SyncRun,
    WorkspaceMember,
)
from app.schemas.bms import (
    BmOut,
    BmOverview,
    CheckItem,
    CheckResult,
    ConnectInput,
    PagePreview,
    TokenInput,
)
from app.services import audit
from app.services.errors import ServiceError

if TYPE_CHECKING:
    from app.api.deps import AuthContext

log = logging.getLogger(__name__)


def _fingerprint(token: str) -> str:
    """Nhận ra cùng một mã mà không lưu mã (HMAC với khóa của ứng dụng)."""
    key = get_settings().app_secret_key.get_secret_value().encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def _graph_error(exc: GraphError) -> ServiceError:
    if exc.kind == "invalid_token":
        return ServiceError("bm_token_invalid", 422)
    if exc.kind == "permission":
        return ServiceError("bm_missing_permissions", 422)
    if exc.kind == "rate_limit":
        return ServiceError("meta_rate_limited", 503)
    if exc.kind == "not_configured":
        return ServiceError("meta_not_configured", 503)
    return ServiceError("meta_unavailable", 503)


async def _route(db: AsyncSession, fb_page_id: str) -> uuid.UUID | None:
    result: uuid.UUID | None = await db.scalar(text("SELECT app_route_page(:p)"), {"p": fb_page_id})
    return result


# ---------------------------------------------------------------- kiểm tra mã


@dataclass
class _Fetched:
    business_id: str
    business_name: str
    verification_status: str | None
    system_user_id: str | None
    system_user_name: str | None
    scopes: list[str]
    pages: list[PageInfo]
    ad_accounts: list[Any]


async def _fetch(graph: GraphClient, token: str, business_hint: str | None) -> _Fetched:
    try:
        info = await graph.inspect_token(token)
        if not info.is_valid:
            raise ServiceError("bm_token_invalid", 422)
        business_id = business_hint or (info.business_ids[0] if info.business_ids else None)
        if business_id is None:
            raise ServiceError("bm_business_id_required", 422)
        if business_hint and info.business_ids and business_hint not in info.business_ids:
            raise ServiceError("bm_token_other_business", 422)
        business = await graph.business(token, business_id)
        su_name = await graph.me_name(token)
        pages = await graph.pages(token) if "pages_show_list" in info.scopes else []
        ads = await graph.ad_accounts(token) if "ads_read" in info.scopes else []
    except GraphError as exc:
        raise _graph_error(exc) from None
    return _Fetched(
        business_id=business.id,
        business_name=business.name,
        verification_status=business.verification_status,
        system_user_id=info.system_user_id,
        system_user_name=su_name,
        scopes=list(info.scopes),
        pages=pages,
        ad_accounts=ads,
    )


def _checks(f: _Fetched, missing: list[str], subscribed: int | None = None) -> list[CheckItem]:
    checks = [
        CheckItem(key="token_valid", level="ok", detail=f.system_user_name),
        CheckItem(
            key="pages",
            level="ok" if f.pages and "pages_messaging" not in missing else "fail",
            count=len(f.pages),
        ),
        CheckItem(
            key="webhooks",
            level="fail"
            if "pages_manage_metadata" in missing
            else ("ok" if subscribed is None or subscribed == len(f.pages) else "warn"),
            count=subscribed if subscribed is not None else len(f.pages),
            total=len(f.pages),
        ),
        CheckItem(
            key="ad_accounts",
            level="ok" if "ads_read" not in missing else "warn",
            count=len(f.ad_accounts),
        ),
        CheckItem(key="leadgen", level="ok" if "leads_retrieval" not in missing else "warn"),
    ]
    other = [
        s
        for s in missing
        if s not in ("pages_messaging", "pages_manage_metadata", "ads_read", "leads_retrieval")
    ]
    if other:
        checks.append(CheckItem(key="other_scopes", level="warn", detail=",".join(other)))
    return checks


async def check_token(db: AsyncSession, ctx: AuthContext, body: TokenInput) -> CheckResult:
    """Bước "Kiểm tra": đọc từ Meta, không lưu gì."""
    f = await _fetch(get_graph(), body.token.get_secret_value(), body.fb_business_id)
    missing = [s for s in REQUIRED_SCOPES if s not in f.scopes]
    existing = set(
        (
            await db.scalars(
                select(Page.fb_page_id).where(Page.fb_page_id.in_([p.id for p in f.pages]))
            )
        ).all()
    )
    previews = []
    for page in f.pages:
        routed = await _route(db, page.id)
        if routed is not None and routed != ctx.workspace_id:
            state = "other_workspace"
        else:
            state = "existing" if page.id in existing else "new"
        previews.append(PagePreview(fb_page_id=page.id, name=page.name, state=state))
    already = await db.scalar(
        select(BusinessManager.id).where(BusinessManager.fb_business_id == f.business_id)
    )
    return CheckResult(
        business_id=f.business_id,
        business_name=f.business_name,
        verification_status=f.verification_status,
        system_user_name=f.system_user_name,
        scopes=f.scopes,
        missing_scopes=missing,
        can_save=not any(s in missing for s in ESSENTIAL_SCOPES),
        checks=_checks(f, missing),
        pages=previews,
        ad_account_count=len(f.ad_accounts),
        already_connected=already is not None,
    )


# ---------------------------------------------------------------- đồng bộ một BM


@dataclass
class SyncOutcome:
    status: ConnectionStatus
    previous: ConnectionStatus
    new_pages: int
    subscribed: int
    failed_subscriptions: int


def _status_for(missing: list[str]) -> tuple[ConnectionStatus, str | None]:
    if any(s in missing for s in ESSENTIAL_SCOPES):
        return ConnectionStatus.MISSING_PERMISSIONS, ",".join(missing)
    if missing:
        return ConnectionStatus.MISSING_PERMISSIONS, ",".join(missing)
    return ConnectionStatus.ACTIVE, None


async def _upsert_page(
    db: AsyncSession, bm: BusinessManager, info: PageInfo, now: dt.datetime
) -> tuple[Page, bool]:
    page = await db.scalar(select(Page).where(Page.fb_page_id == info.id))
    created = page is None
    if page is None:
        page = Page(
            workspace_id=bm.workspace_id,
            business_manager_id=bm.id,
            fb_page_id=info.id,
            name=info.name,
            is_tracked=False,
        )
        db.add(page)
        await db.flush()
    page.name = info.name
    page.category = info.category
    page.business_manager_id = bm.id
    page.access_status = ConnectionStatus.ACTIVE
    if info.access_token:
        page.page_token_ciphertext = get_token_cipher().encrypt(info.access_token)
    if not page.is_tracked:
        routed = await _route(db, info.id)
        if routed is not None and routed != bm.workspace_id:
            page.untracked_reason = "other_workspace"
            return page, created
        try:
            async with db.begin_nested():
                page.is_tracked = True
                page.untracked_reason = None
                await db.flush()
        except IntegrityError:
            # Workspace khác (kể cả đang tạm khóa) đã theo dõi Trang này.
            page.is_tracked = False
            page.untracked_reason = "other_workspace"
    return page, created


async def sync_bm(
    db: AsyncSession,
    bm: BusinessManager,
    now: dt.datetime,
    graph: GraphClient | None = None,
    *,
    kind: str = "health_check",
) -> SyncOutcome:
    """Kiểm tra mã và quyền, cập nhật Trang (đăng ký webhook Trang mới) và tài khoản quảng cáo."""
    graph = graph or get_graph()
    previous = bm.status
    run = SyncRun(
        workspace_id=bm.workspace_id,
        business_manager_id=bm.id,
        kind=kind,
        started_at=now,
        status="running",
    )
    db.add(run)
    await db.flush()
    try:
        if bm.token_ciphertext is None:
            raise ServiceError("bm_token_invalid", 422)
        token = get_token_cipher().decrypt(bm.token_ciphertext)
        f = await _fetch(graph, token, bm.fb_business_id)
    except (ServiceError, TokenDecryptError) as exc:
        code = getattr(exc, "code", "token_decrypt_failed")
        if code in ("bm_token_invalid", "bm_token_other_business", "token_decrypt_failed"):
            bm.status = ConnectionStatus.DISCONNECTED
            bm.status_detail = code
        bm.last_checked_at = now
        run.status = "failed"
        run.error = code
        run.finished_at = dt.datetime.now(dt.UTC)
        run.usage = graph.last_usage
        await db.flush()
        if code not in ("bm_token_invalid", "bm_token_other_business", "token_decrypt_failed"):
            raise
        return SyncOutcome(bm.status, previous, 0, 0, 0)

    missing = [s for s in REQUIRED_SCOPES if s not in f.scopes]
    bm.status, bm.status_detail = _status_for(missing)
    bm.scopes = f.scopes
    bm.name = bm.name or f.business_name
    bm.verification_status = f.verification_status
    bm.system_user_id = f.system_user_id
    bm.last_checked_at = now
    bm.last_synced_at = now

    seen: set[str] = set()
    new_pages = subscribed = failed = 0
    for info in f.pages:
        seen.add(info.id)
        page, created = await _upsert_page(db, bm, info, now)
        new_pages += int(created and page.is_tracked)
        if page.is_tracked and info.access_token and "pages_manage_metadata" in f.scopes:
            if page.webhook_subscribed_at is None or created:
                try:
                    if await graph.subscribe_page(info.id, info.access_token):
                        page.webhook_subscribed_at = now
                        page.webhook_fields = list(WEBHOOK_FIELDS)
                        subscribed += 1
                    else:
                        failed += 1
                except GraphError:
                    failed += 1
    # Trang không còn được gán trong BM: ngừng theo dõi, giữ dữ liệu cũ.
    for page in await db.scalars(
        select(Page).where(Page.business_manager_id == bm.id, Page.is_tracked.is_(True))
    ):
        if page.fb_page_id not in seen:
            page.is_tracked = False
            page.untracked_reason = "removed_from_bm"

    for ad in f.ad_accounts:
        row = await db.scalar(select(AdAccount).where(AdAccount.fb_ad_account_id == ad.id))
        if row is None:
            row = AdAccount(
                workspace_id=bm.workspace_id,
                business_manager_id=bm.id,
                fb_ad_account_id=ad.id,
                name=ad.name,
            )
            db.add(row)
        row.name = ad.name
        row.currency = ad.currency
        row.timezone_name = ad.timezone_name
        row.account_status = ad.account_status
        row.access_status = ConnectionStatus.ACTIVE

    run.status = "ok" if bm.status == ConnectionStatus.ACTIVE and not failed else "warning"
    run.finished_at = dt.datetime.now(dt.UTC)
    run.usage = graph.last_usage
    await db.flush()
    return SyncOutcome(bm.status, previous, new_pages, subscribed, failed)


def _save_token(bm: BusinessManager, token: str) -> None:
    bm.token_ciphertext = get_token_cipher().encrypt(token)
    bm.token_last4 = last4(token)
    bm.token_fingerprint = _fingerprint(token)


async def connect(
    db: AsyncSession, ctx: AuthContext, body: ConnectInput, *, now: dt.datetime | None = None
) -> BmOut:
    """Lưu BM mới (hoặc mã mới cho BM đã có) rồi đồng bộ ngay."""
    now = now or dt.datetime.now(dt.UTC)
    graph = get_graph()
    token = body.token.get_secret_value()
    f = await _fetch(graph, token, body.fb_business_id)
    missing = [s for s in REQUIRED_SCOPES if s not in f.scopes]
    if any(s in missing for s in ESSENTIAL_SCOPES):
        raise ServiceError(
            "bm_missing_permissions", 422, missing=[s for s in missing if s in ESSENTIAL_SCOPES]
        )
    bm = await db.scalar(
        select(BusinessManager).where(BusinessManager.fb_business_id == f.business_id)
    )
    action = "bm.token_rotated" if bm else "bm.connected"
    if bm is None:
        bm = BusinessManager(
            workspace_id=ctx.workspace_id,
            fb_business_id=f.business_id,
            name=(body.name or "").strip() or f.business_name,
            connected_by_member_id=ctx.member_id,
        )
        db.add(bm)
        await db.flush()
    elif body.name and body.name.strip():
        bm.name = body.name.strip()
    _save_token(bm, token)
    await sync_bm(db, bm, now, graph, kind="connect")
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action=action,
        entity_type="business_manager",
        entity_id=bm.id,
        after={
            "fb_business_id": bm.fb_business_id,
            "name": bm.name,
            "token_last4": bm.token_last4,
            "status": bm.status.value,
        },
        ip=ctx.ip,
    )
    await db.commit()
    return (await overview(db, ctx, only=bm.id)).bms[0]


async def _get_bm(db: AsyncSession, bm_id: uuid.UUID) -> BusinessManager:
    bm = await db.scalar(
        select(BusinessManager).where(BusinessManager.id == bm_id).with_for_update()
    )
    if bm is None:
        raise ServiceError("bm_not_found", 404)
    return bm


async def rotate_token(
    db: AsyncSession, ctx: AuthContext, bm_id: uuid.UUID, body: TokenInput
) -> BmOut:
    bm = await _get_bm(db, bm_id)
    return await connect(
        db, ctx, ConnectInput(token=body.token, fb_business_id=bm.fb_business_id, name=None)
    )


async def recheck(db: AsyncSession, ctx: AuthContext, bm_id: uuid.UUID) -> BmOut:
    bm = await _get_bm(db, bm_id)
    await sync_bm(db, bm, dt.datetime.now(dt.UTC), kind="manual_check")
    await db.commit()
    return (await overview(db, ctx, only=bm.id)).bms[0]


async def disconnect(db: AsyncSession, ctx: AuthContext, bm_id: uuid.UUID) -> BmOut:
    """Xóa mã, ngừng theo dõi các Trang của BM. Dữ liệu khách và lịch sử gán Trang giữ nguyên."""
    bm = await _get_bm(db, bm_id)
    bm.token_ciphertext = None
    bm.token_last4 = None
    bm.token_fingerprint = None
    bm.status = ConnectionStatus.DISCONNECTED
    bm.status_detail = "disconnected_by_owner"
    for page in await db.scalars(select(Page).where(Page.business_manager_id == bm.id)):
        page.is_tracked = False
        page.untracked_reason = "bm_disconnected"
        page.page_token_ciphertext = None
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="bm.disconnected",
        entity_type="business_manager",
        entity_id=bm.id,
        before={"fb_business_id": bm.fb_business_id, "name": bm.name},
        ip=ctx.ip,
    )
    await db.commit()
    return (await overview(db, ctx, only=bm.id)).bms[0]


# ---------------------------------------------------------------- đọc


async def overview(
    db: AsyncSession, ctx: AuthContext, *, only: uuid.UUID | None = None
) -> BmOverview:
    from app.core.rbac import Perm

    query = select(BusinessManager).order_by(BusinessManager.created_at)
    if only is not None:
        query = query.where(BusinessManager.id == only)
    bms = list(await db.scalars(query))
    page_counts = dict(
        (
            await db.execute(
                select(Page.business_manager_id, func.count())
                .where(Page.is_tracked.is_(True))
                .group_by(Page.business_manager_id)
            )
        ).all()
    )
    ad_counts = dict(
        (
            await db.execute(
                select(AdAccount.business_manager_id, func.count()).group_by(
                    AdAccount.business_manager_id
                )
            )
        ).all()
    )
    tracked = int(
        await db.scalar(select(func.count()).select_from(Page).where(Page.is_tracked.is_(True)))
        or 0
    )
    assigned = int(
        await db.scalar(
            select(func.count(func.distinct(PageAssignment.page_id)))
            .join(Page, Page.id == PageAssignment.page_id)
            .where(PageAssignment.valid_to.is_(None), Page.is_tracked.is_(True))
        )
        or 0
    )
    out = [
        BmOut(
            id=bm.id,
            name=bm.name,
            fb_business_id=bm.fb_business_id,
            verification_status=bm.verification_status,
            system_user_name="Dashboard" if bm.system_user_id else None,
            token_last4=bm.token_last4,
            status=bm.status,
            status_detail=bm.status_detail,
            missing_scopes=[s for s in REQUIRED_SCOPES if s not in (bm.scopes or [])]
            if bm.token_ciphertext
            else [],
            page_count=int(page_counts.get(bm.id, 0)),
            ad_account_count=int(ad_counts.get(bm.id, 0)),
            last_checked_at=bm.last_checked_at,
            is_mock=bm.token_last4 is not None and get_settings().mock_mode,
        )
        for bm in bms
    ]
    return BmOverview(
        bms=out,
        tracked_pages=tracked,
        unassigned_pages=tracked - assigned,
        ad_accounts=int(sum(ad_counts.values())),
        can_connect=ctx.can(Perm.BM_CONNECT),
    )


# ---------------------------------------------------------------- job 6 giờ


async def check_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, now: dt.datetime
) -> dict[str, int]:
    """Kiểm tra mọi BM còn mã của workspace. Trạng thái xấu đi thì nhắc Chủ sở hữu trong app."""
    counts = {"checked": 0, "worse": 0, "new_pages": 0}
    for bm in list(
        await db.scalars(
            select(BusinessManager).where(BusinessManager.token_ciphertext.is_not(None))
        )
    ):
        outcome = await sync_bm(db, bm, now)
        counts["checked"] += 1
        counts["new_pages"] += outcome.new_pages
        rank = {
            ConnectionStatus.ACTIVE: 0,
            ConnectionStatus.MISSING_PERMISSIONS: 1,
            ConnectionStatus.DISCONNECTED: 2,
        }
        if rank[outcome.status] > rank[outcome.previous]:
            counts["worse"] += 1
            await _notify_owners(db, bm, outcome.status, now)
            from app.services.alert_service import notify_bm_status

            await notify_bm_status(db, bm, outcome.status, now)
    return counts


async def _notify_owners(
    db: AsyncSession, bm: BusinessManager, status: ConnectionStatus, now: dt.datetime
) -> None:
    from app.i18n import vi

    owners = (
        await db.scalars(
            select(WorkspaceMember.id).where(
                WorkspaceMember.role == MemberRole.OWNER, WorkspaceMember.status == "active"
            )
        )
    ).all()
    title = vi.BM_TITLES[status.value]
    body = vi.BM_BODIES[status.value].format(name=bm.name)
    for owner_id in owners:
        db.add(
            Notification(
                workspace_id=bm.workspace_id,
                member_id=owner_id,
                lead_id=None,
                type=NotificationType.MANUAL,
                dedupe_key=f"bm:{bm.id}:{status.value}:{now.date().isoformat()}",
                title=title,
                body=body,
                created_at=now,
            )
        )
    await db.flush()
