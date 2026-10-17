"""Đồng bộ mỗi giờ (Bước 7): cấu trúc và chi tiêu quảng cáo, bài đăng, số liệu Trang.

decisions.md mục I:
- Số liệu QC lưu theo ngày ở cả 3 cấp; mỗi lần lấy lại hôm nay và 2 ngày trước, lần đầu lấy bù
  30 ngày. "Ngày" theo múi giờ tài khoản QC.
- `spend_vnd` quy đổi qua `fx_rates` của workspace; thiếu tỉ giá thì NULL.
- Khách gắn với quảng cáo qua `fb_ad_id`; khách đến trước khi QC được đồng bộ thì gắn bù ở đây.

Không bao giờ ghi mã truy cập vào log.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenDecryptError, get_token_cipher
from app.core.ids import uuid7
from app.meta.graph import GraphClient, GraphError, InsightRow, currency_offset, get_graph
from app.models import (
    Ad,
    AdAccount,
    AdInsightDaily,
    AdSet,
    BusinessManager,
    Campaign,
    ConnectionStatus,
    FxRate,
    Page,
    PageInsightDaily,
    PagePost,
    SyncRun,
    Workspace,
)
from app.models.page_stats import EXCERPT_MAX

log = logging.getLogger(__name__)

REFRESH_DAYS = 2  # lấy lại hôm nay và 2 ngày trước
BACKFILL_DAYS = 30
POST_WINDOW_DAYS = 30
# Mục tiêu tin nhắn/khách tiềm năng: không có kết quả thì là 0, không phải "–".
RESULT_OBJECTIVES = frozenset({"MESSAGES", "LEAD_GENERATION", "OUTCOME_LEADS", "CONVERSATIONS"})
LEVELS = ("campaign", "adset", "ad")


# ---------------------------------------------------------------- tỉ giá


class FxTable:
    """Tỉ giá của workspace: ngày D dùng dòng có `effective_from` gần nhất ≤ D."""

    def __init__(self, rows: list[tuple[str, dt.date, Decimal]]) -> None:
        self._by_currency: dict[str, tuple[list[dt.date], list[Decimal]]] = {}
        for currency, start, rate in sorted(rows, key=lambda r: (r[0], r[1])):
            dates, rates = self._by_currency.setdefault(currency, ([], []))
            dates.append(start)
            rates.append(rate)

    @classmethod
    async def load(cls, db: AsyncSession) -> FxTable:
        rows = await db.execute(select(FxRate.currency, FxRate.effective_from, FxRate.vnd_per_unit))
        return cls([(c, d, r) for c, d, r in rows.all()])

    def rate(self, currency: str, day: dt.date) -> Decimal | None:
        if currency == "VND":
            return Decimal(1)
        found = self._by_currency.get(currency)
        if not found:
            return None
        dates, rates = found
        i = bisect_right(dates, day)
        return rates[i - 1] if i else None

    def to_vnd(self, spend_minor: int, currency: str, day: dt.date) -> int | None:
        rate = self.rate(currency, day)
        if rate is None:
            return None
        major = Decimal(spend_minor) / currency_offset(currency)
        return int((major * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def apply_fx(db: AsyncSession, currency: str) -> int:
    """Tính lại `spend_vnd` của mọi dòng dùng `currency` (sau khi Chủ sở hữu sửa tỉ giá)."""
    fx = await FxTable.load(db)
    rows = (
        await db.execute(
            select(AdInsightDaily.id, AdInsightDaily.spend_minor, AdInsightDaily.date).where(
                AdInsightDaily.currency == currency
            )
        )
    ).all()
    for row_id, spend_minor, day in rows:
        await db.execute(
            update(AdInsightDaily)
            .where(AdInsightDaily.id == row_id)
            .values(spend_vnd=fx.to_vnd(spend_minor, currency, day))
        )
    return len(rows)


# ---------------------------------------------------------------- quảng cáo


def results_of(objective: str | None, messaging: int, leads: int) -> int | None:
    total = messaging + leads
    if total > 0 or (objective or "").upper() in RESULT_OBJECTIVES:
        return total
    return None


@dataclass
class SyncCounts:
    ad_accounts: int = 0
    insight_rows: int = 0
    pages: int = 0
    posts: int = 0
    failed: int = 0
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)


def _upsert_stmt(model: Any, values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """INSERT … ON CONFLICT (keys) DO UPDATE các cột còn lại."""
    stmt = pg_insert(model).values(**values)
    return stmt.on_conflict_do_update(
        index_elements=list(keys),
        set_={k: stmt.excluded[k] for k in values if k not in keys and k != "id"}
        | {"updated_at": func.now()},
    )


async def _upsert(db: AsyncSession, model: Any, values: dict[str, Any], key: str) -> uuid.UUID:
    """Thêm hoặc cập nhật theo `(workspace_id, key)`, trả `id`."""
    stmt = _upsert_stmt(model, {"id": uuid7(), **values}, ("workspace_id", key))
    result: uuid.UUID = (await db.execute(stmt.returning(model.id))).scalar_one()
    return result


def _account_today(account: AdAccount, workspace_tz: str) -> dt.date:
    return dt.datetime.now(ZoneInfo(account.timezone_name or workspace_tz)).date()


async def sync_ad_account(
    db: AsyncSession,
    account: AdAccount,
    token: str,
    graph: GraphClient,
    fx: FxTable,
    workspace_tz: str,
    counts: SyncCounts,
) -> None:
    ws = account.workspace_id
    campaigns = await graph.campaigns(token, account.fb_ad_account_id)
    ad_sets = await graph.ad_sets(token, account.fb_ad_account_id)
    ads = await graph.ads(token, account.fb_ad_account_id)

    campaign_ids: dict[str, uuid.UUID] = {}
    objectives: dict[str, str | None] = {}
    for c in campaigns:
        campaign_ids[c.id] = await _upsert(
            db,
            Campaign,
            {
                "workspace_id": ws,
                "ad_account_id": account.id,
                "fb_campaign_id": c.id,
                "name": c.name[:400],
                "objective": c.objective,
                "status": c.status,
                "daily_budget_minor": c.daily_budget_minor,
            },
            "fb_campaign_id",
        )
        objectives[c.id] = c.objective
    adset_ids: dict[str, uuid.UUID] = {}
    for s in ad_sets:
        if s.campaign_id not in campaign_ids:
            continue
        adset_ids[s.id] = await _upsert(
            db,
            AdSet,
            {
                "workspace_id": ws,
                "campaign_id": campaign_ids[s.campaign_id],
                "fb_ad_set_id": s.id,
                "name": s.name[:400],
                "status": s.status,
                "daily_budget_minor": s.daily_budget_minor,
            },
            "fb_ad_set_id",
        )
    page_ids = {
        fb_id: page_id
        for fb_id, page_id in (await db.execute(select(Page.fb_page_id, Page.id))).all()
    }
    ad_ids: dict[str, uuid.UUID] = {}
    for a in ads:
        if a.adset_id not in adset_ids or a.campaign_id not in campaign_ids:
            continue
        ad_ids[a.id] = await _upsert(
            db,
            Ad,
            {
                "workspace_id": ws,
                "ad_set_id": adset_ids[a.adset_id],
                "campaign_id": campaign_ids[a.campaign_id],
                "page_id": page_ids.get(a.page_id) if a.page_id else None,
                "fb_ad_id": a.id,
                "name": a.name[:400],
                "status": a.status,
            },
            "fb_ad_id",
        )

    today = _account_today(account, workspace_tz)
    has_rows = await db.scalar(
        select(AdInsightDaily.id).where(AdInsightDaily.ad_account_id == account.id).limit(1)
    )
    since = today - dt.timedelta(days=REFRESH_DAYS if has_rows else BACKFILL_DAYS - 1)
    currency = (account.currency or "VND").upper()
    offset = currency_offset(currency)
    object_maps = {"campaign": campaign_ids, "adset": adset_ids, "ad": ad_ids}
    for level in LEVELS:
        rows: list[InsightRow] = await graph.insights(
            token, account.fb_ad_account_id, level, since, today
        )
        for r in rows:
            object_id = object_maps[level].get(r.object_id)
            campaign_id = campaign_ids.get(r.campaign_id)
            if object_id is None or campaign_id is None:
                counts.skipped_rows += 1  # đối tượng đã xóa / lưu trữ, Meta không còn liệt kê
                continue
            spend_minor = int((r.spend * offset).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            values = {
                "workspace_id": ws,
                "ad_account_id": account.id,
                "campaign_id": campaign_id,
                "level": level,
                "object_id": object_id,
                "date": r.date,
                "currency": currency,
                "spend_minor": spend_minor,
                "spend_vnd": fx.to_vnd(spend_minor, currency, r.date),
                "impressions": r.impressions,
                "reach": r.reach,
                "clicks": r.clicks,
                "messaging_starts": r.messaging_starts,
                "leads": r.leads,
                "results": results_of(objectives.get(r.campaign_id), r.messaging_starts, r.leads),
            }
            await db.execute(
                _upsert_stmt(AdInsightDaily, values, ("workspace_id", "level", "object_id", "date"))
            )
            counts.insight_rows += 1
    account.access_status = ConnectionStatus.ACTIVE
    counts.ad_accounts += 1


async def link_unlinked_leads(db: AsyncSession) -> int:
    """Gắn bù khách đến trước khi quảng cáo của họ được đồng bộ."""
    result = await db.execute(
        text(
            "UPDATE leads l SET ad_id = a.id, campaign_id = a.campaign_id"
            " FROM ads a"
            " WHERE a.workspace_id = l.workspace_id AND a.fb_ad_id = l.fb_ad_id"
            "   AND l.fb_ad_id IS NOT NULL AND l.ad_id IS NULL"
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


# ---------------------------------------------------------------- Trang


async def sync_page(
    db: AsyncSession,
    page: Page,
    page_token: str,
    graph: GraphClient,
    workspace_tz: str,
    now: dt.datetime,
    counts: SyncCounts,
) -> None:
    ws = page.workspace_id
    posts = await graph.page_posts(
        page.fb_page_id, page_token, now - dt.timedelta(days=POST_WINDOW_DAYS)
    )
    for p in posts:
        await _upsert(
            db,
            PagePost,
            {
                "workspace_id": ws,
                "page_id": page.id,
                "fb_post_id": p.id,
                "created_time": p.created_time,
                "type": p.type,
                "excerpt": (p.message or "")[:EXCERPT_MAX] or None,
                "permalink": (p.permalink or "")[:500] or None,
                "reactions": p.reactions,
                "comments": p.comments,
                "shares": p.shares,
                "views": p.views,
            },
            "fb_post_id",
        )
    counts.posts += len(posts)

    today = now.astimezone(ZoneInfo(workspace_tz)).date()
    has_rows = page.content_synced_at is not None
    since = today - dt.timedelta(days=REFRESH_DAYS if has_rows else BACKFILL_DAYS - 1)
    for day in await graph.page_insights(page.fb_page_id, page_token, since, today):
        values = {
            "workspace_id": ws,
            "page_id": page.id,
            "date": day.date,
            "followers": day.followers,
            "new_follows": day.new_follows,
            "views": day.views,
            "reach": day.reach,
            "engagements": day.engagements,
            "video_views": day.video_views,
        }
        await db.execute(
            _upsert_stmt(PageInsightDaily, values, ("workspace_id", "page_id", "date"))
        )
    page.content_synced_at = now
    counts.pages += 1


# ---------------------------------------------------------------- một BM, cả workspace


async def sync_bm_content(
    db: AsyncSession,
    bm: BusinessManager,
    now: dt.datetime,
    graph: GraphClient | None = None,
    *,
    workspace_tz: str = "Asia/Ho_Chi_Minh",
    fx: FxTable | None = None,
    kind: str = "hourly_sync",
) -> SyncCounts:
    graph = graph or get_graph()
    fx = fx or await FxTable.load(db)
    counts = SyncCounts()
    run = SyncRun(
        workspace_id=bm.workspace_id,
        business_manager_id=bm.id,
        kind=kind,
        started_at=now,
        status="running",
    )
    db.add(run)
    await db.flush()
    cipher = get_token_cipher()
    try:
        if bm.token_ciphertext is None:
            raise TokenDecryptError
        token = cipher.decrypt(bm.token_ciphertext)
    except TokenDecryptError:
        run.status, run.error = "failed", "token_unavailable"
        run.finished_at = dt.datetime.now(dt.UTC)
        await db.flush()
        counts.failed += 1
        return counts

    accounts = list(
        await db.scalars(
            select(AdAccount).where(
                AdAccount.business_manager_id == bm.id,
                AdAccount.access_status != ConnectionStatus.DISCONNECTED,
            )
        )
    )
    for account in accounts:
        try:
            async with db.begin_nested():
                await sync_ad_account(db, account, token, graph, fx, workspace_tz, counts)
        except GraphError as exc:
            counts.failed += 1
            counts.errors.append(f"ad_account:{exc.kind}")
            if exc.kind == "permission":
                account.access_status = ConnectionStatus.MISSING_PERMISSIONS
            if exc.kind == "invalid_token":
                break

    pages = list(
        await db.scalars(
            select(Page).where(
                Page.business_manager_id == bm.id,
                Page.is_tracked.is_(True),
                Page.page_token_ciphertext.is_not(None),
            )
        )
    )
    for page in pages:
        try:
            page_token = cipher.decrypt(page.page_token_ciphertext or b"")
        except TokenDecryptError:
            counts.failed += 1
            continue
        try:
            async with db.begin_nested():
                await sync_page(db, page, page_token, graph, workspace_tz, now, counts)
        except GraphError as exc:
            counts.failed += 1
            counts.errors.append(f"page:{exc.kind}")

    run.status = (
        "ok"
        if not counts.failed
        else ("warning" if counts.pages or counts.ad_accounts else "failed")
    )
    run.error = ",".join(sorted(set(counts.errors)))[:500] or None
    run.finished_at = dt.datetime.now(dt.UTC)
    run.usage = graph.last_usage
    await db.flush()
    return counts


async def sync_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, now: dt.datetime, graph: GraphClient | None = None
) -> dict[str, int]:
    """Đồng bộ mọi BM còn kết nối của workspace, rồi gắn bù khách với quảng cáo."""
    workspace_tz = await db.scalar(select(Workspace.timezone).where(Workspace.id == workspace_id))
    fx = await FxTable.load(db)
    totals = {"bms": 0, "ad_accounts": 0, "insight_rows": 0, "pages": 0, "posts": 0, "failed": 0}
    bms = list(
        await db.scalars(
            select(BusinessManager).where(
                BusinessManager.token_ciphertext.is_not(None),
                BusinessManager.status != ConnectionStatus.DISCONNECTED,
            )
        )
    )
    for bm in bms:
        c = await sync_bm_content(
            db, bm, now, graph, workspace_tz=workspace_tz or "Asia/Ho_Chi_Minh", fx=fx
        )
        totals["bms"] += 1
        totals["ad_accounts"] += c.ad_accounts
        totals["insight_rows"] += c.insight_rows
        totals["pages"] += c.pages
        totals["posts"] += c.posts
        totals["failed"] += c.failed
    totals["leads_linked"] = await link_unlinked_leads(db)
    return totals
