"""Schema cho ứng dụng điện thoại (/m), nhắc việc và đăng ký thông báo đẩy."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import NotificationType, Tier
from app.schemas.leads import LeadCard
from app.services.push import is_push_endpoint

MobileTab = Literal["todo", "callback", "done"]


class MobileScore(BaseModel):
    total: Decimal | None
    tier: Tier | None
    rank: int | None
    ranked_count: int
    # Số bậc tăng (+) hay giảm (−) so với tuần trước.
    rank_change: int | None
    next_tier: Tier | None
    points_to_next: Decimal | None
    insufficient_data: bool
    lead_count: int
    min_leads: int


class MobileStats(BaseModel):
    median_response_seconds: int | None
    phone_rate: Decimal | None
    close_rate: Decimal | None


class MobileHome(BaseModel):
    first_name: str
    pages: list[str]
    score: MobileScore | None
    stats: MobileStats | None
    phone_not_called: int
    tabs: dict[MobileTab, int]
    unread: int


class MobileLead(LeadCard):
    fb_page_id: str
    snippet: str | None
    phone_captured_at: dt.datetime | None


class NotificationOut(BaseModel):
    id: int
    type: NotificationType
    title: str
    body: str
    lead_id: uuid.UUID | None
    created_at: dt.datetime
    read_at: dt.datetime | None


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class PushConfig(BaseModel):
    enabled: bool
    public_key: str | None


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="ignore")

    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscribe(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def _push_service(cls, value: str) -> str:
        if not is_push_endpoint(value):
            raise ValueError("endpoint_not_push_service")
        return value


class PushUnsubscribe(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
