"""Tổng quan, Fanpage, Chi tiết Trang (Bước 7, decisions.md mục I).

Phạm vi theo `report.view`: Trưởng nhóm chỉ thấy nhóm mình (khách theo người phụ trách, Trang theo
người đang phụ trách). Số tiền quảng cáo chỉ trả về khi có `ads.cost.view`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.config import get_settings
from app.core.rbac import Perm, Scope
from app.models import (
    BusinessManager,
    Campaign,
    ConnectionStatus,
    Lead,
    LeadStatus,
    Page,
    PageAssignment,
    PageInsightDaily,
    PagePost,
    PeriodType,
    Team,
    Tier,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)
from app.schemas.leads import NamedRef
from app.schemas.reports import (
    BoardRow,
    Boards,
    CampaignSummary,
    DailyPoint,
    DayValue,
    Funnel,
    Metric,
    OverviewAlerts,
    OverviewKpis,
    OverviewOut,
    OwnerShare,
    PageDetailOut,
    PageKpis,
    PageReportList,
    PageReportRow,
    PageSort,
    PageStatus,
    PageTab,
    PageTabs,
    PostRow,
    RangeOut,
)
from app.services import ads_service, inbound, metrics, score_service
from app.services.ads_service import money_ratio, owner_condition, ratio
from app.services.alert_rules import effective_rules
from app.services.errors import ServiceError
from app.services.lead_service import member_ids_for
from app.services.member_service import visible_team_ids
from app.services.periods import Period
from app.services.report_range import DateRange, RangeKey, resolve_range
from app.services.scoring import LeadFacts, MemberScore

LOW_POSTS_THRESHOLD = 3  # "Ít đăng bài": dưới 3 bài trong 7 ngày (mục L)
DECLINE_RATIO = Decimal("0.7")  # "Giảm tương tác": lượt xem 7 ngày giảm ≥ 30%
HEATMAP_MIN_POSTS = 10
HEAT_SLOTS = ((6, 9), (9, 12), (12, 15), (15, 18), (18, 21), (21, 24))
PAGE_SIZE = 20
BOARD_SIZE = 5


def _metric(value: Any, previous: Any) -> Metric:
    return Metric(
        value=Decimal(value) if value is not None else None,
        previous=Decimal(previous) if previous is not None else None,
    )


async def workspace_tz(db: AsyncSession, workspace_id: uuid.UUID) -> ZoneInfo:
    name = await db.scalar(select(Workspace.timezone).where(Workspace.id == workspace_id))
    return ZoneInfo(name or "Asia/Ho_Chi_Minh")


async def _scope_ids(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID | None
) -> set[uuid.UUID] | None:
    """Người phụ trách được xem: theo `report.view`, giao với nhóm đang lọc."""
    ids = await member_ids_for(db, ctx, ctx.scope(Perm.REPORT_VIEW))
    if team_id is None:
        return ids
    if ctx.scope(Perm.REPORT_VIEW) == Scope.TEAM and team_id not in await visible_team_ids(db, ctx):
        raise ServiceError("forbidden", 403)
    members = set(
        await db.scalars(select(WorkspaceMember.id).where(WorkspaceMember.team_id == team_id))
    )
    return members if ids is None else ids & members


async def _teams(db: AsyncSession, ctx: AuthContext) -> list[NamedRef]:
    query = select(Team.id, Team.name).order_by(Team.name)
    if ctx.scope(Perm.REPORT_VIEW) != Scope.ALL:
        query = query.where(Team.id.in_(await visible_team_ids(db, ctx)))
    return [NamedRef(id=i, name=n) for i, n in (await db.execute(query)).all()]


def _local_date(column: Any, tz: ZoneInfo) -> Any:
    return func.date(func.timezone(tz.key, column))


# ---------------------------------------------------------------- Tổng quan


async def _ad_spend(db: AsyncSession, r: DateRange) -> int | None:
    stats = await ads_service.level_stats(db, "campaign", r)
    return ads_service.total(stats).spend_vnd if stats else 0


def _score_period(r: DateRange) -> Period:
    """Kỳ điểm của khối dẫn đầu: trùng kỳ màn hình, riêng "Hôm nay" dùng 7 ngày (ghi rõ)."""
    if r.key == "today":
        return Period(PeriodType.ROLLING_7, r.first_day - dt.timedelta(days=6), r.last_day)
    kind = {"30d": PeriodType.ROLLING_30, "90d": PeriodType.ROLLING_30, "month": PeriodType.MONTH}
    return Period(kind.get(r.key, PeriodType.ROLLING_7), r.first_day, r.last_day)


async def _alerts(
    db: AsyncSession,
    ctx: AuthContext,
    owner_ids: set[uuid.UUID] | None,
    now: dt.datetime,
    settings: WorkspaceSettings,
    week7: score_service.LivePeriod,
    unassigned_leads: int | None,
) -> OverviewAlerts:
    # Quá hạn 48 giờ ở thẻ cảnh báo: mọi thời điểm (decisions.md mục J).
    overdue = (
        await db.execute(
            select(
                func.count(),
                func.count(func.distinct(Lead.page_id)),
                func.min(Lead.first_inbound_at),
            ).where(
                Lead.result_at.is_(None),
                Lead.result_due_at < now,
                Lead.merged_into_lead_id.is_(None),
                owner_condition(owner_ids),
            )
        )
    ).one()
    slow_limit = settings.slow_reply_minutes * 60
    by_owner = metrics.group(metrics.in_scope(week7.facts, owner_ids), lambda f: f.owner_id)
    slow = 0
    for owner, items in by_owner.items():
        if owner is None:
            continue
        median = metrics.summarize(items, now, week7.params).median_response_seconds
        if median is not None and median > slow_limit:
            slow += 1

    unassigned = bm_down = None
    bm_name = None
    bm_pages = 0
    if ctx.can(Perm.BM_VIEW):
        open_assignment = select(PageAssignment.id).where(
            PageAssignment.page_id == Page.id, PageAssignment.valid_to.is_(None)
        )
        unassigned = int(
            await db.scalar(
                select(func.count()).where(Page.is_tracked.is_(True), ~open_assignment.exists())
            )
            or 0
        )
        down = list(
            await db.scalars(
                select(BusinessManager).where(
                    BusinessManager.status == ConnectionStatus.DISCONNECTED
                )
            )
        )
        bm_down = len(down)
        if down:
            bm_name = down[0].name
            bm_pages = int(
                await db.scalar(
                    select(func.count()).where(
                        Page.business_manager_id.in_([b.id for b in down]),
                        Page.is_tracked.is_(True),
                    )
                )
                or 0
            )
    expensive = None
    if ctx.can(Perm.ADS_COST_VIEW):
        rules = await effective_rules(db)
        limit = int(rules["cost_per_won"].params["max_vnd"])
        r7 = resolve_range("7d", await workspace_tz(db, ctx.workspace_id), now)
        stats = await ads_service.level_stats(db, "campaign", r7)
        expensive = sum(
            1
            for s in stats.values()
            if (s.cost_per_won is not None and s.cost_per_won > limit)
            or (s.won == 0 and (s.spend_vnd or 0) > limit)
        )
    count, pages, oldest = overdue
    return OverviewAlerts(
        overdue=int(count),
        overdue_pages=int(pages),
        overdue_oldest_hours=int((now - oldest).total_seconds() // 3600) if oldest else None,
        slow_staff=slow,
        slow_reply_minutes=settings.slow_reply_minutes,
        unassigned_pages=unassigned,
        bm_disconnected=bm_down,
        bm_disconnected_name=bm_name,
        bm_disconnected_pages=bm_pages,
        expensive_campaigns=expensive,
        unassigned_leads=unassigned_leads,
    )


def _daily(r: DateRange, facts: list[LeadFacts]) -> list[DailyPoint]:
    """Theo ngày khách nhắn tin đầu tiên: tổng các cột = Khách mới / Chốt của kỳ."""
    new: dict[dt.date, int] = defaultdict(int)
    won: dict[dt.date, int] = defaultdict(int)
    for f in facts:
        if f.first_inbound_at is None:
            continue
        day = f.first_inbound_at.astimezone(r.tz).date()
        new[day] += 1
        if f.status == LeadStatus.WON:
            won[day] += 1
    return [DailyPoint(day=d, new=new[d], won=won[d]) for d in r.days]


_NOTE_RAW = {
    "close_rate": "close_rate",
    "response_speed": "median_response_seconds",
    "revenue": "revenue_vnd",
    "phone_rate": "phone_rate",
    "page_care": "posts_count",
    "on_time": "on_time_rate",
}


async def _boards(
    db: AsyncSession,
    live: score_service.LivePeriod,
    owner_ids: set[uuid.UUID] | None,
    same_as_range: bool,
) -> Boards:
    names = await _member_names(db)
    ranked = sorted(
        (
            s
            for s in live.scores
            if s.total is not None and (owner_ids is None or s.metrics.member_id in owner_ids)
        ),
        key=lambda s: (-(s.total or 0), names.get(s.metrics.member_id, "")),
    )
    pages = dict(
        (
            await db.execute(
                select(PageAssignment.member_id, Page.name)
                .join(Page, Page.id == PageAssignment.page_id)
                .where(PageAssignment.valid_to.is_(None))
                .order_by(PageAssignment.valid_from)
            )
        ).all()
    )

    def row(score: MemberScore, best: bool) -> BoardRow:
        parts = {c: v for c, v in score.components.items() if v is not None}
        key = (max if best else min)(parts, key=lambda c: parts[c]) if parts else None
        raw = getattr(score.metrics, _NOTE_RAW[key]) if key else None
        mid = score.metrics.member_id
        return BoardRow(
            member=NamedRef(id=mid, name=names.get(mid, "")),
            rank=score.rank,
            total=score.total,
            tier=score.tier,
            page=pages.get(mid),
            note_key=key,
            note_value=Decimal(raw) if raw is not None else None,
        )

    # Mục M: "Dẫn đầu" chỉ hạng A/B, "Cần hỗ trợ" chỉ hạng C/D (điểm thấp nhất trước).
    top = [row(s, True) for s in ranked if s.tier in (Tier.A, Tier.B)][:BOARD_SIZE]
    bottom = [row(s, False) for s in reversed(ranked) if s.tier in (Tier.C, Tier.D)][:BOARD_SIZE]
    return Boards(
        period=live.period.type,
        first_day=live.period.first_day,
        last_day=live.period.last_day,
        same_as_range=same_as_range,
        top=top,
        bottom=bottom,
    )


async def _member_names(db: AsyncSession) -> dict[uuid.UUID, str]:
    rows = await db.execute(
        select(WorkspaceMember.id, User.full_name).join(User, User.id == WorkspaceMember.user_id)
    )
    return {mid: name for mid, name in rows.all()}


async def _campaigns(
    db: AsyncSession, r: DateRange, owner_ids: set[uuid.UUID] | None
) -> list[CampaignSummary]:
    stats = await ads_service.level_stats(db, "campaign", r, owner_ids=owner_ids)
    top = sorted(stats.values(), key=lambda s: (-(s.spend_vnd or 0), -s.leads))[:BOARD_SIZE]
    campaign_names = await ads_service.names(db, "campaign", {s.object_id for s in top})
    return [
        CampaignSummary(
            id=s.object_id,
            name=campaign_names[s.object_id].name,
            spend_vnd=s.spend_vnd,
            leads=s.leads,
            won=s.won,
            cost_per_won_vnd=s.cost_per_won,
        )
        for s in top
        if s.object_id in campaign_names
    ]


def _people(live: score_service.LivePeriod, owner_ids: set[uuid.UUID] | None) -> int:
    """Số người trong danh sách /staff của kỳ (có khách hoặc phụ trách Trang)."""
    return sum(1 for s in live.scores if owner_ids is None or s.metrics.member_id in owner_ids)


async def overview(
    db: AsyncSession,
    ctx: AuthContext,
    range_key: RangeKey,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    team_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> OverviewOut:
    now = now or dt.datetime.now(dt.UTC)
    tz = await workspace_tz(db, ctx.workspace_id)
    r = resolve_range(range_key, tz, now, date_from, date_to)
    prev = r.previous()
    owner_ids = await _scope_ids(db, ctx, team_id)
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    if settings is None:
        raise ServiceError("workspace_not_found", 404)

    # Một lần nạp cho kỳ màn hình (số khách + người) và cho kỳ điểm của khối dẫn đầu.
    range_live = await score_service.live_period(
        db, ctx.workspace_id, Period(PeriodType.ROLLING_7, r.first_day, r.last_day), now
    )
    score_period = _score_period(r)
    same = score_period.first_day == r.first_day and score_period.last_day == r.last_day
    board_live = (
        range_live
        if same
        else await score_service.live_period(db, ctx.workspace_id, score_period, now)
    )
    week7 = (
        board_live
        if board_live.period.last_day - board_live.period.first_day == dt.timedelta(days=6)
        else await score_service.live_period(
            db, ctx.workspace_id, _score_period(resolve_range("today", tz, now)), now
        )
    )
    params = range_live.params
    facts = metrics.in_scope(range_live.facts, owner_ids)
    cur = metrics.summarize(facts, now, params)
    rules = await inbound.load_rules(db, ctx.workspace_id)
    old = metrics.summarize(
        metrics.in_scope(
            await metrics.load_facts(db, rules, prev.start, prev.end, prev.end), owner_ids
        ),
        prev.end,
        params,
    )
    can_cost = ctx.can(Perm.ADS_COST_VIEW)
    cost = None
    if can_cost:
        cost = _metric(
            money_ratio(await _ad_spend(db, r), cur.won_from_ads),
            money_ratio(await _ad_spend(db, prev), old.won_from_ads),
        )
    unassigned_leads = sum(1 for f in facts if f.owner_id is None) if owner_ids is None else None
    return OverviewOut(
        range=RangeOut(key=r.key, first_day=r.first_day, last_day=r.last_day),
        members=_people(range_live, owner_ids),
        pages=int(await db.scalar(select(func.count()).where(Page.is_tracked.is_(True))) or 0),
        bms=int(await db.scalar(select(func.count()).select_from(BusinessManager)) or 0),
        alerts=await _alerts(db, ctx, owner_ids, now, settings, week7, unassigned_leads),
        kpis=OverviewKpis(
            new_leads=_metric(cur.leads, old.leads),
            median_response_seconds=_metric(
                cur.median_response_seconds, old.median_response_seconds
            ),
            phone_rate=_metric(cur.phone_rate, old.phone_rate),
            close_rate=_metric(cur.close_rate, old.close_rate),
            revenue_vnd=_metric(cur.revenue_vnd, old.revenue_vnd),
            cost_per_won_vnd=cost,
            overdue_in_range=cur.overdue,
        ),
        funnel=Funnel(
            new=cur.leads,
            replied=cur.replied,
            unreplied=cur.unreplied,
            phone=cur.phone,
            no_phone=cur.no_phone,
            called=cur.called,
            not_called=cur.not_called,
            won=cur.won,
            lost=cur.lost,
            callback=cur.callback,
            pending=cur.pending,
        ),
        daily=_daily(r, facts),
        campaigns=await _campaigns(db, r, owner_ids) if can_cost else None,
        missing_fx=await ads_service.missing_fx_currencies(db, r) if can_cost else [],
        boards=await _boards(db, board_live, owner_ids, same),
        teams=await _teams(db, ctx),
        is_mock=get_settings().mock_mode,
    )


# ---------------------------------------------------------------- Fanpage


async def _views_by_page(
    db: AsyncSession, first: dt.date, last: dt.date
) -> dict[uuid.UUID, dict[dt.date, int | None]]:
    rows = await db.execute(
        select(PageInsightDaily.page_id, PageInsightDaily.date, PageInsightDaily.views).where(
            PageInsightDaily.date >= first, PageInsightDaily.date <= last
        )
    )
    out: dict[uuid.UUID, dict[dt.date, int | None]] = defaultdict(dict)
    for page_id, day, views in rows.all():
        out[page_id][day] = views
    return out


def _page_status(
    page: Page, bm_status: ConnectionStatus, daily: dict[dt.date, int | None], today: dt.date
) -> PageStatus:
    if page.access_status != ConnectionStatus.ACTIVE or bm_status == ConnectionStatus.DISCONNECTED:
        return "disconnected"
    recent = sum(daily.get(today - dt.timedelta(days=i)) or 0 for i in range(7))
    before = sum(daily.get(today - dt.timedelta(days=i)) or 0 for i in range(7, 14))
    if before > 0 and Decimal(recent) < DECLINE_RATIO * before:
        return "declining"
    return "ok"


async def _page_rows(
    db: AsyncSession,
    ctx: AuthContext,
    now: dt.datetime,
    tz: ZoneInfo,
    team_id: uuid.UUID | None = None,
) -> tuple[list[tuple[PageReportRow, uuid.UUID]], DateRange]:
    """Trang trong phạm vi, kèm BM. Số khách, chốt, trả lời, điểm cùng kỳ 7 ngày (mục J).

    Lọc theo người phụ trách của khách: Trang hiện nếu có khách trong phạm vi hoặc đang do người
    trong phạm vi phụ trách. Toàn workspace thì hiện mọi Trang đang theo dõi.
    """
    owner_ids = await _scope_ids(db, ctx, team_id)
    r = resolve_range("7d", tz, now)
    live = await score_service.live_period(
        db, ctx.workspace_id, Period(PeriodType.ROLLING_7, r.first_day, r.last_day), now
    )
    by_page = metrics.group(metrics.in_scope(live.facts, owner_ids), lambda f: f.page_id)
    scores = {s.metrics.member_id: s for s in live.scores}
    today = now.astimezone(tz).date()
    pages = (
        await db.execute(
            select(Page, BusinessManager.name, BusinessManager.status)
            .join(BusinessManager, BusinessManager.id == Page.business_manager_id)
            .where(Page.is_tracked.is_(True))
        )
    ).all()
    owners = {
        page_id: (member_id, name)
        for page_id, member_id, name in (
            await db.execute(
                select(PageAssignment.page_id, PageAssignment.member_id, User.full_name)
                .join(WorkspaceMember, WorkspaceMember.id == PageAssignment.member_id)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(PageAssignment.valid_to.is_(None))
            )
        ).all()
    }
    # Bài đăng cùng kỳ 7 ngày với các cột khác và với điểm Chăm Trang (decisions.md mục L).
    posts = dict(
        (
            await db.execute(
                select(PagePost.page_id, func.count())
                .where(PagePost.created_time >= live.start, PagePost.created_time < live.until)
                .group_by(PagePost.page_id)
            )
        ).all()
    )
    first = today - dt.timedelta(days=29)
    views = await _views_by_page(db, first, today)
    names = await _member_names(db)

    out = []
    for page, bm_name, bm_status in pages:
        owner = owners.get(page.id)
        items = by_page.get(page.id, [])
        owned_in_scope = owner is not None and (owner_ids is None or owner[0] in owner_ids)
        if owner_ids is not None and not items and not owned_in_scope:
            continue
        summary = metrics.summarize(items, now, live.params)
        score = scores.get(owner[0]) if owner else None
        shares = _owner_shares(items, owner[0] if owner else None, names)
        daily = views.get(page.id, {})
        days = [first + dt.timedelta(days=i) for i in range(30)]
        has_views = any(daily.get(d) is not None for d in days)
        row = PageReportRow(
            id=page.id,
            name=page.name,
            fb_page_id=page.fb_page_id,
            bm_name=bm_name,
            owner=NamedRef(id=owner[0], name=owner[1]) if owner else None,
            owner_total=score.total if score else None,
            owner_tier=score.tier if score else None,
            owners_in_range=shares,
            leads_7d=summary.leads,
            median_response_seconds=summary.median_response_seconds,
            won_7d=summary.won,
            revenue_7d=summary.revenue_vnd,
            overdue_7d=summary.overdue,
            posts_7d=int(posts.get(page.id, 0)) if page.content_synced_at else None,
            views_30d=sum(daily.get(d) or 0 for d in days) if has_views else None,
            views_daily=[daily.get(d) for d in days],
            status=_page_status(page, bm_status, daily, today),
        )
        out.append((row, page.business_manager_id))
    return out, r


def _owner_shares(
    items: list[LeadFacts], current: uuid.UUID | None, names: dict[uuid.UUID, str]
) -> list[OwnerShare]:
    """Số khách của Trang theo người (kể cả "chưa có người", và người đang phụ trách dù 0 khách).
    Chỉ trả khi có hơn một người, để giải thích vì sao khách của Trang khác khách của người
    đang phụ trách."""
    counts: dict[uuid.UUID | None, int] = defaultdict(int)
    for f in items:
        counts[f.owner_id] += 1
    if current is not None and items:
        counts.setdefault(current, 0)
    if len(counts) <= 1:
        return []
    return [
        OwnerShare(
            member=NamedRef(id=mid, name=names.get(mid, "")) if mid is not None else None,
            leads=n,
        )
        for mid, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0] is None))
    ]


def _in_tab(row: PageReportRow, tab: PageTab) -> bool:
    if tab == "unassigned":
        return row.owner is None
    if tab == "low_posts":
        return row.posts_7d is not None and row.posts_7d < LOW_POSTS_THRESHOLD
    if tab == "declining":
        return row.status == "declining"
    if tab == "disconnected":
        return row.status == "disconnected"
    return True


def _sort_key(sort: PageSort) -> Any:
    if sort == "score":
        return lambda r: (r.owner_total is None, r.owner_total or 0, r.name)
    if sort == "posts":
        return lambda r: (r.posts_7d is None, r.posts_7d or 0, r.name)
    if sort == "name":
        return lambda r: r.name.lower()
    return lambda r: (-r.leads_7d, r.name)


async def pages_report(
    db: AsyncSession,
    ctx: AuthContext,
    *,
    tab: PageTab = "all",
    q: str | None = None,
    bm_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    sort: PageSort = "leads",
    page: int = 1,
    page_size: int = PAGE_SIZE,
    now: dt.datetime | None = None,
) -> PageReportList:
    now = now or dt.datetime.now(dt.UTC)
    tz = await workspace_tz(db, ctx.workspace_id)
    all_rows, r = await _page_rows(db, ctx, now, tz, team_id)
    needle = (q or "").strip().lower()
    filtered = [
        row
        for row, row_bm in all_rows
        if (bm_id is None or row_bm == bm_id)
        and (
            not needle
            or needle in row.name.lower()
            or needle in row.fb_page_id
            or (row.owner is not None and needle in row.owner.name.lower())
        )
    ]

    def count(tab_key: PageTab) -> int:
        return sum(1 for r in filtered if _in_tab(r, tab_key))

    tabs = PageTabs(
        all=count("all"),
        unassigned=count("unassigned"),
        low_posts=count("low_posts"),
        declining=count("declining"),
        disconnected=count("disconnected"),
    )
    rows = sorted((r for r in filtered if _in_tab(r, tab)), key=_sort_key(sort))
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    bms = [
        NamedRef(id=i, name=n)
        for i, n in (
            await db.execute(
                select(BusinessManager.id, BusinessManager.name).order_by(BusinessManager.name)
            )
        ).all()
    ]
    start = (max(page, 1) - 1) * page_size
    return PageReportList(
        rows=rows[start : start + page_size],
        total=len(rows),
        page=max(page, 1),
        page_size=page_size,
        tabs=tabs,
        bms=bms if ctx.can(Perm.BM_VIEW) else [],
        teams=await _teams(db, ctx),
        posts_target=settings.posts_per_week_target if settings else 5,
        can_assign=ctx.can(Perm.PAGE_ASSIGN),
        range=RangeOut(key=r.key, first_day=r.first_day, last_day=r.last_day),
        is_mock=get_settings().mock_mode,
    )


async def all_page_rows(db: AsyncSession, ctx: AuthContext) -> list[PageReportRow]:
    now = dt.datetime.now(dt.UTC)
    rows, _ = await _page_rows(db, ctx, now, await workspace_tz(db, ctx.workspace_id))
    return sorted((r for r, _ in rows), key=_sort_key("leads"))


# ---------------------------------------------------------------- Chi tiết Trang


def _engagement(post: PagePost) -> Decimal | None:
    if not post.views:
        return None
    return ratio(post.reactions + post.comments + post.shares, post.views)


def _heatmap(posts: list[PagePost], tz: ZoneInfo) -> list[list[Decimal | None]] | None:
    rated: list[tuple[PagePost, Decimal]] = [
        (p, rate) for p in posts if (rate := _engagement(p)) is not None
    ]
    if len(rated) < HEATMAP_MIN_POSTS:
        return None
    cells: dict[tuple[int, int], list[Decimal]] = defaultdict(list)
    for post, rate in rated:
        local = post.created_time.astimezone(tz)
        for slot, (lo, hi) in enumerate(HEAT_SLOTS):
            if lo <= local.hour < hi:
                cells[(local.weekday(), slot)].append(rate)

    def average(values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return (sum(values, Decimal(0)) / len(values)).quantize(Decimal("0.0001"))

    return [[average(cells.get((d, s), [])) for s in range(len(HEAT_SLOTS))] for d in range(7)]


async def page_detail(
    db: AsyncSession, ctx: AuthContext, page_id: uuid.UUID, now: dt.datetime | None = None
) -> PageDetailOut:
    now = now or dt.datetime.now(dt.UTC)
    tz = await workspace_tz(db, ctx.workspace_id)
    found = (
        await db.execute(
            select(Page, BusinessManager.name, BusinessManager.status)
            .join(BusinessManager, BusinessManager.id == Page.business_manager_id)
            .where(Page.id == page_id, Page.is_tracked.is_(True))
        )
    ).first()
    if found is None:
        raise ServiceError("page_not_found", 404)
    page, bm_name, bm_status = found
    owner_row = (
        await db.execute(
            select(PageAssignment.member_id, User.full_name, Team.name)
            .join(WorkspaceMember, WorkspaceMember.id == PageAssignment.member_id)
            .join(User, User.id == WorkspaceMember.user_id)
            .outerjoin(Team, Team.id == WorkspaceMember.team_id)
            .where(PageAssignment.page_id == page.id, PageAssignment.valid_to.is_(None))
        )
    ).first()
    owner_ids = await member_ids_for(db, ctx, ctx.scope(Perm.REPORT_VIEW))
    if owner_ids is not None and (owner_row is None or owner_row[0] not in owner_ids):
        raise ServiceError("page_not_found", 404)

    today = now.astimezone(tz).date()
    first = today - dt.timedelta(days=29)
    prev_first = first - dt.timedelta(days=30)
    rows = {
        r.date: r
        for r in await db.scalars(
            select(PageInsightDaily).where(
                PageInsightDaily.page_id == page.id,
                PageInsightDaily.date >= prev_first,
                PageInsightDaily.date <= today,
            )
        )
    }

    def window_sum(column: str, start: dt.date) -> int | None:
        values = [
            getattr(rows[d], column)
            for i in range(30)
            if (d := start + dt.timedelta(days=i)) in rows and getattr(rows[d], column) is not None
        ]
        return sum(values) if values else None

    def metric(column: str) -> Metric:
        return _metric(window_sum(column, first), window_sum(column, prev_first))

    window_start = dt.datetime.combine(first, dt.time(0), tzinfo=tz)
    prev_start = dt.datetime.combine(prev_first, dt.time(0), tzinfo=tz)
    posts = list(
        await db.scalars(
            select(PagePost)
            .where(PagePost.page_id == page.id, PagePost.created_time >= window_start)
            .order_by(PagePost.created_time.desc())
        )
    )
    prev_posts = await db.scalar(
        select(func.count()).where(
            PagePost.page_id == page.id,
            and_(PagePost.created_time >= prev_start, PagePost.created_time < window_start),
        )
    )
    followers = next(
        (rows[d].followers for d in sorted(rows, reverse=True) if rows[d].followers is not None),
        None,
    )
    synced = page.content_synced_at is not None
    return PageDetailOut(
        id=page.id,
        name=page.name,
        fb_page_id=page.fb_page_id,
        bm_name=bm_name,
        status=_page_status(page, bm_status, {d: r.views for d, r in rows.items()}, today),
        owner=NamedRef(id=owner_row[0], name=owner_row[1]) if owner_row else None,
        team=owner_row[2] if owner_row else None,
        content_synced_at=page.content_synced_at,
        kpis=PageKpis(
            followers=followers,
            new_follows=metric("new_follows"),
            views=metric("views"),
            reach=metric("reach"),
            engagements=metric("engagements"),
            video_views=metric("video_views"),
            posts=_metric(len(posts) if synced else None, prev_posts if synced else None),
        ),
        daily_views=[
            DayValue(day=d, value=rows[d].views if d in rows else None)
            for d in (first + dt.timedelta(days=i) for i in range(30))
        ],
        heatmap=_heatmap(posts, tz),
        heatmap_min_posts=HEATMAP_MIN_POSTS,
        posts=[
            PostRow(
                id=p.id,
                excerpt=p.excerpt,
                created_time=p.created_time,
                type=p.type,
                views=p.views,
                reactions=p.reactions,
                comments=p.comments,
                shares=p.shares,
                engagement_rate=_engagement(p),
                permalink=p.permalink,
            )
            for p in posts
        ],
        is_mock=get_settings().mock_mode,
    )


async def campaign_name(db: AsyncSession, campaign_id: uuid.UUID | None) -> str | None:
    if campaign_id is None:
        return None
    return await db.scalar(select(Campaign.name).where(Campaign.id == campaign_id))
