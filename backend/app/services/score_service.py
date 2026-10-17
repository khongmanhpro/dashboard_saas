"""Tính điểm từ dữ liệu trong DB và lưu `score_snapshots`.

Chạy trong một transaction đã đặt `app.workspace_id`. Job ban đêm, nút "Tính lại ngay" và "xem
thử" đều đi qua `compute_period`, nên cùng dữ liệu và cùng công thức thì ra cùng một điểm.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Page,
    PageAssignment,
    PagePost,
    PeriodType,
    ScoreFormula,
    ScoreSnapshot,
)
from app.services import inbound, metrics
from app.services.errors import ServiceError
from app.services.periods import Period, period_for, previous_week
from app.services.scoring import (
    FormulaParams,
    LeadFacts,
    MemberScore,
    compute_scores,
    member_metrics,
)


async def current_formula(db: AsyncSession, workspace_id: uuid.UUID) -> ScoreFormula:
    formula = await db.scalar(
        select(ScoreFormula)
        .where(ScoreFormula.workspace_id == workspace_id)
        .order_by(ScoreFormula.version.desc())
        .limit(1)
    )
    if formula is None:
        raise ServiceError("score_formula_missing", 500)
    return formula


async def lead_facts(
    db: AsyncSession,
    rules: inbound.WorkspaceRules,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
) -> list[LeadFacts]:
    """Khách có người phụ trách của kỳ (cùng tập với `metrics.load_facts`)."""
    facts = await metrics.load_facts(db, rules, start, end, now)
    return [f for f in facts if f.owner_id is not None]


async def _assigned_members(
    db: AsyncSession, start: dt.datetime, end: dt.datetime
) -> set[uuid.UUID]:
    """Người phụ trách Trang ở bất kỳ lúc nào trong kỳ."""
    rows = await db.scalars(
        select(PageAssignment.member_id).where(
            PageAssignment.valid_from < end,
            or_(PageAssignment.valid_to.is_(None), PageAssignment.valid_to > start),
        )
    )
    return set(rows.all())


async def posts_by_member(
    db: AsyncSession, start: dt.datetime, end: dt.datetime
) -> dict[uuid.UUID, int]:
    """Số bài trên Trang mỗi người phụ trách, chỉ tính lúc họ đang phụ trách (mục I).

    Người chỉ phụ trách Trang chưa đồng bộ được bài đăng thì không có trong kết quả."""
    lower = func.greatest(PageAssignment.valid_from, start)
    upper = func.least(func.coalesce(PageAssignment.valid_to, end), end)
    rows = await db.execute(
        select(PageAssignment.member_id, func.count(PagePost.id))
        .join(Page, Page.id == PageAssignment.page_id)
        .outerjoin(
            PagePost,
            and_(
                PagePost.page_id == PageAssignment.page_id,
                PagePost.created_time >= lower,
                PagePost.created_time < upper,
            ),
        )
        .where(
            Page.content_synced_at.is_not(None),
            PageAssignment.valid_from < end,
            or_(PageAssignment.valid_to.is_(None), PageAssignment.valid_to > start),
        )
        .group_by(PageAssignment.member_id)
    )
    return {member_id: int(count) for member_id, count in rows.all()}


@dataclass
class LivePeriod:
    """Điểm và tập khách của một kỳ, tính từ cùng một lần nạp dữ liệu (decisions.md mục J)."""

    period: Period
    params: FormulaParams
    scores: list[MemberScore]
    facts: list[LeadFacts]  # gồm cả khách chưa có người phụ trách
    start: dt.datetime
    until: dt.datetime


async def live_period(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    period: Period,
    now: dt.datetime,
    params: FormulaParams | None = None,
) -> LivePeriod:
    rules = await inbound.load_rules(db, workspace_id)
    if params is None:
        params = FormulaParams.from_model(await current_formula(db, workspace_id))
    start, end = period.utc_range(rules.tz)
    until = min(now, end)
    facts = await metrics.load_facts(db, rules, start, end, until)
    scores = await _scores(db, params, facts, start, until)
    return LivePeriod(period, params, scores, facts, start, until)


async def _scores(
    db: AsyncSession,
    params: FormulaParams,
    facts: list[LeadFacts],
    start: dt.datetime,
    until: dt.datetime,
) -> list[MemberScore]:
    by_owner: dict[uuid.UUID, list[LeadFacts]] = defaultdict(list)
    for fact in facts:
        if fact.owner_id is not None:
            by_owner[fact.owner_id].append(fact)
    members = set(by_owner) | await _assigned_members(db, start, until)
    posts = await posts_by_member(db, start, until)
    metric_rows = []
    for m in members:
        metric = member_metrics(m, by_owner.get(m, []), until, params)
        metric.posts_count = posts.get(m)
        metric_rows.append(metric)
    elapsed = Decimal(max((until - start).total_seconds(), 0)) / 86400
    return compute_scores(metric_rows, params, max(elapsed, Decimal(1)))


async def compute_period(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    period: Period,
    params: FormulaParams,
    now: dt.datetime,
    tz: ZoneInfo | None = None,
) -> list[MemberScore]:
    rules = await inbound.load_rules(db, workspace_id)
    start, end = period.utc_range(tz or rules.tz)
    until = min(now, end)
    facts = await metrics.load_facts(db, rules, start, end, until)
    return await _scores(db, params, facts, start, until)


async def save_period(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    period: Period,
    formula: ScoreFormula,
    scores: list[MemberScore],
    now: dt.datetime,
    *,
    final: bool,
) -> int:
    """Ghi điểm của kỳ. Dòng đã chốt (`is_final`) giữ nguyên. Trả về số dòng đã ghi."""
    existing = {
        s.member_id: s
        for s in await db.scalars(
            select(ScoreSnapshot)
            .where(
                ScoreSnapshot.period_type == period.type,
                ScoreSnapshot.period_start == period.first_day,
            )
            .with_for_update()
        )
    }
    written = 0
    for score in scores:
        row = existing.get(score.metrics.member_id)
        if row is not None and row.is_final:
            continue
        if row is None:
            row = ScoreSnapshot(
                workspace_id=workspace_id,
                member_id=score.metrics.member_id,
                period_type=period.type,
                period_start=period.first_day,
            )
            db.add(row)
        m = score.metrics
        c = score.components
        row.formula_id = formula.id
        row.period_end = period.last_day
        row.computed_at = now
        row.lead_count = m.lead_count
        row.won_count = m.won_count
        row.phone_count = m.phone_count
        row.close_rate = m.close_rate
        row.median_response_seconds = m.median_response_seconds
        row.revenue_vnd = m.revenue_vnd
        row.phone_rate = m.phone_rate
        row.posts_count = m.posts_count
        row.on_time_rate = m.on_time_rate
        row.s_close_rate = c.get("close_rate")
        row.s_response_speed = c.get("response_speed")
        row.s_revenue = c.get("revenue")
        row.s_phone_rate = c.get("phone_rate")
        row.s_page_care = c.get("page_care")
        row.s_on_time = c.get("on_time")
        row.total = score.total
        row.tier = score.tier
        row.rank = score.rank
        row.insufficient_data = score.insufficient_data
        row.is_final = final
        written += 1
    await db.flush()
    return written


async def recompute_workspace(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    now: dt.datetime,
    *,
    finalize_previous_week: bool = True,
) -> dict[str, int]:
    """Tính lại tuần hiện tại và các kỳ tham khảo; chốt tuần trước nếu chưa chốt."""
    formula = await current_formula(db, workspace_id)
    params = FormulaParams.from_model(formula)
    rules = await inbound.load_rules(db, workspace_id)
    counts: dict[str, int] = {}
    for period_type in PeriodType:
        period = period_for(period_type, now, rules.tz)
        scores = await compute_period(db, workspace_id, period, params, now)
        counts[period_type.value] = await save_period(
            db, workspace_id, period, formula, scores, now, final=False
        )
    if finalize_previous_week:
        last_week = previous_week(now, rules.tz)
        open_rows = await db.scalar(
            select(ScoreSnapshot.id)
            .where(
                ScoreSnapshot.period_type == PeriodType.WEEK,
                ScoreSnapshot.period_start == last_week.first_day,
                ScoreSnapshot.is_final.is_(True),
            )
            .limit(1)
        )
        if open_rows is None:
            scores = await compute_period(db, workspace_id, last_week, params, now)
            counts["finalized_week"] = await save_period(
                db, workspace_id, last_week, formula, scores, now, final=True
            )
    return counts
