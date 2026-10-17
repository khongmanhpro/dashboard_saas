"""Schema các màn hình báo cáo của Bước 7: Tổng quan, Fanpage, Chi tiết Trang, Quảng cáo.

Số tiền là VND nguyên. Tỉ lệ là Decimal 0–1. `previous` là cùng chỉ số ở kỳ liền trước.
Trường chi phí quảng cáo là None với người không có `ads.cost.view`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models import PeriodType, Tier
from app.schemas.leads import NamedRef


class RangeOut(BaseModel):
    key: str
    first_day: dt.date
    last_day: dt.date


class Metric(BaseModel):
    value: Decimal | None
    previous: Decimal | None


# ---------------------------------------------------------------- Tổng quan


class OverviewAlerts(BaseModel):
    # Quá hạn 48 giờ: mọi thời điểm, không giới hạn kỳ (decisions.md mục J).
    overdue: int
    overdue_pages: int
    overdue_oldest_hours: int | None
    slow_staff: int
    slow_reply_minutes: int
    unassigned_pages: int | None
    bm_disconnected: int | None
    bm_disconnected_name: str | None
    bm_disconnected_pages: int
    expensive_campaigns: int | None
    # Khách của kỳ vào Trang lúc chưa có người phụ trách. None khi không xem toàn workspace.
    unassigned_leads: int | None


class OverviewKpis(BaseModel):
    new_leads: Metric
    median_response_seconds: Metric
    phone_rate: Metric
    close_rate: Metric
    revenue_vnd: Metric
    cost_per_won_vnd: Metric | None
    overdue_in_range: int  # khách của kỳ đã quá hạn 48 giờ (thẻ cảnh báo đếm mọi thời điểm)


class Funnel(BaseModel):
    """Phễu lồng nhau, kết quả tách riêng (docs/metrics.md)."""

    new: int
    replied: int
    unreplied: int
    phone: int
    no_phone: int
    called: int
    not_called: int
    won: int
    lost: int
    callback: int
    pending: int


class DailyPoint(BaseModel):
    day: dt.date
    new: int
    won: int


class CampaignSummary(BaseModel):
    id: uuid.UUID
    name: str
    spend_vnd: int | None
    leads: int
    won: int
    cost_per_won_vnd: int | None


class BoardRow(BaseModel):
    member: NamedRef
    rank: int | None
    total: Decimal | None
    tier: Tier | None
    page: str | None
    # Tiêu chí mạnh nhất (top) / yếu nhất (cần hỗ trợ) và số liệu thô của nó.
    note_key: str | None
    note_value: Decimal | None


class Boards(BaseModel):
    """Điểm tính trực tiếp cho kỳ `first_day`–`last_day` (có thể khác kỳ màn hình: "Hôm nay"
    dùng điểm 7 ngày)."""

    period: PeriodType
    first_day: dt.date
    last_day: dt.date
    same_as_range: bool
    top: list[BoardRow]
    bottom: list[BoardRow]


class OverviewOut(BaseModel):
    range: RangeOut
    # Số người có khách hoặc phụ trách Trang trong kỳ (cùng danh sách với /staff).
    members: int
    pages: int
    bms: int
    alerts: OverviewAlerts
    kpis: OverviewKpis
    funnel: Funnel
    daily: list[DailyPoint]
    campaigns: list[CampaignSummary] | None
    missing_fx: list[str]
    boards: Boards
    teams: list[NamedRef]
    is_mock: bool


# ---------------------------------------------------------------- Fanpage

PageStatus = Literal["ok", "declining", "disconnected"]
PageTab = Literal["all", "unassigned", "low_posts", "declining", "disconnected"]
PageSort = Literal["leads", "score", "posts", "name"]


class PageReportRow(BaseModel):
    """Số khách, chốt, trả lời, điểm: cùng kỳ 7 ngày (hôm nay và 6 ngày trước)."""

    id: uuid.UUID
    name: str
    fb_page_id: str
    bm_name: str
    owner: NamedRef | None
    owner_total: Decimal | None
    owner_tier: Tier | None
    leads_7d: int
    median_response_seconds: int | None
    won_7d: int
    revenue_7d: int
    overdue_7d: int
    posts_week: int | None
    views_30d: int | None
    views_daily: list[int | None]
    status: PageStatus


class PageTabs(BaseModel):
    all: int
    unassigned: int
    low_posts: int
    declining: int
    disconnected: int


class PageReportList(BaseModel):
    rows: list[PageReportRow]
    total: int
    page: int
    page_size: int
    tabs: PageTabs
    bms: list[NamedRef]
    teams: list[NamedRef]
    posts_target: int
    can_assign: bool
    range: RangeOut
    is_mock: bool


class PostRow(BaseModel):
    id: uuid.UUID
    excerpt: str | None
    created_time: dt.datetime
    type: str
    views: int | None
    reactions: int
    comments: int
    shares: int
    engagement_rate: Decimal | None
    permalink: str | None


class DayValue(BaseModel):
    day: dt.date
    value: int | None


class PageKpis(BaseModel):
    followers: int | None
    new_follows: Metric
    views: Metric
    reach: Metric
    engagements: Metric
    video_views: Metric
    posts: Metric


class PageDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    fb_page_id: str
    bm_name: str
    status: PageStatus
    owner: NamedRef | None
    team: str | None
    content_synced_at: dt.datetime | None
    kpis: PageKpis
    daily_views: list[DayValue]
    # 7 hàng (T2..CN) × 6 khung giờ (6–9h … 21–24h): tỉ lệ tương tác trung bình. None: ít bài.
    heatmap: list[list[Decimal | None]] | None
    heatmap_min_posts: int
    posts: list[PostRow]
    is_mock: bool


# ---------------------------------------------------------------- Quảng cáo

AdsLevel = Literal["campaign", "adset", "ad"]


class AdsKpis(BaseModel):
    spend_vnd: Metric
    results: Metric
    cost_per_result_vnd: Metric
    ctr: Metric
    cpm_vnd: Metric
    frequency: Metric
    leads: Metric
    won: Metric
    cost_per_won_vnd: Metric


class AdsRow(BaseModel):
    id: uuid.UUID
    name: str
    parent: str | None
    account: str
    objective: str | None
    status: str | None
    daily_budget_vnd: int | None
    spend_vnd: int | None
    results: int | None
    cost_per_result_vnd: int | None
    ctr: Decimal | None
    cpm_vnd: int | None
    frequency: Decimal | None
    leads: int
    won: int
    cost_per_won_vnd: int | None


class CostBar(BaseModel):
    id: uuid.UUID
    name: str
    cost_per_result_vnd: int


class AdAccountRef(BaseModel):
    id: uuid.UUID
    name: str
    currency: str | None


class AdsReport(BaseModel):
    range: RangeOut
    accounts: list[AdAccountRef]
    kpis: AdsKpis
    cost_bars: list[CostBar]
    cost_threshold_vnd: int
    rows: list[AdsRow]
    missing_fx: list[str]
    is_mock: bool
