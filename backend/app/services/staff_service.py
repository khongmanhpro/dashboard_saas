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
    FunnelStep,
    HourBucket,
    Kpis,
    Leaderboard,
    LeaderboardRow,
    PeriodInfo,
    PreviewOut,
    PreviewRow,
    RecentLead,
    ScorePart,
    StaffDetail,
    TrendPoint,
    Weights,
)
from app.services import audit, inbound
from app.services.errors import ServiceError
from app.services.lead_service import member_ids_for
from app.services.periods import Period, period_for
from app.services.score_service import (
    compute_period,
    current_formula,
    lead_facts,
    recompute_workspace,
)
from app.services.scoring import CRITERIA, FormulaParams, speed_samples

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


def _formula_out(f: ScoreFormula, created_by: str | None, can_edit: bool) -> FormulaOut:
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
        effective_from=f.effective_from,
        created_by=created_by,
        page_care_available=False,
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
    return _formula_out(f, created_by, ctx.can(Perm.SCORE_FORMULA_EDIT))


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
    db: AsyncSession, ctx: AuthContext, weights: Weights, *, now: dt.datetime | None = None
) -> PreviewOut:
    """Điểm tuần hiện tại với công thức đang dùng và với trọng số mới (cùng hàm với job)."""
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
        db, ctx.workspace_id, period, params.with_weights(weights.model_dump()), now
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
    db: AsyncSession, ctx: AuthContext, weights: Weights, *, now: dt.datetime | None = None
) -> FormulaOut:
    """Thêm phiên bản công thức mới, áp dụng ngay cho kỳ chưa chốt rồi tính lại."""
    now = now or dt.datetime.now(dt.UTC)
    old = await current_formula(db, ctx.workspace_id)
    new = ScoreFormula(
        workspace_id=ctx.workspace_id,
        version=old.version + 1,
        speed_full_minutes=old.speed_full_minutes,
        speed_zero_minutes=old.speed_zero_minutes,
        tier_a=old.tier_a,
        tier_b=old.tier_b,
        tier_c=old.tier_c,
        min_leads=old.min_leads,
        posts_per_week_target=old.posts_per_week_target,
        effective_from=now,
        created_by_member_id=ctx.member_id,
        **{f"w_{c}": v for c, v in weights.model_dump().items()},
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
        before={"version": old.version, **{c: getattr(old, f"w_{c}") for c in CRITERIA}},
        after={"version": new.version, **weights.model_dump()},
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


async def _latest_start(db: AsyncSession, period_type: PeriodType) -> dt.date | None:
    result: dt.date | None = await db.scalar(
        select(func.max(ScoreSnapshot.period_start)).where(ScoreSnapshot.period_type == period_type)
    )
    return result


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


async def _overdue_counts(
    db: AsyncSession, start: dt.datetime, end: dt.datetime, now: dt.datetime
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Lead.owner_member_id, func.count())
        .where(
            Lead.owner_member_id.is_not(None),
            Lead.merged_into_lead_id.is_(None),
            Lead.first_inbound_at >= start,
            Lead.first_inbound_at < end,
            Lead.result_at.is_(None),
            Lead.result_due_at < now,
        )
        .group_by(Lead.owner_member_id)
    )
    return {owner: int(n) for owner, n in rows.all() if owner is not None}


def _period_info(period_type: PeriodType, rows: list[ScoreSnapshot]) -> PeriodInfo:
    if not rows:
        return PeriodInfo(
            type=period_type, first_day=None, last_day=None, computed_at=None, is_final=False
        )
    first = rows[0]
    return PeriodInfo(
        type=period_type,
        first_day=first.period_start,
        last_day=first.period_end,
        computed_at=max(r.computed_at for r in rows),
        is_final=all(r.is_final for r in rows),
    )


async def _previous_week_totals(
    db: AsyncSession, first_day: dt.date
) -> dict[uuid.UUID, Decimal | None]:
    rows = await db.execute(
        select(ScoreSnapshot.member_id, ScoreSnapshot.total).where(
            ScoreSnapshot.period_type == PeriodType.WEEK,
            ScoreSnapshot.period_start == first_day - dt.timedelta(days=7),
        )
    )
    return {mid: total for mid, total in rows.all()}


# ---------------------------------------------------------------- bảng xếp hạng


async def leaderboard(
    db: AsyncSession, ctx: AuthContext, period_type: PeriodType, *, now: dt.datetime | None = None
) -> Leaderboard:
    now = now or dt.datetime.now(dt.UTC)
    scope = ctx.scope(Perm.LEADERBOARD_VIEW)
    formula = await current_formula(db, ctx.workspace_id)
    start_day = await _latest_start(db, period_type)
    snapshots: list[ScoreSnapshot] = []
    if start_day is not None:
        snapshots = list(
            await db.scalars(
                select(ScoreSnapshot).where(
                    ScoreSnapshot.period_type == period_type,
                    ScoreSnapshot.period_start == start_day,
                )
            )
        )
    info = _period_info(period_type, snapshots)
    members = await _members_info(db, ctx.workspace_id)
    pages = await _current_pages(db)
    deltas: dict[uuid.UUID, Decimal | None] = {}
    if period_type == PeriodType.WEEK and info.first_day:
        deltas = await _previous_week_totals(db, info.first_day)
    overdue: dict[uuid.UUID, int] = {}
    if info.first_day and info.last_day:
        rules = await inbound.load_rules(db, ctx.workspace_id)
        start, end = Period(period_type, info.first_day, info.last_day).utc_range(rules.tz)
        overdue = await _overdue_counts(db, start, end, now)

    visible = await member_ids_for(db, ctx, scope)
    full_view = scope in (Scope.ALL, Scope.TEAM)
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    staff_sees_top = bool(settings and settings.staff_can_see_leaderboard)

    rows: list[LeaderboardRow] = []
    for snap in snapshots:
        mid = snap.member_id
        is_self = mid == ctx.member_id
        in_scope = visible is None or mid in visible
        top_only = (
            not in_scope
            and scope == Scope.OWN
            and staff_sees_top
            and snap.rank is not None
            and snap.rank <= TOP_FOR_STAFF
        )
        if not in_scope and not top_only:
            continue
        info_m = members.get(mid, {})
        show = in_scope
        delta = None
        if show and snap.total is not None and deltas.get(mid) is not None:
            delta = snap.total - deltas[mid]  # type: ignore[operator]
        rows.append(
            LeaderboardRow(
                member=NamedRef(id=mid, name=info_m.get("name", "")),
                team=NamedRef(id=info_m["team_id"], name=info_m["team_name"])
                if info_m.get("team_id")
                else None,
                pages=[p.name for p in pages.get(mid, [])],
                is_self=is_self,
                rank=snap.rank,
                tier=snap.tier,
                insufficient_data=snap.insufficient_data,
                total=snap.total if show else None,
                delta=delta,
                lead_count=snap.lead_count if show else None,
                median_response_seconds=snap.median_response_seconds if show else None,
                phone_rate=snap.phone_rate if show else None,
                close_rate=snap.close_rate if show else None,
                revenue_vnd=snap.revenue_vnd if show else None,
                overdue_count=overdue.get(mid, 0) if show else None,
            )
        )
    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.member.name))

    tiers = kpis = insufficient = None
    teams: list[NamedRef] = []
    if full_view:
        in_view = [s for s in snapshots if visible is None or s.member_id in visible]
        tiers = {t: sum(1 for s in in_view if s.tier == t) for t in Tier}
        insufficient = sum(1 for s in in_view if s.insufficient_data)
        kpis = await _kpis(db, ctx, info, in_view, overdue, now)
        team_ids = {
            members[s.member_id]["team_id"]
            for s in in_view
            if members.get(s.member_id, {}).get("team_id")
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
        full_view=full_view,
    )


async def _kpis(
    db: AsyncSession,
    ctx: AuthContext,
    info: PeriodInfo,
    snapshots: list[ScoreSnapshot],
    overdue: dict[uuid.UUID, int],
    now: dt.datetime,
) -> Kpis:
    member_ids = {s.member_id for s in snapshots}
    lead_count = sum(s.lead_count for s in snapshots)
    won = sum(s.won_count for s in snapshots)
    phones = sum(s.phone_count for s in snapshots)
    median: int | None = None
    if info.first_day and info.last_day and member_ids:
        # Cùng cách lấy mẫu với điểm tốc độ, để thẻ chỉ số khớp với từng hàng.
        rules = await inbound.load_rules(db, ctx.workspace_id)
        params = FormulaParams.from_model(await current_formula(db, ctx.workspace_id))
        start, end = Period(info.type, info.first_day, info.last_day).utc_range(rules.tz)
        facts = await lead_facts(db, rules, start, end, min(now, end))
        samples = speed_samples((x for x in facts if x.owner_id in member_ids), params)
        median = int(statistics.median(samples)) if samples else None
    return Kpis(
        lead_count=lead_count,
        median_response_seconds=median,
        phone_rate=_rate(phones, lead_count),
        close_rate=_rate(won, lead_count),
        revenue_vnd=sum(s.revenue_vnd for s in snapshots),
        overdue_count=sum(overdue.get(m, 0) for m in member_ids),
    )


# ---------------------------------------------------------------- hồ sơ nhân viên


def _parts(snap: ScoreSnapshot | None, formula: ScoreFormula) -> list[ScorePart]:
    weights = {c: int(getattr(formula, f"w_{c}")) for c in CRITERIA}
    scores: dict[str, Decimal | None] = {
        c: getattr(snap, f"s_{c}") if snap else None for c in CRITERIA
    }
    used = sum(w for c, w in weights.items() if scores[c] is not None and w > 0)
    raw: dict[str, dict[str, int | Decimal | None]] = {
        "close_rate": {
            "rate": snap.close_rate if snap else None,
            "won": snap.won_count if snap else None,
        },
        "response_speed": {"median_seconds": snap.median_response_seconds if snap else None},
        "revenue": {"revenue_vnd": snap.revenue_vnd if snap else None},
        "phone_rate": {
            "rate": snap.phone_rate if snap else None,
            "phones": snap.phone_count if snap else None,
        },
        "page_care": {
            "posts": snap.posts_count if snap else None,
            "target": formula.posts_per_week_target,
        },
        "on_time": {"rate": snap.on_time_rate if snap else None},
    }
    parts = []
    for c in CRITERIA:
        score = scores[c]
        effective = None
        points = None
        if score is not None and used and weights[c] > 0:
            effective = (Decimal(weights[c]) * 100 / Decimal(used)).quantize(Decimal("0.01"))
            points = (score * Decimal(weights[c]) / Decimal(used)).quantize(Decimal("0.01"))
        parts.append(
            ScorePart(
                key=c,
                weight=weights[c],
                effective_weight=effective,
                score=score,
                points=points,
                raw=raw[c],
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
    start_day = await _latest_start(db, period_type)
    snap = None
    ranked_count = 0
    if start_day is not None:
        snap = await db.scalar(
            select(ScoreSnapshot).where(
                ScoreSnapshot.period_type == period_type,
                ScoreSnapshot.period_start == start_day,
                ScoreSnapshot.member_id == member_id,
            )
        )
        ranked_count = int(
            await db.scalar(
                select(func.count()).where(
                    ScoreSnapshot.period_type == period_type,
                    ScoreSnapshot.period_start == start_day,
                    ScoreSnapshot.rank.is_not(None),
                )
            )
            or 0
        )
    formula = (
        await db.get(ScoreFormula, snap.formula_id)
        if snap
        else await current_formula(db, ctx.workspace_id)
    )
    assert formula is not None  # noqa: S101 — khóa ngoại bảo đảm
    period = (
        Period(period_type, snap.period_start, snap.period_end)
        if snap
        else period_for(period_type, now, rules.tz)
    )
    start, end = period.utc_range(rules.tz)

    delta = None
    if snap and snap.total is not None and period_type == PeriodType.WEEK:
        prev = await db.scalar(
            select(ScoreSnapshot.total).where(
                ScoreSnapshot.period_type == PeriodType.WEEK,
                ScoreSnapshot.member_id == member_id,
                ScoreSnapshot.period_start == snap.period_start - dt.timedelta(days=7),
            )
        )
        delta = snap.total - prev if prev is not None else None

    funnel = await _funnel(db, member_id, start, end)
    hours = await _hours(db, member_id, start, end, rules.tz)
    trend_rows = (
        await db.scalars(
            select(ScoreSnapshot)
            .where(
                ScoreSnapshot.period_type == PeriodType.WEEK, ScoreSnapshot.member_id == member_id
            )
            .order_by(ScoreSnapshot.period_start.desc())
            .limit(TREND_WEEKS)
        )
    ).all()
    recent = await _recent_leads(db, member_id, now)
    pages = (await _current_pages(db)).get(member_id, [])
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    return StaffDetail(
        member=NamedRef(id=member_id, name=me["name"]),
        role=me["role"],
        team=NamedRef(id=me["team_id"], name=me["team_name"]) if me["team_id"] else None,
        team_lead=team_lead,
        pages=pages,
        period=_period_info(period_type, [snap] if snap else []),
        total=snap.total if snap else None,
        tier=snap.tier if snap else None,
        rank=snap.rank if snap else None,
        ranked_count=ranked_count,
        delta=delta,
        insufficient_data=snap.insufficient_data if snap else True,
        min_leads=formula.min_leads,
        lead_count=snap.lead_count if snap else funnel[0].value,
        parts=_parts(snap, formula),
        funnel=funnel,
        hours=hours,
        trend=[
            TrendPoint(first_day=r.period_start, total=r.total, tier=r.tier)
            for r in reversed(trend_rows)
        ],
        recent=recent,
        slow_reply_minutes=settings.slow_reply_minutes if settings else 30,
    )


def _funnel_counts(leads: list[Lead]) -> dict[str, int]:
    return {
        "leads": len(leads),
        "replied": sum(1 for x in leads if x.first_reply_at is not None),
        "phone": sum(1 for x in leads if x.phone is not None),
        "called": sum(1 for x in leads if x.called_at is not None),
        "won": sum(1 for x in leads if x.status.value == "won"),
    }


async def _funnel(
    db: AsyncSession, member_id: uuid.UUID, start: dt.datetime, end: dt.datetime
) -> list[FunnelStep]:
    base = select(Lead).where(
        Lead.owner_member_id.is_not(None),
        Lead.merged_into_lead_id.is_(None),
        Lead.first_inbound_at >= start,
        Lead.first_inbound_at < end,
    )
    all_leads = list(await db.scalars(base))
    mine = _funnel_counts([x for x in all_leads if x.owner_member_id == member_id])
    company = _funnel_counts(all_leads)

    def denominator(key: str, counts: dict[str, int]) -> int:
        # "Đã gọi" tính trên số khách có SĐT (theo thiết kế), còn lại trên số khách nhận.
        return counts["phone"] if key == "called" else counts["leads"]

    return [
        FunnelStep(
            key=key,
            value=mine[key],
            rate=None if key == "leads" else _rate(mine[key], denominator(key, mine)),
            company_rate=None if key == "leads" else _rate(company[key], denominator(key, company)),
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
