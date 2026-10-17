"""Schema Kết nối BM và gán Trang (Bước 6). Không bao giờ trả mã truy cập ra ngoài."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models import ConnectionStatus


class TokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # SecretStr: không lộ mã khi in, log hay báo lỗi kiểm tra dữ liệu.
    token: SecretStr = Field(min_length=8, max_length=1000)
    fb_business_id: str | None = Field(default=None, max_length=32, pattern=r"^\d+$")

    @field_validator("token")
    @classmethod
    def _no_spaces(cls, value: SecretStr) -> SecretStr:
        return SecretStr(value.get_secret_value().strip())


class ConnectInput(TokenInput):
    name: str | None = Field(default=None, max_length=200)


CheckLevel = Literal["ok", "warn", "fail"]


class CheckItem(BaseModel):
    key: str
    level: CheckLevel
    count: int | None = None
    total: int | None = None
    detail: str | None = None


class PagePreview(BaseModel):
    fb_page_id: str
    name: str
    # new: sẽ theo dõi; existing: đã có trong workspace;
    # other_workspace: workspace khác đang theo dõi
    state: Literal["new", "existing", "other_workspace"]


class CheckResult(BaseModel):
    business_id: str
    business_name: str
    verification_status: str | None
    system_user_name: str | None
    scopes: list[str]
    missing_scopes: list[str]
    can_save: bool
    checks: list[CheckItem]
    pages: list[PagePreview]
    ad_account_count: int
    already_connected: bool


class BmOut(BaseModel):
    id: uuid.UUID
    name: str
    fb_business_id: str
    verification_status: str | None
    system_user_name: str | None
    token_last4: str | None
    status: ConnectionStatus
    status_detail: str | None
    missing_scopes: list[str]
    page_count: int
    ad_account_count: int
    last_checked_at: dt.datetime | None
    is_mock: bool


class BmOverview(BaseModel):
    bms: list[BmOut]
    tracked_pages: int
    unassigned_pages: int
    ad_accounts: int
    can_connect: bool


class PageRow(BaseModel):
    id: uuid.UUID
    fb_page_id: str
    name: str
    business_manager: str
    is_tracked: bool
    untracked_reason: str | None
    webhook_subscribed: bool
    owner: NamedRefOpt | None
    owner_since: dt.datetime | None
    leads_7d: int
    is_new: bool


class NamedRefOpt(BaseModel):
    id: uuid.UUID
    name: str


class PageList(BaseModel):
    pages: list[PageRow]
    # Người nhận được Trang. Bật "1 nhân viên – 1 Trang" thì chỉ gồm người chưa có Trang.
    candidates: list[NamedRefOpt]
    one_page_per_member: bool


class AssignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: uuid.UUID | None


PageRow.model_rebuild()
