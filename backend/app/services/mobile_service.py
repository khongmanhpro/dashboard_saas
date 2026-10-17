"""Dữ liệu cho ứng dụng điện thoại (/m): chỉ khách của chính người đăng nhập (quyết định Bước 5)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    Page,
    PageAssignment,
    PeriodType,
    ScoreSnapshot,
    Tier,
    User,
    WorkspaceMember,
)
from app.schemas.mobile import MobileHome, MobileLead, MobileScore, MobileStats, MobileTab
from app.services import lead_service
from app.services.notify_service import unread_count
from app.services.score_service import current_formula

if TYPE_CHECKING:
    from app.api.deps import AuthContext

DONE_WINDOW = dt.timedelta(days=7)
MAX_ITEMS = 100
_OPEN = (LeadStatus.NEW, LeadStatus.CONTACTED)


def _tab_condition(tab: MobileTab, now: dt.datetime) -> Any:
    if tab == "todo":
        return Lead.status.in_(_OPEN)
    if tab == "callback":
        return Lead.status == LeadStatus.CALLBACK
    return Lead.status.in_((LeadStatus.WON, LeadStatus.LOST)) & (
        Lead.status_changed_at >= now - DONE_WINDOW
    )


def _own(ctx: AuthContext) -> list[Any]:
    return [Lead.owner_member_id == ctx.member_id, Lead.merged_into_lead_id.is_(None)]


def _urgency(item: MobileLead) -> tuple[int, float]:
    """Cần xử lý: quá hạn → chưa trả lời → có SĐT chưa gọi → còn lại."""
    if item.overdue:
        return 0, item.result_due_at.timestamp()
    if item.waiting_business_seconds is not None:
        return 1, item.first_inbound_at.timestamp()
    if item.phone and item.called_at is None:
        return 2, (item.phone_captured_at or item.first_inbound_at).timestamp()
    return 3, -item.first_inbound_at.timestamp()


async def mobile_leads(
    db: AsyncSession, ctx: AuthContext, tab: MobileTab, *, now: dt.datetime | None = None
) -> list[MobileLead]:
    now = now or dt.datetime.now(dt.UTC)
    access = await lead_service.lead_access(db, ctx)
    rules = await lead_service._rules(db, ctx.workspace_id)
    order = Lead.callback_at.asc() if tab == "callback" else Lead.first_inbound_at.desc()
    rows = (
        await db.execute(
            lead_service._base_select()
            .where(*_own(ctx), _tab_condition(tab, now))
            .order_by(order)
            .limit(MAX_ITEMS)
        )
    ).all()
    lead_ids = [r.Lead.id for r in rows]
    snippets: dict[uuid.UUID, str | None] = {}
    if lead_ids:
        newest = (
            select(Message.lead_id, func.max(Message.sent_at).label("sent_at"))
            .where(Message.lead_id.in_(lead_ids), Message.direction == MessageDirection.IN)
            .group_by(Message.lead_id)
            .subquery()
        )
        latest = select(Message.lead_id, Message.text, Message.has_attachments).join(
            newest,
            (Message.lead_id == newest.c.lead_id) & (Message.sent_at == newest.c.sent_at),
        )
        for lead_id, text, has_attachments in (await db.execute(latest)).all():
            if lead_id is None:
                continue
            snippets[lead_id] = text if text else (None if not has_attachments else "")
    items = []
    for row in rows:
        card = lead_service._card(row, access, rules, now)
        items.append(
            MobileLead(
                **card.model_dump(),
                fb_page_id=row.fb_page_id,
                snippet=snippets.get(row.Lead.id),
                phone_captured_at=row.Lead.phone_captured_at,
            )
        )
    if tab == "todo":
        items.sort(key=_urgency)
    return items


def _next_tier(total: Decimal, thresholds: dict[Tier, int]) -> tuple[Tier | None, Decimal | None]:
    order = [Tier.D, Tier.C, Tier.B, Tier.A]
    for tier in order[1:]:
        need = Decimal(thresholds[tier])
        if total < need:
            return tier, (need - total).quantize(Decimal("0.01"))
    return None, None


async def _snapshot(
    db: AsyncSession, member_id: uuid.UUID, period_type: PeriodType
) -> ScoreSnapshot | None:
    start = await db.scalar(
        select(func.max(ScoreSnapshot.period_start)).where(ScoreSnapshot.period_type == period_type)
    )
    if start is None:
        return None
    return await db.scalar(
        select(ScoreSnapshot).where(
            ScoreSnapshot.period_type == period_type,
            ScoreSnapshot.period_start == start,
            ScoreSnapshot.member_id == member_id,
        )
    )


async def home(db: AsyncSession, ctx: AuthContext, *, now: dt.datetime | None = None) -> MobileHome:
    now = now or dt.datetime.now(dt.UTC)
    full_name = await db.scalar(
        select(User.full_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.id == ctx.member_id)
    )
    first_name = (full_name or "").replace("[", "").replace("]", "").split()[-1:] or [""]
    pages = (
        await db.scalars(
            select(Page.name)
            .join(PageAssignment, PageAssignment.page_id == Page.id)
            .where(PageAssignment.member_id == ctx.member_id, PageAssignment.valid_to.is_(None))
            .order_by(Page.name)
        )
    ).all()

    formula = await current_formula(db, ctx.workspace_id)
    week = await _snapshot(db, ctx.member_id, PeriodType.WEEK)
    score = None
    if week is not None:
        ranked = int(
            await db.scalar(
                select(func.count()).where(
                    ScoreSnapshot.period_type == PeriodType.WEEK,
                    ScoreSnapshot.period_start == week.period_start,
                    ScoreSnapshot.rank.is_not(None),
                )
            )
            or 0
        )
        previous_rank = await db.scalar(
            select(ScoreSnapshot.rank).where(
                ScoreSnapshot.period_type == PeriodType.WEEK,
                ScoreSnapshot.member_id == ctx.member_id,
                ScoreSnapshot.period_start == week.period_start - dt.timedelta(days=7),
            )
        )
        next_tier, gap = (None, None)
        if week.total is not None:
            next_tier, gap = _next_tier(
                week.total, {Tier.A: formula.tier_a, Tier.B: formula.tier_b, Tier.C: formula.tier_c}
            )
        score = MobileScore(
            total=week.total,
            tier=week.tier,
            rank=week.rank,
            ranked_count=ranked,
            rank_change=(previous_rank - week.rank)
            if previous_rank is not None and week.rank is not None
            else None,
            next_tier=next_tier,
            points_to_next=gap,
            insufficient_data=week.insufficient_data,
            lead_count=week.lead_count,
            min_leads=formula.min_leads,
        )
    rolling = await _snapshot(db, ctx.member_id, PeriodType.ROLLING_7)
    stats = (
        MobileStats(
            median_response_seconds=rolling.median_response_seconds,
            phone_rate=rolling.phone_rate,
            close_rate=rolling.close_rate,
        )
        if rolling
        else None
    )
    phone_not_called = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                *_own(ctx),
                Lead.phone.is_not(None),
                Lead.called_at.is_(None),
                Lead.status.not_in((LeadStatus.WON, LeadStatus.LOST)),
            )
        )
        or 0
    )
    tabs: dict[MobileTab, int] = {}
    for tab in ("todo", "callback", "done"):
        tabs[tab] = int(
            await db.scalar(
                select(func.count()).select_from(Lead).where(*_own(ctx), _tab_condition(tab, now))
            )
            or 0
        )
    return MobileHome(
        first_name=first_name[0],
        pages=list(pages),
        score=score,
        stats=stats,
        phone_not_called=phone_not_called,
        tabs=tabs,
        unread=await unread_count(db, ctx.member_id),
    )
