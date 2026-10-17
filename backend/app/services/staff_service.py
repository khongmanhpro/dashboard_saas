"""Bảng xếp hạng, hồ sơ nhân viên, công thức điểm (Bước 4).

Phạm vi xem theo `leaderboard.view` (quyết định #9):
- ALL (Chủ sở hữu, Quản lý, Chỉ xem): mọi người.
- TEAM (Trưởng nhóm): người trong nhóm mình dẫn dắt hoặc thuộc về, và bản thân.
- OWN (Nhân viên): điểm của mình; cộng tên và hạng top 10 nếu bật `staff_can_see_leaderboard`.
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Perm, Scope
from app.models import (
    Contact,
    Lead,
    LeadgenSubmission,
    LeadSource,
    Page,
    PageAssignment,
    PeriodType,
    ScoreFormula,
    ScoreSnapshot,
    Team,
    Tier,
    User,
    WorkspaceMember,
    WorkspaceSettings,
)
from app.schemas.leads import NamedRef
from app.schemas.staff import (
    AssignedPage,
    FormulaOut,
    FormulaUpdate,
    FunnelStep,
    HourBucket,
    Kpis,
    Leaderboard,
    LeaderboardRow,
    PastPage,
    PeriodInfo,
    PreviewOut,
    PreviewRow,
    RecentLead,
    ScorePart,
    StaffDetail,
    Thresholds,
    TrendPoint,
    UnassignedRow,
    Weights,
)
from app.services import audit, inbound, metrics
from app.services.errors import ServiceError
from app.services.lead_service import member_ids_for
from app.services.periods import period_for
from app.services.score_service import (
    compute_period,
    current_formula,
    live_period,
    recompute_workspace,
)
from app.services.scoring import (
    CRITERIA,
    THRESHOLD_FIELDS,
    FormulaParams,
    MemberScore,
    revenue_target,
)

if TYPE_CHECKING:
    from app.api.deps import AuthContext

TOP_FOR_STAFF = 10
TREND_WEEKS = 8
HOUR_BUCKETS: list[tuple[str, int, int]] = [
    ("8-10", 8, 10),
    ("10-12", 10, 12),
    ("12-14", 12, 14),
    ("14-17", 14, 17),
    ("17-19", 17, 19),
    ("19-22", 19, 22),
    ("22-8", 22, 8),
]


def _rate(part: int, whole: int) -> Decimal | None:
    if whole <= 0:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- công thức


def _formula_out(
    f: ScoreFormula, created_by: str | None, can_edit: bool, page_care_available: bool
) -> FormulaOut:
    return FormulaOut(
        version=f.version,
        weights=Weights(**{c: getattr(f, f"w_{c}") for c in CRITERIA}),
        speed_full_minutes=f.speed_full_minutes,
        speed_zero_minutes=f.speed_zero_minutes,
        tier_a=f.tier_a,
        tier_b=f.tier_b,
        tier_c=f.tier_c,
        min_leads=f.min_leads,
        posts_per_week_target=f.posts_per_week_target,
        thresholds=Thresholds(**{k: getattr(f, k) for k in THRESHOLD_FIELDS}),
        score_method=f.score_method,
        effective_from=f.effective_from,
        created_by=created_by,
        page_care_available=page_care_available,
        can_edit=can_edit,
    )


async def get_formula(db: AsyncSession, ctx: AuthContext) -> FormulaOut:
    f = await current_formula(db, ctx.workspace_id)
    created_by = None
    if f.created_by_member_id:
        created_by = await db.scalar(
            select(User.full_name)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.id == f.created_by_member_id)
        )
    synced = await db.scalar(select(Page.id).where(Page.content_synced_at.is_not(None)).limit(1))
    return _formula_out(f, created_by, ctx.can(Perm.SCORE_FORMULA_EDIT), synced is not None)


async def _member_names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(
        select(WorkspaceMember.id, User.full_name)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.id.in_(ids))
    )
    return {mid: name for mid, name in rows.all()}


async def preview_formula(
    db: AsyncSession, ctx: AuthContext, body: FormulaUpdate, *, now: dt.datetime | None = None
) -> PreviewOut:
    """Điểm tuần hiện tại với công thức đang dùng và với trọng số, ngưỡng mới (cùng hàm với job)."""
    now = now or dt.datetime.now(dt.UTC)
    formula = await current_formula(db, ctx.workspace_id)
    params = FormulaParams.from_model(formula)
    rules = await inbound.load_rules(db, ctx.workspace_id)
    period = period_for(PeriodType.WEEK, now, rules.tz)
    current = {
        s.metrics.member_id: s
        for s in await compute_period(db, ctx.workspace_id, period, params, now)
    }
    proposed = await compute_period(
        db,
        ctx.workspace_id,
        period,
        params.with_changes(weights=body.weights.model_dump(), **body.thresholds.model_dump()),
        now,
    )
    names = await _member_names(db, set(current))
    rows = [
        PreviewRow(
            member=NamedRef(id=s.metrics.member_id, name=names.get(s.metrics.member_id, "")),
            current_total=current[s.metrics.member_id].total,
            current_tier=current[s.metrics.member_id].tier,
            new_total=s.total,
            new_tier=s.tier,
            new_rank=s.rank,
        )
        for s in proposed
        if not s.insufficient_data
    ]
    rows.sort(key=lambda r: (r.new_rank is None, r.new_rank or 0, r.member.name))
    return PreviewOut(period_first_day=period.first_day, period_last_day=period.last_day, rows=rows)


async def update_formula(
    db: AsyncSession, ctx: AuthContext, body: FormulaUpdate, *, now: dt.datetime | None = None
) -> FormulaOut:
    """Thêm phiên bản công thức mới, áp dụng ngay cho kỳ chưa chốt rồi tính lại."""
    now = now or dt.datetime.now(dt.UTC)
    old = await current_formula(db, ctx.workspace_id)
    new = ScoreFormula(
        workspace_id=ctx.workspace_id,
        version=old.version + 1,
        tier_a=old.tier_a,
        tier_b=old.tier_b,
        tier_c=old.tier_c,
        min_leads=old.min_leads,
        posts_per_week_target=old.posts_per_week_target,
        effective_from=now,
        created_by_member_id=ctx.member_id,
        **{f"w_{c}": v for c, v in body.weights.model_dump().items()},
        **body.thresholds.model_dump(),
    )
    db.add(new)
    await db.flush()
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="score_formula.updated",
        entity_type="score_formula",
        entity_id=new.id,
        before={
            "version": old.version,
            **{c: getattr(old, f"w_{c}") for c in CRITERIA},
            **{k: getattr(old, k) for k in THRESHOLD_FIELDS},
        },
        after={
            "version": new.version,
            **body.weights.model_dump(),
            **body.thresholds.model_dump(),
        },
        ip=ctx.ip,
    )
    await recompute_workspace(db, ctx.workspace_id, now, finalize_previous_week=False)
    await db.commit()
    return await get_formula(db, ctx)


async def recompute_now(
    db: AsyncSession, ctx: AuthContext, *, now: dt.datetime | None = None
) -> dict[str, int]:
    counts = await recompute_workspace(db, ctx.workspace_id, now or dt.datetime.now(dt.UTC))
    await db.commit()
    return counts


# ---------------------------------------------------------------- phạm vi và dữ liệu chung


async def _members_info(
    db: AsyncSession, workspace_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, Any]]:
    rows = await db.execute(
        select(
            WorkspaceMember.id,
            User.full_name,
            WorkspaceMember.team_id,
            Team.name,
            WorkspaceMember.role,
        )
        .join(User, User.id == WorkspaceMember.user_id)
        .outerjoin(Team, Team.id == WorkspaceMember.team_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    return {
        mid: {"name": name, "team_id": team_id, "team_name": team_name, "role": role}
        for mid, name, team_id, team_name, role in rows.all()
    }


async def _current_pages(db: AsyncSession) -> dict[uuid.UUID, list[AssignedPage]]:
    rows = await db.execute(
        select(PageAssignment.member_id, Page.id, Page.name, PageAssignment.valid_from)
        .join(Page, Page.id == PageAssignment.page_id)
        .where(PageAssignment.valid_to.is_(None))
        .order_by(Page.name)
    )
    pages: dict[uuid.UUID, list[AssignedPage]] = defaultdict(list)
    for member_id, page_id, name, since in rows.all():
        pages[member_id].append(AssignedPage(id=page_id, name=name, since=since))
    return pages


async def _past_pages(
    db: AsyncSession, start: dt.datetime, until: dt.datetime
) -> dict[uuid.UUID, list[PastPage]]:
    """Trang người này đã thôi phụ trách trong kỳ: mỗi Trang một dòng, lần kết thúc gần nhất.

    Trang người đó vẫn đang phụ trách (được gán lại sau) không tính."""
    current = {
        (member_id, page_id)
        for member_id, page_id in (
            await db.execute(
                select(PageAssignment.member_id, PageAssignment.page_id).where(
                    PageAssignment.valid_to.is_(None)
                )
            )
        ).all()
    }
    rows = await db.execute(
        select(
            PageAssignment.member_id,
            PageAssignment.page_id,
            Page.name,
            func.max(PageAssignment.valid_to),
        )
        .join(Page, Page.id == PageAssignment.page_id)
        .where(PageAssignment.valid_to >= start, PageAssignment.valid_to < until)
        .group_by(PageAssignment.member_id, PageAssignment.page_id, Page.name)
        .order_by(func.max(PageAssignment.valid_to))
    )
    out: dict[uuid.UUID, list[PastPage]] = defaultdict(list)
    for member_id, page_id, name, until_at in rows.all():
        if (member_id, page_id) not in current:
            out[member_id].append(PastPage(name=name, until=until_at))
    return out


async def _previous_week_totals(
    db: AsyncSession, first_day: dt.date
) -> dict[uuid.UUID, tuple[Decimal | None, uuid.UUID]]:
    """Điểm tuần trước kèm phiên bản công thức đã dùng để tính (mục L)."""
    rows = await db.execute(
        select(ScoreSnapshot.member_id, ScoreSnapshot.total, ScoreSnapshot.formula_id).where(
            ScoreSnapshot.period_type == PeriodType.WEEK,
            ScoreSnapshot.period_start == first_day - dt.timedelta(days=7),
        )
    )
    return {mid: (total, formula_id) for mid, total, formula_id in rows.all()}


# ---------------------------------------------------------------- bảng xếp hạng


def _row_metrics(summary: metrics.Summary) -> dict[str, Any]:
    return {
        "lead_count": summary.leads,
        "won_count": summary.won,
        "median_response_seconds": summary.median_response_seconds,
        "phone_rate": summary.phone_rate,
        "close_rate": summary.close_rate,
        "revenue_vnd": summary.revenue_vnd,
        "overdue_count": summary.overdue,
    }


async def leaderboard(
    db: AsyncSession, ctx: AuthContext, period_type: PeriodType, *, now: dt.datetime | None = None
) -> Leaderboard:
    """Kỳ chưa chốt: tính trực tiếp bằng đúng hàm của job (decisions.md mục J)."""
    now = now or dt.datetime.now(dt.UTC)
    scope = ctx.scope(Perm.LEADERBOARD_VIEW)
    formula = await current_formula(db, ctx.workspace_id)
    rules = await inbound.load_rules(db, ctx.workspace_id)
    live = await live_period(
        db,
        ctx.workspace_id,
        period_for(period_type, now, rules.tz),
        now,
        FormulaParams.from_model(formula),
    )
    info = PeriodInfo(
        type=period_type,
        first_day=live.period.first_day,
        last_day=live.period.last_day,
        computed_at=now,
        is_final=False,
    )
    members = await _members_info(db, ctx.workspace_id)
    pages = await _current_pages(db)
    deltas: dict[uuid.UUID, tuple[Decimal | None, uuid.UUID]] = {}
    if period_type == PeriodType.WEEK:
        deltas = await _previous_week_totals(db, live.period.first_day)
    by_owner = metrics.group(live.facts, lambda f: f.owner_id)
    past = await _past_pages(db, live.start, live.until)

    visible = await member_ids_for(db, ctx, scope)
    full_view = scope in (Scope.ALL, Scope.TEAM)
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    staff_sees_top = bool(settings and settings.staff_can_see_leaderboard)

    rows: list[LeaderboardRow] = []
    for score in live.scores:
        mid = score.metrics.member_id
        in_scope = visible is None or mid in visible
        top_only = (
            not in_scope
            and scope == Scope.OWN
            and staff_sees_top
            and score.rank is not None
            and score.rank <= TOP_FOR_STAFF
        )
        if not in_scope and not top_only:
            continue
        info_m = members.get(mid, {})
        summary = metrics.summarize(by_owner.get(mid, []), now, live.params)
        shown = _row_metrics(summary) if in_scope else dict.fromkeys(_row_metrics(summary))
        delta = None
        other_formula = False
        previous, previous_formula = deltas.get(mid, (None, formula.id))
        if in_scope and score.total is not None and previous is not None:
            delta = score.total - previous
            other_formula = previous_formula != formula.id
        rows.append(
            LeaderboardRow(
                member=NamedRef(id=mid, name=info_m.get("name", "")),
                role=info_m.get("role"),
                team=NamedRef(id=info_m["team_id"], name=info_m["team_name"])
                if info_m.get("team_id")
                else None,
                pages=[p.name for p in pages.get(mid, [])],
                past_pages=past.get(mid, []),
                is_self=mid == ctx.member_id,
                rank=score.rank,
                tier=score.tier,
                insufficient_data=score.insufficient_data,
                total=score.total if in_scope else None,
                delta=delta,
                delta_other_formula=other_formula,
                **shown,
            )
        )
    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.member.name))

    tiers = kpis = insufficient = unassigned = None
    teams: list[NamedRef] = []
    if full_view:
        in_view = [s for s in live.scores if visible is None or s.metrics.member_id in visible]
        tiers = {t: sum(1 for s in in_view if s.tier == t) for t in Tier}
        insufficient = sum(1 for s in in_view if s.insufficient_data)
        # Toàn workspace thì gồm cả khách chưa có người phụ trách: ô chỉ số = Tổng quan.
        total = metrics.summarize(metrics.in_scope(live.facts, visible), now, live.params)
        kpis = Kpis(
            lead_count=total.leads,
            won_count=total.won,
            median_response_seconds=total.median_response_seconds,
            phone_rate=total.phone_rate,
            close_rate=total.close_rate,
            revenue_vnd=total.revenue_vnd,
            overdue_count=total.overdue,
        )
        orphans = by_owner.get(None, [])
        if visible is None and orphans:
            unassigned = UnassignedRow(**_row_metrics(metrics.summarize(orphans, now, live.params)))
        team_ids = {
            members[s.metrics.member_id]["team_id"]
            for s in in_view
            if members.get(s.metrics.member_id, {}).get("team_id")
        }
        teams = sorted(
            (
                NamedRef(
                    id=tid,
                    name=next(m["team_name"] for m in members.values() if m["team_id"] == tid),
                )
                for tid in team_ids
            ),
            key=lambda t: t.name,
        )
    return Leaderboard(
        period=info,
        min_leads=formula.min_leads,
        tiers=tiers,
        insufficient_count=insufficient,
        kpis=kpis,
        teams=teams,
        rows=rows,
        unassigned=unassigned,
        full_view=full_view,
    )


# ---------------------------------------------------------------- hồ sơ nhân viên


def _parts(
    score: MemberScore | None,
    formula: ScoreFormula,
    params: FormulaParams,
    period_days: Decimal,
) -> list[ScorePart]:
    weights = {c: int(getattr(formula, f"w_{c}")) for c in CRITERIA}
    components: dict[str, Decimal | None] = (
        dict(score.components) if score else dict.fromkeys(CRITERIA)
    )
    used = sum(w for c, w in weights.items() if components.get(c) is not None and w > 0)
    m = score.metrics if score else None
    raw: dict[str, dict[str, int | Decimal | None]] = {
        "close_rate": {"rate": m.close_rate if m else None, "won": m.won_count if m else None},
        "response_speed": {"median_seconds": m.median_response_seconds if m else None},
        "revenue": {"revenue_vnd": m.revenue_vnd if m else None},
        "phone_rate": {"rate": m.phone_rate if m else None, "phones": m.phone_count if m else None},
        "page_care": {
            "posts": m.posts_count if m else None,
            "target": formula.posts_per_week_target,
        },
        "on_time": {"rate": m.on_time_rate if m else None},
    }
    # Ngưỡng hiển thị: phần trăm, phút, hoặc ₫ đã quy theo số ngày của kỳ (mục K).
    bounds: dict[str, tuple[Decimal, Decimal] | None] = {
        "close_rate": (Decimal(params.close_rate_zero), Decimal(params.close_rate_full)),
        "response_speed": (
            Decimal(params.speed_zero_minutes),
            Decimal(params.speed_full_minutes),
        ),
        "revenue": (Decimal(0), revenue_target(params, period_days).quantize(Decimal(1))),
        "phone_rate": (Decimal(params.phone_rate_zero), Decimal(params.phone_rate_full)),
        "page_care": None,
        "on_time": (Decimal(params.on_time_zero), Decimal(params.on_time_full)),
    }
    parts = []
    for c in CRITERIA:
        component = components.get(c)
        effective = points = None
        if component is not None and used and weights[c] > 0:
            effective = (Decimal(weights[c]) * 100 / Decimal(used)).quantize(Decimal("0.01"))
            points = (component * Decimal(weights[c]) / Decimal(used)).quantize(Decimal("0.01"))
        bound = bounds[c]
        parts.append(
            ScorePart(
                key=c,
                weight=weights[c],
                effective_weight=effective,
                score=component,
                points=points,
                raw=raw[c],
                method="target" if bound is None else "linear",
                zero=bound[0] if bound else None,
                full=bound[1] if bound else None,
            )
        )
    return parts


async def staff_detail(
    db: AsyncSession,
    ctx: AuthContext,
    member_id: uuid.UUID,
    period_type: PeriodType,
    *,
    now: dt.datetime | None = None,
) -> StaffDetail:
    now = now or dt.datetime.now(dt.UTC)
    visible = await member_ids_for(db, ctx, ctx.scope(Perm.LEADERBOARD_VIEW))
    if visible is not None and member_id not in visible:
        raise ServiceError("member_not_found", 404)
    members = await _members_info(db, ctx.workspace_id)
    me = members.get(member_id)
    if me is None:
        raise ServiceError("member_not_found", 404)
    team_lead = None
    if me["team_id"]:
        team_lead = await db.scalar(
            select(User.full_name)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .join(Team, Team.lead_member_id == WorkspaceMember.id)
            .where(Team.id == me["team_id"])
        )
    rules = await inbound.load_rules(db, ctx.workspace_id)
    formula = await current_formula(db, ctx.workspace_id)
    params = FormulaParams.from_model(formula)
    period = period_for(period_type, now, rules.tz)
    live = await live_period(db, ctx.workspace_id, period, now, params)
    score = next((s for s in live.scores if s.metrics.member_id == member_id), None)
    ranked_count = sum(1 for s in live.scores if s.rank is not None)

    delta = None
    delta_other_formula = False
    if score and score.total is not None and period_type == PeriodType.WEEK:
        prev = (
            await db.execute(
                select(ScoreSnapshot.total, ScoreSnapshot.formula_id).where(
                    ScoreSnapshot.period_type == PeriodType.WEEK,
                    ScoreSnapshot.member_id == member_id,
                    ScoreSnapshot.period_start == period.first_day - dt.timedelta(days=7),
                )
            )
        ).first()
        if prev is not None and prev.total is not None:
            delta = score.total - prev.total
            delta_other_formula = prev.formula_id != formula.id

    mine = [f for f in live.facts if f.owner_id == member_id]
    funnel = _funnel(
        metrics.summarize(mine, now, params), metrics.summarize(live.facts, now, params)
    )
    start, end = period.utc_range(rules.tz)
    hours = await _hours(db, member_id, start, end, rules.tz)
    trend = await _trend(db, ctx, member_id, now, rules.tz, formula, period_type, score)
    recent = await _recent_leads(db, member_id, now)
    pages = (await _current_pages(db)).get(member_id, [])
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    elapsed = Decimal(max((live.until - live.start).total_seconds(), 0)) / 86400
    target = (Decimal(params.posts_per_week_target) * max(elapsed, Decimal(1)) / 7).quantize(
        Decimal("0.1")
    )
    return StaffDetail(
        member=NamedRef(id=member_id, name=me["name"]),
        role=me["role"],
        team=NamedRef(id=me["team_id"], name=me["team_name"]) if me["team_id"] else None,
        team_lead=team_lead,
        pages=pages,
        period=PeriodInfo(
            type=period_type,
            first_day=period.first_day,
            last_day=period.last_day,
            computed_at=now,
            is_final=False,
        ),
        total=score.total if score else None,
        tier=score.tier if score else None,
        rank=score.rank if score else None,
        ranked_count=ranked_count,
        delta=delta,
        delta_other_formula=delta_other_formula,
        formula_version=formula.version,
        insufficient_data=score.insufficient_data if score else True,
        min_leads=formula.min_leads,
        lead_count=len(mine),
        parts=_parts(score, formula, params, max(elapsed, Decimal(1))),
        funnel=funnel,
        hours=hours,
        trend=trend,
        recent=recent,
        slow_reply_minutes=settings.slow_reply_minutes if settings else 30,
        speed_full_minutes=params.speed_full_minutes,
        speed_zero_minutes=params.speed_zero_minutes,
        posts_target=target,
    )


async def _trend(
    db: AsyncSession,
    ctx: AuthContext,
    member_id: uuid.UUID,
    now: dt.datetime,
    tz: Any,
    formula: ScoreFormula,
    period_type: PeriodType,
    score: MemberScore | None,
) -> list[TrendPoint]:
    """Các tuần đã chốt (bảng lưu) cộng tuần này (tính trực tiếp). Ghi phiên bản công thức của
    từng tuần để giao diện đánh dấu tuần tính bằng công thức khác (mục L)."""
    params = FormulaParams.from_model(formula)
    week = period_for(PeriodType.WEEK, now, tz)
    rows = (
        await db.execute(
            select(ScoreSnapshot, ScoreFormula.version)
            .join(ScoreFormula, ScoreFormula.id == ScoreSnapshot.formula_id)
            .where(
                ScoreSnapshot.period_type == PeriodType.WEEK,
                ScoreSnapshot.member_id == member_id,
                ScoreSnapshot.period_start < week.first_day,
            )
            .order_by(ScoreSnapshot.period_start.desc())
            .limit(TREND_WEEKS - 1)
        )
    ).all()
    points = [
        TrendPoint(
            first_day=r.period_start,
            total=r.total,
            tier=r.tier,
            is_final=r.is_final,
            formula_version=version,
            other_formula=r.formula_id != formula.id,
        )
        for r, version in reversed(rows)
    ]
    if period_type != PeriodType.WEEK:
        live = await live_period(db, ctx.workspace_id, week, now, params)
        score = next((s for s in live.scores if s.metrics.member_id == member_id), None)
    points.append(
        TrendPoint(
            first_day=week.first_day,
            total=score.total if score else None,
            tier=score.tier if score else None,
            is_final=False,
            formula_version=formula.version,
            other_formula=False,
        )
    )
    return points


def _funnel(mine: metrics.Summary, company: metrics.Summary) -> list[FunnelStep]:
    """Phễu lồng nhau (docs/metrics.md). Chốt tính trên khách mới vì có thể chốt mà không gọi."""

    def steps(s: metrics.Summary) -> dict[str, tuple[int, int]]:
        return {
            "leads": (s.leads, 0),
            "replied": (s.replied, s.leads),
            "phone": (s.phone, s.replied),
            "called": (s.called, s.phone),
            "won": (s.won, s.leads),
        }

    a, b = steps(mine), steps(company)
    return [
        FunnelStep(
            key=key,
            value=a[key][0],
            rate=None if key == "leads" else metrics.rate(*a[key]),
            company_rate=None if key == "leads" else metrics.rate(*b[key]),
        )
        for key in ("leads", "replied", "phone", "called", "won")
    ]


async def _hours(
    db: AsyncSession, member_id: uuid.UUID, start: dt.datetime, end: dt.datetime, tz: Any
) -> list[HourBucket]:
    rows = await db.execute(
        select(Lead.first_inbound_at, Lead.response_business_seconds).where(
            Lead.owner_member_id == member_id,
            Lead.merged_into_lead_id.is_(None),
            Lead.source == LeadSource.MESSAGE,
            Lead.first_inbound_at >= start,
            Lead.first_inbound_at < end,
            Lead.response_business_seconds.is_not(None),
        )
    )
    samples: dict[str, list[int]] = defaultdict(list)
    for at, seconds in rows.all():
        if seconds is None:
            continue
        hour = at.astimezone(tz).hour
        for label, lo, hi in HOUR_BUCKETS:
            inside = lo <= hour < hi if lo < hi else (hour >= lo or hour < hi)
            if inside:
                samples[label].append(seconds)
                break
    return [
        HourBucket(
            label=label,
            median_minutes=(Decimal(statistics.median(samples[label])) / 60).quantize(
                Decimal("0.1")
            )
            if samples[label]
            else None,
            count=len(samples[label]),
        )
        for label, _, _ in HOUR_BUCKETS
    ]


async def _recent_leads(
    db: AsyncSession, member_id: uuid.UUID, now: dt.datetime
) -> list[RecentLead]:
    form_name = (
        select(LeadgenSubmission.field_data["full_name"].astext)
        .where(LeadgenSubmission.lead_id == Lead.id)
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Lead, Contact.display_name, Contact.psid, form_name.label("form_name"))
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .where(Lead.owner_member_id == member_id, Lead.merged_into_lead_id.is_(None))
        .order_by(Lead.first_inbound_at.desc())
        .limit(6)
    )
    return [
        RecentLead(
            id=r.Lead.id,
            display_name=r.display_name or r.form_name,
            short_ref=(r.psid or r.Lead.id.hex)[-4:],
            first_inbound_at=r.Lead.first_inbound_at,
            response_business_seconds=r.Lead.response_business_seconds,
            status=r.Lead.status,
            overdue=r.Lead.result_at is None and r.Lead.result_due_at < now,
        )
        for r in rows.all()
    ]
