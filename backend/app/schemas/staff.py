"""Schema bảng xếp hạng, hồ sơ nhân viên và công thức điểm."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import LeadStatus, MemberRole, PeriodType, Tier
from app.schemas.leads import NamedRef


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    close_rate: int = Field(ge=0, le=100)
    response_speed: int = Field(ge=0, le=100)
    revenue: int = Field(ge=0, le=100)
    phone_rate: int = Field(ge=0, le=100)
    page_care: int = Field(ge=0, le=100)
    on_time: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _sum_is_100(self) -> Weights:
        if sum(self.model_dump().values()) != 100:
            raise ValueError("weights_must_sum_to_100")
        return self


class FormulaOut(BaseModel):
    version: int
    weights: Weights
    speed_full_minutes: int
    speed_zero_minutes: int
    tier_a: int
    tier_b: int
    tier_c: int
    min_leads: int
    posts_per_week_target: int
    effective_from: dt.datetime
    created_by: str | None
    # Chăm Trang chưa có số liệu tới Bước 7: trọng số của nó được chia lại.
    page_care_available: bool
    can_edit: bool


class FormulaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: Weights


class PreviewRow(BaseModel):
    member: NamedRef
    current_total: Decimal | None
    current_tier: Tier | None
    new_total: Decimal | None
    new_tier: Tier | None
    new_rank: int | None


class PreviewOut(BaseModel):
    period_first_day: dt.date
    period_last_day: dt.date
    rows: list[PreviewRow]


class PeriodInfo(BaseModel):
    type: PeriodType
    first_day: dt.date | None
    last_day: dt.date | None
    computed_at: dt.datetime | None
    is_final: bool


class LeaderboardRow(BaseModel):
    member: NamedRef
    team: NamedRef | None
    pages: list[str]
    is_self: bool
    rank: int | None
    tier: Tier | None
    insufficient_data: bool
    # NULL khi người xem không được thấy (nhân viên xem top 10 của người khác, quyết định #9).
    total: Decimal | None
    delta: Decimal | None
    lead_count: int | None
    median_response_seconds: int | None
    phone_rate: Decimal | None
    close_rate: Decimal | None
    revenue_vnd: int | None
    overdue_count: int | None


class Kpis(BaseModel):
    lead_count: int
    median_response_seconds: int | None
    phone_rate: Decimal | None
    close_rate: Decimal | None
    revenue_vnd: int
    overdue_count: int


class Leaderboard(BaseModel):
    period: PeriodInfo
    min_leads: int
    tiers: dict[Tier, int] | None
    insufficient_count: int | None
    kpis: Kpis | None
    teams: list[NamedRef]
    rows: list[LeaderboardRow]
    full_view: bool


class ScorePart(BaseModel):
    key: str
    weight: int
    effective_weight: Decimal | None
    score: Decimal | None
    points: Decimal | None
    raw: dict[str, int | Decimal | None]


class FunnelStep(BaseModel):
    key: str
    value: int
    rate: Decimal | None
    company_rate: Decimal | None


class HourBucket(BaseModel):
    label: str
    median_minutes: Decimal | None
    count: int


class TrendPoint(BaseModel):
    first_day: dt.date
    total: Decimal | None
    tier: Tier | None


class RecentLead(BaseModel):
    id: uuid.UUID
    display_name: str | None
    short_ref: str
    first_inbound_at: dt.datetime
    response_business_seconds: int | None
    status: LeadStatus
    overdue: bool


class AssignedPage(BaseModel):
    id: uuid.UUID
    name: str
    since: dt.datetime


class StaffDetail(BaseModel):
    member: NamedRef
    role: MemberRole
    team: NamedRef | None
    team_lead: str | None
    pages: list[AssignedPage]
    period: PeriodInfo
    total: Decimal | None
    tier: Tier | None
    rank: int | None
    ranked_count: int
    delta: Decimal | None
    insufficient_data: bool
    min_leads: int
    lead_count: int
    parts: list[ScorePart]
    funnel: list[FunnelStep]
    hours: list[HourBucket]
    trend: list[TrendPoint]
    recent: list[RecentLead]
    slow_reply_minutes: int
