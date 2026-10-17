"""Nguồn tính số liệu duy nhất (decisions.md mục J, định nghĩa ở docs/metrics.md).

Tổng quan, Fanpage, Nhân viên, Hồ sơ nhân viên, điểm và cảnh báo đều lấy tập khách của kỳ qua
`load_facts`, rồi tính bằng `summarize`. Chỉ khác cách nhóm (theo Trang, theo người, tổng), nên
cùng kỳ và cùng phạm vi thì các con số luôn cộng khớp với nhau.
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, LeadSource, LeadStatus
from app.services.inbound import WorkspaceRules
from app.services.scoring import FormulaParams, LeadFacts, speed_samples

_FINAL = (LeadStatus.WON, LeadStatus.LOST, LeadStatus.CALLBACK)


async def load_facts(
    db: AsyncSession,
    rules: WorkspaceRules,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
) -> list[LeadFacts]:
    """Khách của kỳ: đợt có tin đầu tiên trong [start, end), bỏ đợt form đã gộp.

    Gồm cả khách chưa có người phụ trách (`owner_id` None). `now` dùng để tính thời gian khách
    chưa được trả lời đã chờ (trong giờ làm việc).
    """
    rows = await db.execute(
        select(
            Lead.page_id,
            Lead.owner_member_id,
            Lead.source,
            Lead.status,
            Lead.first_inbound_at,
            Lead.first_reply_at,
            Lead.response_business_seconds,
            Lead.phone,
            Lead.called_at,
            Lead.won_value_vnd,
            Lead.result_at,
            Lead.result_due_at,
            Lead.campaign_id,
        ).where(
            Lead.merged_into_lead_id.is_(None),
            Lead.first_inbound_at >= start,
            Lead.first_inbound_at < end,
        )
    )
    facts = []
    for r in rows.all():
        waiting = None
        if r.source == LeadSource.MESSAGE and r.first_reply_at is None:
            waiting = rules.business_seconds(r.first_inbound_at, now)
        facts.append(
            LeadFacts(
                owner_id=r.owner_member_id,
                source=r.source,
                status=r.status,
                response_seconds=r.response_business_seconds,
                waiting_seconds=waiting,
                has_phone=r.phone is not None,
                won_value_vnd=r.won_value_vnd,
                result_at=r.result_at,
                result_due_at=r.result_due_at,
                page_id=r.page_id,
                first_inbound_at=r.first_inbound_at,
                replied=r.first_reply_at is not None
                or r.called_at is not None
                or r.status != LeadStatus.NEW,
                called=r.called_at is not None,
                campaign_id=r.campaign_id,
            )
        )
    return facts


def in_scope(facts: Iterable[LeadFacts], owner_ids: set[uuid.UUID] | None) -> list[LeadFacts]:
    """None = toàn workspace, kể cả khách chưa có người phụ trách. Tập = chỉ khách của những người
    này (lọc theo người phụ trách của khách, không theo người đang phụ trách Trang)."""
    if owner_ids is None:
        return list(facts)
    return [f for f in facts if f.owner_id is not None and f.owner_id in owner_ids]


def group[K: Hashable](
    facts: Iterable[LeadFacts], key: Callable[[LeadFacts], K]
) -> dict[K, list[LeadFacts]]:
    out: dict[K, list[LeadFacts]] = defaultdict(list)
    for f in facts:
        out[key(f)].append(f)
    return out


def rate(part: int, whole: int) -> Decimal | None:
    if whole <= 0:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Summary:
    """Chỉ số của một tập khách. Phễu lồng nhau, kết quả tách riêng (docs/metrics.md)."""

    leads: int
    replied: int
    phone: int  # phễu: đã trả lời và có SĐT
    called: int  # phễu: có SĐT (phễu) và đã gọi
    won: int
    lost: int
    callback: int
    pending: int
    phones_all: int  # mọi khách có SĐT (ô chỉ số, tiêu chí điểm)
    revenue_vnd: int
    overdue: int  # khách của kỳ đã quá hạn 48 giờ
    median_response_seconds: int | None
    won_from_ads: int

    @property
    def unreplied(self) -> int:
        return self.leads - self.replied

    @property
    def no_phone(self) -> int:
        return self.replied - self.phone

    @property
    def not_called(self) -> int:
        return self.phone - self.called

    @property
    def phone_rate(self) -> Decimal | None:
        return rate(self.phones_all, self.leads)

    @property
    def close_rate(self) -> Decimal | None:
        return rate(self.won, self.leads)


def summarize(facts: Iterable[LeadFacts], now: dt.datetime, params: FormulaParams) -> Summary:
    items = list(facts)
    won = [f for f in items if f.status == LeadStatus.WON]
    phone = [f for f in items if f.replied and f.has_phone]
    samples = speed_samples(items, params)
    return Summary(
        leads=len(items),
        replied=sum(1 for f in items if f.replied),
        phone=len(phone),
        called=sum(1 for f in phone if f.called),
        won=len(won),
        lost=sum(1 for f in items if f.status == LeadStatus.LOST),
        callback=sum(1 for f in items if f.status == LeadStatus.CALLBACK),
        pending=sum(1 for f in items if f.status not in _FINAL),
        phones_all=sum(1 for f in items if f.has_phone),
        revenue_vnd=sum(f.won_value_vnd or 0 for f in won),
        overdue=sum(1 for f in items if f.result_at is None and f.result_due_at < now),
        median_response_seconds=int(statistics.median(samples)) if samples else None,
        won_from_ads=sum(1 for f in won if f.campaign_id is not None),
    )
