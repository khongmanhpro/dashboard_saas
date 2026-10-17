"""Schema API khách hàng. SĐT đã được che ở service nếu người xem không có quyền."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import LeadSource, LeadStatus, LostReason


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class LeadCard(BaseModel):
    id: uuid.UUID
    # NULL thì giao diện hiện "Khách ···<short_ref>".
    display_name: str | None
    short_ref: str
    page: NamedRef
    owner: NamedRef | None
    source: LeadSource
    from_ad: bool
    fb_ad_id: str | None
    status: LeadStatus
    first_inbound_at: dt.datetime
    first_reply_at: dt.datetime | None
    response_business_seconds: int | None
    # Khách chưa được trả lời: số giây trong giờ làm việc đã chờ tính tới lúc đọc.
    waiting_business_seconds: int | None
    is_slow: bool
    result_due_at: dt.datetime
    result_at: dt.datetime | None
    overdue: bool
    callback_at: dt.datetime | None
    won_value_vnd: int | None
    lost_reason: LostReason | None
    phone: str | None
    phone_masked: bool
    called_at: dt.datetime | None


class LeadPage(BaseModel):
    items: list[LeadCard]
    next_cursor: str | None


class LeadSummary(BaseModel):
    total: int
    unreplied: int
    overdue: int
    phone_not_called: int
    new_today: int
    by_status: dict[LeadStatus, int]


class FilterOptions(BaseModel):
    pages: list[NamedRef]
    owners: list[NamedRef]


class TimelineItem(BaseModel):
    kind: Literal["message", "event"]
    at: dt.datetime
    # Tin nhắn
    direction: Literal["in", "out"] | None = None
    text: str | None = None
    has_attachments: bool = False
    is_automated: bool = False
    is_first_reply: bool = False
    # Sự kiện
    type: str | None = None
    actor: str | None = None
    data: dict[str, Any] | None = None


class LeadPermissions(BaseModel):
    can_update: bool
    can_edit_result: bool
    # Nhân viên tự sửa kết quả tới mốc này (7 ngày sau lần có kết quả đầu tiên).
    edit_until: dt.datetime | None


class LeadDetail(LeadCard):
    fb_page_id: str
    slow_reply_minutes: int
    lost_note: str | None
    phones: list[str]
    timeline: list[TimelineItem]
    timeline_truncated: bool
    permissions: LeadPermissions


class CalledUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    called: bool


MAX_ORDER_VND = 100_000_000_000  # 100 tỷ: chặn gõ nhầm thừa số 0


class ResultUpdate(BaseModel):
    """Kết quả của đợt khách. Chỉ Hẹn lại / Chốt / Hủy (quyết định Bước 3)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[LeadStatus.CALLBACK, LeadStatus.WON, LeadStatus.LOST]
    callback_at: dt.datetime | None = None
    won_value_vnd: int | None = Field(default=None, gt=0, le=MAX_ORDER_VND)
    lost_reason: LostReason | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _required_fields(self) -> ResultUpdate:
        if self.status == LeadStatus.CALLBACK:
            if self.callback_at is None:
                raise ValueError("callback_at_required")
            if self.callback_at.tzinfo is None:
                raise ValueError("callback_at_needs_timezone")
        if self.status == LeadStatus.WON and self.won_value_vnd is None:
            raise ValueError("won_value_required")
        if self.status == LeadStatus.LOST:
            if self.lost_reason is None:
                raise ValueError("lost_reason_required")
            if self.lost_reason == LostReason.OTHER and not (self.note and self.note.strip()):
                raise ValueError("lost_note_required")
        return self
