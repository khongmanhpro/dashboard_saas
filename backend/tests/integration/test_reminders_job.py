"""Job nhắc việc: tạo thông báo một lần, gửi Web Push (bản giả), xóa đăng ký hết hạn."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    LeadEvent,
    LeadEventType,
    MemberRole,
    Notification,
    NotificationType,
    PushSubscription,
)
from app.services import push
from app.services.assignment import assign_page
from app.workers.reminders import send_reminders
from tests.integration import factories as f

pytestmark = pytest.mark.integration

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MORNING = dt.datetime(2026, 10, 14, 10, 0, tzinfo=VN)


OK = "https://fcm.googleapis.com/fcm/send/ok"
GONE = "https://fcm.googleapis.com/fcm/send/gone"
INTERNAL = "https://10.0.0.5/noi-bo"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Thay hàm gửi thật: ghi lại (endpoint, nội dung). Endpoint chứa "gone" thì trả 410."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(sub: PushSubscription, data: str) -> int | None:
        calls.append((sub.endpoint, json.loads(data)))
        return 410 if "gone" in sub.endpoint else None

    monkeypatch.setattr(push, "_send_one", fake)
    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", "BPublicKeyForTests")
    monkeypatch.setattr(s, "vapid_private_key", SecretStr("private-key-for-tests"))
    return calls


@pytest.fixture
async def setup(admin_db: AsyncSession) -> dict[str, Any]:
    ws = await f.create_workspace(admin_db)
    staff = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
    page = await f.create_page(admin_db, ws)
    await assign_page(admin_db, page, staff, MORNING - dt.timedelta(days=30))
    # Khách chờ 20 phút chưa trả lời, có SĐT từ 3 giờ trước, chưa gọi.
    lead = await f.create_lead(
        admin_db,
        page,
        staff,
        MORNING - dt.timedelta(minutes=20),
        response_seconds=None,
        phone="0900000123",
    )
    lead.phone_captured_at = MORNING - dt.timedelta(hours=3)
    for endpoint in (OK, GONE, INTERNAL):
        admin_db.add(
            PushSubscription(
                workspace_id=ws.id, member_id=staff.id, endpoint=endpoint, p256dh="k", auth="a"
            )
        )
    await admin_db.commit()
    return {"staff": staff.id, "lead": lead.id}


async def test_job_creates_each_reminder_once_and_pushes(
    setup: dict[str, Any], admin_db: AsyncSession, sent: list[tuple[str, dict[str, Any]]]
) -> None:
    result = await send_reminders({}, now=MORNING.astimezone(dt.UTC))
    assert result == {"created": 2, "failed": 0}
    rows = (await admin_db.scalars(select(Notification).order_by(Notification.id))).all()
    assert {r.type for r in rows} == {NotificationType.WAIT_15, NotificationType.PHONE_NOT_CALLED}
    assert all(r.member_id == setup["staff"] and r.sent_via == "push" for r in rows)
    assert all("0900000123" not in r.body and "0900000123" not in r.title for r in rows)

    payloads = [p for _, p in sent]
    assert all(p["url"] == f"/m/leads/{setup['lead']}" for p in payloads)
    assert "0900000123" not in json.dumps(payloads)
    # Máy trả 410 bị xóa đăng ký.
    endpoints = (await admin_db.scalars(select(PushSubscription.endpoint))).all()
    assert endpoints == [OK]
    # Mục O: địa chỉ không phải dịch vụ đẩy thì xóa, không gọi tới.
    assert INTERNAL not in [e for e, _ in sent]
    events = await admin_db.scalar(
        select(func.count()).where(LeadEvent.type == LeadEventType.REMINDER_SENT)
    )
    assert events == 2

    # Chạy lại cùng mốc: không nhắc lặp.
    sent.clear()
    again = await send_reminders({}, now=MORNING.astimezone(dt.UTC) + dt.timedelta(minutes=5))
    assert again == {"created": 0, "failed": 0}
    assert sent == []
    # 10 phút sau: khách chờ 30 phút → mốc mới.
    later = await send_reminders({}, now=MORNING.astimezone(dt.UTC) + dt.timedelta(minutes=10))
    assert later["created"] == 1


async def test_night_run_sends_nothing(
    setup: dict[str, Any], admin_db: AsyncSession, sent: list[Any]
) -> None:
    night = dt.datetime(2026, 10, 14, 23, 0, tzinfo=VN)
    assert (await send_reminders({}, now=night.astimezone(dt.UTC)))["created"] == 0


async def test_without_vapid_keys_reminders_stay_in_app(
    setup: dict[str, Any], admin_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vapid_private_key", SecretStr(""))
    assert (await send_reminders({}, now=MORNING.astimezone(dt.UTC)))["created"] == 2
    rows = (await admin_db.scalars(select(Notification))).all()
    assert all(r.sent_via is None for r in rows)
