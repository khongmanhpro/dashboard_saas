"""Luật nhắc việc (quyết định Bước 5): đúng mốc, mỗi mốc một khóa, ngoài giờ chỉ nhắc giờ hẹn."""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest

from app.models import LeadSource, LeadStatus, NotificationType
from app.services.reminders import LeadState, display_name, due_reminders

NOW = dt.datetime(2026, 10, 14, 3, 0, tzinfo=dt.UTC)  # 10:00 giờ VN
OWNER = uuid.uuid4()


def lead(**changes: object) -> LeadState:
    base = LeadState(
        id=uuid.UUID(int=1),
        owner_id=OWNER,
        name="[Khách 1042]",
        source=LeadSource.MESSAGE,
        status=LeadStatus.CONTACTED,
        first_inbound_at=NOW - dt.timedelta(hours=1),
        first_reply_at=NOW - dt.timedelta(minutes=50),
        waiting_business_seconds=None,
        phone_captured_at=None,
        called_at=None,
        result_at=None,
        result_due_at=NOW + dt.timedelta(hours=47),
        callback_at=None,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def types(
    state: LeadState, now: dt.datetime = NOW, in_hours: bool = True
) -> list[NotificationType]:
    return [r.type for r in due_reminders(state, now, in_business_hours=in_hours)]


def unreplied(minutes: int) -> LeadState:
    return lead(status=LeadStatus.NEW, first_reply_at=None, waiting_business_seconds=minutes * 60)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (14, []),
        (15, [NotificationType.WAIT_15]),
        (29, [NotificationType.WAIT_15]),
        (30, [NotificationType.WAIT_30]),
        (200, [NotificationType.WAIT_30]),
    ],
)
def test_waiting_customer(minutes: int, expected: list[NotificationType]) -> None:
    assert types(unreplied(minutes)) == expected


def test_no_reminder_outside_business_hours_except_callback() -> None:
    assert types(unreplied(40), in_hours=False) == []
    callback = lead(
        status=LeadStatus.CALLBACK,
        callback_at=NOW + dt.timedelta(minutes=10),
        result_at=NOW - dt.timedelta(hours=2),
    )
    assert types(callback, in_hours=False) == [NotificationType.CALLBACK_SOON]


def test_old_unreplied_lead_is_not_reminded() -> None:
    old = dataclasses.replace(unreplied(500), first_inbound_at=NOW - dt.timedelta(days=3))
    assert NotificationType.WAIT_30 not in types(old)


def test_phone_not_called_after_two_hours() -> None:
    assert types(lead(phone_captured_at=NOW - dt.timedelta(minutes=119))) == []
    assert types(lead(phone_captured_at=NOW - dt.timedelta(hours=2))) == [
        NotificationType.PHONE_NOT_CALLED
    ]
    called = lead(
        phone_captured_at=NOW - dt.timedelta(hours=3), called_at=NOW - dt.timedelta(hours=1)
    )
    assert types(called) == []
    assert types(lead(phone_captured_at=NOW - dt.timedelta(days=8))) == []


def test_result_deadline() -> None:
    assert types(lead(result_due_at=NOW + dt.timedelta(hours=4, minutes=1))) == []
    assert types(lead(result_due_at=NOW + dt.timedelta(hours=4))) == [NotificationType.DUE_SOON]
    assert types(lead(result_due_at=NOW)) == [NotificationType.OVERDUE]
    assert types(lead(result_due_at=NOW - dt.timedelta(hours=25))) == []
    done = lead(
        result_due_at=NOW - dt.timedelta(hours=1),
        result_at=NOW - dt.timedelta(hours=2),
        status=LeadStatus.CALLBACK,
        callback_at=NOW + dt.timedelta(days=2),
    )
    assert types(done) == []


def test_callback_reminders_follow_appointment_time() -> None:
    at = NOW + dt.timedelta(minutes=15)
    soon = lead(status=LeadStatus.CALLBACK, callback_at=at, result_at=NOW - dt.timedelta(hours=1))
    reminders = due_reminders(soon, NOW, in_business_hours=True, callback_time_text="10:15")
    assert [r.type for r in reminders] == [NotificationType.CALLBACK_SOON]
    assert "10:15" in reminders[0].body
    moved = dataclasses.replace(soon, callback_at=at + dt.timedelta(days=1))
    assert types(moved, now=NOW + dt.timedelta(days=1)) == [NotificationType.CALLBACK_SOON]
    assert (
        reminders[0].dedupe_key
        != due_reminders(moved, NOW + dt.timedelta(days=1), in_business_hours=True)[0].dedupe_key
    )
    missed = lead(
        status=LeadStatus.CALLBACK,
        callback_at=NOW - dt.timedelta(hours=24),
        result_at=NOW - dt.timedelta(days=2),
    )
    assert types(missed) == [NotificationType.CALLBACK_MISSED]


def test_final_or_unowned_leads_are_never_reminded() -> None:
    assert types(dataclasses.replace(unreplied(40), owner_id=None)) == []
    assert types(lead(status=LeadStatus.WON, result_due_at=NOW)) == []
    assert types(lead(status=LeadStatus.LOST, result_due_at=NOW)) == []


def test_texts_have_name_but_never_phone() -> None:
    r = due_reminders(
        lead(phone_captured_at=NOW - dt.timedelta(hours=3)), NOW, in_business_hours=True
    )[0]
    assert "[Khách 1042]" in r.body
    assert r.dedupe_key == f"phone_not_called:{uuid.UUID(int=1)}"
    assert display_name(None, "1234") == "Khách ···1234"
