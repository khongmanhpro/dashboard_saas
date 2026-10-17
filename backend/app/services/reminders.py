"""Luật nhắc việc (quyết định Bước 5, mục G). Hàm thuần, job gọi theo từng khách.

Mỗi mốc có `dedupe_key` riêng nên chỉ nhắc một lần. Nhắc theo giờ hẹn gắn với `callback_at`,
nên đổi giờ hẹn thì có mốc mới. Khách cũ (dữ liệu trước khi có tính năng) không bị nhắc hàng
loạt: mỗi luật có cửa sổ thời gian giới hạn.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from app.i18n import vi
from app.models import LeadSource, LeadStatus, NotificationType

WAIT_FIRST = dt.timedelta(minutes=15)
WAIT_SECOND = dt.timedelta(minutes=30)
WAIT_WINDOW = dt.timedelta(days=2)
PHONE_AFTER = dt.timedelta(hours=2)
PHONE_WINDOW = dt.timedelta(days=7)
DUE_SOON_BEFORE = dt.timedelta(hours=4)
OVERDUE_WINDOW = dt.timedelta(hours=24)
CALLBACK_BEFORE = dt.timedelta(minutes=15)
CALLBACK_MISSED_AFTER = dt.timedelta(hours=24)  # quyết định #11
CALLBACK_MISSED_WINDOW = dt.timedelta(hours=24)
_FINAL = (LeadStatus.WON, LeadStatus.LOST)


@dataclass(frozen=True)
class LeadState:
    id: uuid.UUID
    owner_id: uuid.UUID | None
    name: str
    source: LeadSource
    status: LeadStatus
    first_inbound_at: dt.datetime
    first_reply_at: dt.datetime | None
    waiting_business_seconds: int | None  # chỉ có khi khách nhắn tin chưa được trả lời
    phone_captured_at: dt.datetime | None
    called_at: dt.datetime | None
    result_at: dt.datetime | None
    result_due_at: dt.datetime
    callback_at: dt.datetime | None


@dataclass(frozen=True)
class Reminder:
    type: NotificationType
    lead_id: uuid.UUID
    member_id: uuid.UUID
    dedupe_key: str
    title: str
    body: str


def display_name(name: str | None, short_ref: str) -> str:
    return name or vi.UNNAMED.format(ref=short_ref)


def _make(type_: NotificationType, lead: LeadState, key: str, **params: str) -> Reminder:
    assert lead.owner_id is not None  # noqa: S101 — lọc trước khi gọi
    return Reminder(
        type=type_,
        lead_id=lead.id,
        member_id=lead.owner_id,
        dedupe_key=f"{type_.value}:{lead.id}{key}",
        title=vi.TITLES[type_],
        body=vi.BODIES[type_].format(name=lead.name, **params),
    )


def due_reminders(
    lead: LeadState, now: dt.datetime, *, in_business_hours: bool, callback_time_text: str = ""
) -> list[Reminder]:
    """Các nhắc việc đến hạn của một khách tại thời điểm `now`."""
    if lead.owner_id is None or lead.status in _FINAL:
        return []
    out: list[Reminder] = []

    if lead.status == LeadStatus.CALLBACK and lead.callback_at is not None:
        key = f":{int(lead.callback_at.timestamp())}"
        if lead.callback_at - CALLBACK_BEFORE <= now < lead.callback_at:
            out.append(_make(NotificationType.CALLBACK_SOON, lead, key, time=callback_time_text))
        missed_at = lead.callback_at + CALLBACK_MISSED_AFTER
        if in_business_hours and missed_at <= now < missed_at + CALLBACK_MISSED_WINDOW:
            out.append(_make(NotificationType.CALLBACK_MISSED, lead, key))

    if not in_business_hours:
        return out

    waiting = lead.waiting_business_seconds
    if (
        lead.source == LeadSource.MESSAGE
        and lead.status == LeadStatus.NEW
        and lead.first_reply_at is None
        and waiting is not None
        and now - lead.first_inbound_at < WAIT_WINDOW
    ):
        if waiting >= WAIT_SECOND.total_seconds():
            out.append(_make(NotificationType.WAIT_30, lead, ""))
        elif waiting >= WAIT_FIRST.total_seconds():
            out.append(_make(NotificationType.WAIT_15, lead, ""))

    if (
        lead.phone_captured_at is not None
        and lead.called_at is None
        and lead.phone_captured_at + PHONE_AFTER <= now < lead.phone_captured_at + PHONE_WINDOW
    ):
        out.append(_make(NotificationType.PHONE_NOT_CALLED, lead, ""))

    if lead.result_at is None:
        if lead.result_due_at - DUE_SOON_BEFORE <= now < lead.result_due_at:
            out.append(_make(NotificationType.DUE_SOON, lead, ""))
        elif lead.result_due_at <= now < lead.result_due_at + OVERDUE_WINDOW:
            out.append(_make(NotificationType.OVERDUE, lead, ""))
    return out
