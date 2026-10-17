"""Tính điểm từ dữ liệu trong DB và lưu `score_snapshots`.

Chạy trong một transaction đã đặt `app.workspace_id`. Job ban đêm, nút "Tính lại ngay" và "xem
thử" đều đi qua `compute_period`, nên cùng dữ liệu và cùng công thức thì ra cùng một điểm.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Lead,
    LeadSource,
    PageAssignment,
    PeriodType,
    ScoreFormula,
    ScoreSnapshot,
)
from app.services import inbound
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


async def _lead_facts(
    db: AsyncSession,
    rules: inbound.WorkspaceRules,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
) -> list[LeadFacts]:
    leads = await db.scalars(
        select(Lead).where(
            Lead.owner_member_id.is_not(None),
            Lead.merged_into_lead_id.is_(None),
            Lead.first_inbound_at >= start,
            Lead.first_inbound_at < end,
        )
    )
    facts = []
    for lead in leads:
        assert lead.owner_member_id is not None  # noqa: S101 — đã lọc ở trên
        waiting = None
        if lead.source == LeadSource.MESSAGE and lead.first_reply_at is None:
            waiting = rules.business_seconds(lead.first_inbound_at, now)
        facts.append(
            LeadFacts(
                owner_id=lead.owner_member_id,
                source=lead.source,
                status=lead.status,
                response_seconds=lead.response_business_seconds,
                waiting_seconds=waiting,
                has_phone=lead.phone is not None,
                won_value_vnd=lead.won_value_vnd,
                result_at=lead.result_at,
                result_due_at=lead.result_due_at,
            )
        )
    return facts


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
    facts = await _lead_facts(db, rules, start, end, min(now, end))
    by_owner: dict[uuid.UUID, list[LeadFacts]] = defaultdict(list)
    for fact in facts:
        by_owner[fact.owner_id].append(fact)
    members = set(by_owner) | await _assigned_members(db, start, end)
    metrics = [member_metrics(m, by_owner.get(m, []), min(now, end), params) for m in members]
    return compute_scores(metrics, params)


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
