"""Số liệu quảng cáo cho màn Quảng cáo, Tổng quan và cảnh báo (Bước 7, decisions.md mục I).

- Chi tiêu cộng từ `ad_insights_daily` theo ngày (múi giờ tài khoản QC), quy VND qua `spend_vnd`.
- Khách / khách chốt: tập khách có tin đầu tiên trong kỳ, gắn với QC qua `leads.ad_id`.
- Chi phí mỗi khách = chi tiêu chiến dịch trong ngày ÷ khách mới của chiến dịch trong ngày.
- Chi phí mỗi khách chốt = chi tiêu trong kỳ ÷ khách chốt.
- Tần suất nhiều ngày là ước tính (lượt hiển thị ÷ tổng tiếp cận theo ngày).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Ad,
    AdAccount,
    AdInsightDaily,
    AdSet,
    Campaign,
    Lead,
    LeadStatus,
)
from app.schemas.reports import (
    AdAccountRef,
    AdsKpis,
    AdsReport,
    AdsRow,
    CostBar,
    Metric,
    RangeOut,
)
from app.services.report_range import DateRange

Level = Literal["campaign", "adset", "ad"]


def owner_condition(owner_ids: set[uuid.UUID] | None) -> ColumnElement[bool]:
    """None = mọi người, kể cả khách chưa có người phụ trách. Tập rỗng = không ai."""
    if owner_ids is None:
        return true()
    if not owner_ids:
        return false()
    return Lead.owner_member_id.in_(owner_ids)


def cohort(r: DateRange, owner_ids: set[uuid.UUID] | None) -> list[ColumnElement[bool]]:
    """Tập khách của kỳ: tin đầu tiên trong kỳ, bỏ đợt form đã gộp (như mục F)."""
    return [
        Lead.first_inbound_at >= r.start,
        Lead.first_inbound_at < r.end,
        Lead.merged_into_lead_id.is_(None),
        owner_condition(owner_ids),
    ]


def ratio(part: int | Decimal | None, whole: int | Decimal | None) -> Decimal | None:
    if part is None or not whole:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def money_ratio(spend: int | None, count: int) -> int | None:
    if spend is None or count <= 0:
        return None
    return int((Decimal(spend) / count).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class Stat:
    """Số liệu một đối tượng QC trong kỳ."""

    object_id: uuid.UUID
    spend_vnd: int | None = 0
    missing_fx: bool = False
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    results: int | None = None
    leads: int = 0
    won: int = 0
    revenue_vnd: int = 0

    @property
    def cost_per_result(self) -> int | None:
        return money_ratio(self.spend_vnd, self.results or 0)

    @property
    def cost_per_lead(self) -> int | None:
        return money_ratio(self.spend_vnd, self.leads)

    @property
    def cost_per_won(self) -> int | None:
        return money_ratio(self.spend_vnd, self.won)

    @property
    def ctr(self) -> Decimal | None:
        return ratio(self.clicks, self.impressions)

    @property
    def cpm(self) -> int | None:
        if self.spend_vnd is None or not self.impressions:
            return None
        value = Decimal(self.spend_vnd) * 1000 / self.impressions
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def frequency(self) -> Decimal | None:
        if not self.reach:
            return None
        return (Decimal(self.impressions) / self.reach).quantize(Decimal("0.01"))


_LEAD_KEY = {"campaign": Lead.campaign_id, "ad": Lead.ad_id}


async def level_stats(
    db: AsyncSession,
    level: Level,
    r: DateRange,
    *,
    owner_ids: set[uuid.UUID] | None = None,
    account_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, Stat]:
    """Số liệu theo đối tượng ở một cấp, kèm khách và khách chốt của hệ thống."""
    conds: list[ColumnElement[bool]] = [
        AdInsightDaily.level == level,
        AdInsightDaily.date >= r.first_day,
        AdInsightDaily.date <= r.last_day,
    ]
    if account_id is not None:
        conds.append(AdInsightDaily.ad_account_id == account_id)
    missing = func.bool_or(and_(AdInsightDaily.spend_vnd.is_(None), AdInsightDaily.spend_minor > 0))
    rows = await db.execute(
        select(
            AdInsightDaily.object_id,
            func.coalesce(func.sum(AdInsightDaily.spend_vnd), 0),
            missing,
            func.sum(AdInsightDaily.impressions),
            func.sum(AdInsightDaily.reach),
            func.sum(AdInsightDaily.clicks),
            func.sum(AdInsightDaily.results),
        )
        .where(*conds)
        .group_by(AdInsightDaily.object_id)
    )
    stats: dict[uuid.UUID, Stat] = {}
    for object_id, spend, miss, impressions, reach, clicks, results in rows.all():
        stats[object_id] = Stat(
            object_id=object_id,
            spend_vnd=None if miss else int(spend),
            missing_fx=bool(miss),
            impressions=int(impressions or 0),
            reach=int(reach or 0),
            clicks=int(clicks or 0),
            results=int(results) if results is not None else None,
        )

    key: Any = Ad.ad_set_id if level == "adset" else _LEAD_KEY[level]
    won = Lead.status == LeadStatus.WON
    query = select(
        key,
        func.count(),
        func.count().filter(won),
        func.coalesce(func.sum(Lead.won_value_vnd).filter(won), 0),
    ).select_from(Lead)
    if level == "adset":
        query = query.join(Ad, Ad.id == Lead.ad_id)
    if account_id is not None:
        query = query.join(Campaign, Campaign.id == Lead.campaign_id).where(
            Campaign.ad_account_id == account_id
        )
    lead_rows = await db.execute(query.where(*cohort(r, owner_ids), key.is_not(None)).group_by(key))
    for object_id, leads, won_count, revenue in lead_rows.all():
        stat = stats.setdefault(object_id, Stat(object_id=object_id))
        stat.leads, stat.won, stat.revenue_vnd = int(leads), int(won_count), int(revenue)
    return stats


def total(stats: dict[uuid.UUID, Stat]) -> Stat:
    out = Stat(object_id=uuid.UUID(int=0))
    results = [s.results for s in stats.values() if s.results is not None]
    out.results = sum(results) if results else None
    for s in stats.values():
        # Thiếu tỉ giá: cộng phần đã quy được VND, giao diện ghi rõ "chưa gồm" qua `missing_fx`.
        out.spend_vnd = (out.spend_vnd or 0) + (s.spend_vnd or 0)
        out.missing_fx = out.missing_fx or s.missing_fx
        out.impressions += s.impressions
        out.reach += s.reach
        out.clicks += s.clicks
        out.leads += s.leads
        out.won += s.won
        out.revenue_vnd += s.revenue_vnd
    return out


async def missing_fx_currencies(db: AsyncSession, r: DateRange) -> list[str]:
    rows = await db.scalars(
        select(AdInsightDaily.currency)
        .where(
            AdInsightDaily.date >= r.first_day,
            AdInsightDaily.date <= r.last_day,
            AdInsightDaily.spend_vnd.is_(None),
            AdInsightDaily.spend_minor > 0,
        )
        .distinct()
    )
    return sorted(rows.all())


async def lead_cost(db: AsyncSession, lead: Lead, tz_name: str) -> int | None:
    """Chi phí ước tính của một khách: chi tiêu chiến dịch trong ngày ÷ khách mới cùng ngày."""
    if lead.campaign_id is None:
        return None
    account_tz = await db.scalar(
        select(AdAccount.timezone_name)
        .join(Campaign, Campaign.ad_account_id == AdAccount.id)
        .where(Campaign.id == lead.campaign_id)
    )
    tz = ZoneInfo(account_tz or tz_name)
    day = lead.first_inbound_at.astimezone(tz).date()
    spend = await db.scalar(
        select(AdInsightDaily.spend_vnd).where(
            AdInsightDaily.level == "campaign",
            AdInsightDaily.object_id == lead.campaign_id,
            AdInsightDaily.date == day,
        )
    )
    start = dt.datetime.combine(day, dt.time(0), tzinfo=tz)
    same_day = await db.scalar(
        select(func.count()).where(
            Lead.campaign_id == lead.campaign_id,
            Lead.merged_into_lead_id.is_(None),
            Lead.first_inbound_at >= start,
            Lead.first_inbound_at < start + dt.timedelta(days=1),
        )
    )
    return money_ratio(spend, int(same_day or 0))


async def names(db: AsyncSession, level: Level, ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
    if not ids:
        return {}
    model: Any = {"campaign": Campaign, "adset": AdSet, "ad": Ad}[level]
    return {row.id: row for row in await db.scalars(select(model).where(model.id.in_(ids)))}


# ---------------------------------------------------------------- màn Quảng cáo


def _metric(value: int | Decimal | None, previous: int | Decimal | None) -> Metric:
    return Metric(
        value=Decimal(value) if value is not None else None,
        previous=Decimal(previous) if previous is not None else None,
    )


def _kpis(now_total: Stat, prev_total: Stat) -> AdsKpis:
    return AdsKpis(
        spend_vnd=_metric(now_total.spend_vnd, prev_total.spend_vnd),
        results=_metric(now_total.results, prev_total.results),
        cost_per_result_vnd=_metric(now_total.cost_per_result, prev_total.cost_per_result),
        ctr=_metric(now_total.ctr, prev_total.ctr),
        cpm_vnd=_metric(now_total.cpm, prev_total.cpm),
        frequency=_metric(now_total.frequency, prev_total.frequency),
        leads=_metric(now_total.leads, prev_total.leads),
        won=_metric(now_total.won, prev_total.won),
        cost_per_won_vnd=_metric(now_total.cost_per_won, prev_total.cost_per_won),
    )


async def report(
    db: AsyncSession,
    r: DateRange,
    level: Level,
    *,
    account_id: uuid.UUID | None,
    now: dt.datetime,
    is_mock: bool,
) -> AdsReport:
    from app.services.alert_rules import effective_rules
    from app.services.meta_sync import FxTable

    accounts = list(await db.scalars(select(AdAccount).order_by(AdAccount.name)))
    campaigns_now = await level_stats(db, "campaign", r, account_id=account_id)
    campaigns_prev = await level_stats(db, "campaign", r.previous(), account_id=account_id)
    stats = (
        campaigns_now
        if level == "campaign"
        else await level_stats(db, level, r, account_id=account_id)
    )

    model: Any = {"campaign": Campaign, "adset": AdSet, "ad": Ad}[level]
    query = select(model)
    if account_id is not None:
        if level == "campaign":
            query = query.where(Campaign.ad_account_id == account_id)
        else:
            query = query.join(Campaign, Campaign.id == model.campaign_id).where(
                Campaign.ad_account_id == account_id
            )
    objects = [o for o in await db.scalars(query) if o.id in stats or (o.status or "") == "ACTIVE"]
    campaign_ids = {o.id if level == "campaign" else o.campaign_id for o in objects}
    campaigns = await names(db, "campaign", campaign_ids)
    adsets = await names(db, "adset", {o.ad_set_id for o in objects}) if level == "ad" else {}
    account_by_id = {a.id: a for a in accounts}
    fx = await FxTable.load(db)
    today = now.astimezone(r.tz).date()

    def budget_vnd(minor: int | None, account: AdAccount | None) -> int | None:
        if minor is None or account is None:
            return None
        return fx.to_vnd(minor, (account.currency or "VND").upper(), today)

    rows: list[AdsRow] = []
    for o in objects:
        campaign = campaigns.get(o.id if level == "campaign" else o.campaign_id)
        account = account_by_id.get(campaign.ad_account_id) if campaign else None
        stat = stats.get(o.id, Stat(object_id=o.id))
        parent = None
        if level == "adset" and campaign is not None:
            parent = campaign.name
        elif level == "ad":
            adset = adsets.get(o.ad_set_id)
            parent = adset.name if adset else None
        budget = getattr(o, "daily_budget_minor", None)
        rows.append(
            AdsRow(
                id=o.id,
                name=o.name,
                parent=parent,
                account=account.name if account else "",
                objective=campaign.objective if campaign else None,
                status=o.status,
                daily_budget_vnd=budget_vnd(budget, account),
                spend_vnd=stat.spend_vnd,
                results=stat.results,
                cost_per_result_vnd=stat.cost_per_result,
                ctr=stat.ctr,
                cpm_vnd=stat.cpm,
                frequency=stat.frequency,
                leads=stat.leads,
                won=stat.won,
                cost_per_won_vnd=stat.cost_per_won,
            )
        )
    rows.sort(key=lambda row: (-(row.spend_vnd or 0), row.name))

    top = sorted(
        (s for s in campaigns_now.values() if s.cost_per_result is not None),
        key=lambda s: -(s.spend_vnd or 0),
    )[:5]
    bar_names = await names(db, "campaign", {s.object_id for s in top})
    rules = await effective_rules(db)
    return AdsReport(
        range=RangeOut(key=r.key, first_day=r.first_day, last_day=r.last_day),
        accounts=[AdAccountRef(id=a.id, name=a.name, currency=a.currency) for a in accounts],
        kpis=_kpis(total(campaigns_now), total(campaigns_prev)),
        cost_bars=[
            CostBar(
                id=s.object_id,
                name=bar_names[s.object_id].name,
                cost_per_result_vnd=s.cost_per_result or 0,
            )
            for s in top
        ],
        cost_threshold_vnd=int(rules["cost_per_result"].params["max_vnd"]),
        rows=rows[:200],
        missing_fx=await missing_fx_currencies(db, r),
        is_mock=is_mock,
    )
