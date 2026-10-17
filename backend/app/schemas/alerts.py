"""Schema cấu hình cảnh báo Telegram và tỉ giá (Bước 7)."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.alert_rules import RULE_TYPES

# Chat ID số (nhóm có dấu "-") hoặc tên kênh công khai "@ten_kenh".
CHAT_ID = re.compile(r"^(-?\d{5,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")


class RuleOut(BaseModel):
    type: str
    enabled: bool
    params: dict[str, Any]


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    enabled: bool
    params: dict[str, float] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in RULE_TYPES:
            raise ValueError("unknown_rule")
        return value


class RuleToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class FxRateOut(BaseModel):
    id: uuid.UUID
    currency: str
    effective_from: dt.date
    vnd_per_unit: Decimal


class FxRateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_from: dt.date
    vnd_per_unit: Decimal = Field(gt=0, le=Decimal("1000000"), decimal_places=4)

    @field_validator("currency")
    @classmethod
    def _not_vnd(cls, value: str) -> str:
        if value == "VND":
            raise ValueError("vnd_has_no_rate")
        return value


class DeliveryOut(BaseModel):
    rule_type: str
    status: str
    error: str | None
    sent_at: dt.datetime


class AlertSettingsOut(BaseModel):
    chat_id: str | None
    bot_configured: bool
    is_mock: bool
    rules: list[RuleOut]
    fx_rates: list[FxRateOut]
    currencies: list[str]
    deliveries: list[DeliveryOut]


class AlertSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str | None = Field(default=None, max_length=40)
    rules: list[RuleIn] = Field(default_factory=list, max_length=len(RULE_TYPES))


class RulesView(BaseModel):
    rules: list[RuleOut]
    can_edit: bool
    chat_configured: bool


class TestResult(BaseModel):
    status: str
