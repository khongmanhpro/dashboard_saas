"""Cập nhật khách: đã gọi, Hẹn lại / Chốt / Hủy, hạn sửa 7 ngày, audit (quyết định #12)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Lead, LeadEvent, LeadEventType
from tests.integration.leads_fixtures import lead_id_of

pytestmark = pytest.mark.integration


def _future(hours: int = 24) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=hours)).isoformat()


async def _put(client: Any, lead_id: str, **body: Any) -> Any:
    return await client.put(f"/api/leads/{lead_id}/result", json=body)


async def test_staff_walks_new_to_won(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")

    called = await client.post(f"/api/leads/{lead_id}/called", json={"called": True})
    assert called.status_code == 200, called.text
    assert called.json()["called_at"] is not None

    resp = await _put(client, lead_id, status="won", won_value_vnd=2_450_000, note="[ghi chú]")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "won"
    assert body["won_value_vnd"] == 2_450_000
    assert body["result_at"] is not None
    assert body["overdue"] is False

    lead = await admin_db.get(Lead, lead_id)
    assert lead is not None and lead.result_at is not None
    events = (
        await admin_db.scalars(
            select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.id)
        )
    ).all()
    status_event = [e for e in events if e.type == LeadEventType.STATUS_CHANGED][-1]
    assert status_event.data == {
        "from": "new",
        "to": "won",
        "won_value_vnd": 2_450_000,
        "note": "[ghi chú]",
    }
    assert any(e.type == LeadEventType.CALLED for e in events)
    audits = (await admin_db.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    actions = [a.action for a in audits if a.entity_type == "lead"]
    assert actions == ["lead.called", "lead.result_set"]
    assert "0912345218" not in str([(a.before, a.after) for a in audits])

    summary = (await client.get("/api/leads/summary", params={"period": "30d"})).json()
    assert summary["by_status"]["won"] == 1


async def test_called_toggle_off(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    await client.post(f"/api/leads/{lead_id}/called", json={"called": True})
    resp = await client.post(f"/api/leads/{lead_id}/called", json={"called": False})
    assert resp.json()["called_at"] is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"status": "won"}, 422),
        ({"status": "won", "won_value_vnd": 0}, 422),
        ({"status": "won", "won_value_vnd": 2.5}, 422),
        ({"status": "lost"}, 422),
        ({"status": "lost", "lost_reason": "other"}, 422),
        ({"status": "lost", "lost_reason": "other", "note": "   "}, 422),
        ({"status": "callback"}, 422),
        ({"status": "callback", "callback_at": "2026-10-20T10:00:00"}, 422),
        ({"status": "new"}, 422),
        ({"status": "contacted"}, 422),
        ({"status": "won", "won_value_vnd": 1, "phone": "x"}, 422),
    ],
)
async def test_invalid_results_are_rejected(
    as_role: Any, admin_db: AsyncSession, body: dict[str, Any], code: int
) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    resp = await client.put(f"/api/leads/{lead_id}/result", json=body)
    assert resp.status_code == code, resp.text
    lead = await admin_db.get(Lead, lead_id)
    assert lead is not None and lead.result_at is None


async def test_callback_must_be_in_future(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)).isoformat()
    resp = await _put(client, lead_id, status="callback", callback_at=past)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "callback_must_be_future"


async def test_editing_keeps_first_result_time(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    first = (await _put(client, lead_id, status="callback", callback_at=_future())).json()
    assert first["callback_at"] is not None
    second = (await _put(client, lead_id, status="lost", lost_reason="price")).json()
    assert second["status"] == "lost"
    assert second["lost_reason"] == "price"
    assert second["callback_at"] is None
    assert second["result_at"] == first["result_at"]
    third = (
        await _put(client, lead_id, status="lost", lost_reason="other", note="[khách đổi ý]")
    ).json()
    assert third["lost_note"] == "[khách đổi ý]"
    actions = (await admin_db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all()
    assert [a for a in actions if a.startswith("lead.result")] == [
        "lead.result_set",
        "lead.result_edited",
        "lead.result_edited",
    ]


async def test_staff_edit_window_is_seven_days(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    await _put(client, lead_id, status="won", won_value_vnd=500_000)
    lead = await admin_db.get(Lead, lead_id)
    assert lead is not None
    lead.result_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=8)
    await admin_db.commit()

    detail = (await client.get(f"/api/leads/{lead_id}")).json()
    assert detail["permissions"]["can_edit_result"] is False
    resp = await _put(client, lead_id, status="won", won_value_vnd=600_000)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "result_edit_window_closed"

    manager = await as_role("manager")
    resp = await _put(manager, lead_id, status="won", won_value_vnd=600_000)
    assert resp.status_code == 200
    assert resp.json()["won_value_vnd"] == 600_000


@pytest.mark.parametrize(
    ("role", "psid", "code"),
    [
        ("lead", "p1-a", 403),  # trưởng nhóm thấy khách của nhóm nhưng không sửa thay
        ("viewer", "p1-a", 403),
        ("s2", "p1-a", 404),  # ngoài phạm vi: như không tồn tại
        ("lead", "p3-a", 200),  # Trang trưởng nhóm tự phụ trách
        ("owner", "p2-a", 200),
    ],
)
async def test_who_can_update(
    as_role: Any, admin_db: AsyncSession, role: str, psid: str, code: int
) -> None:
    lead_id = await lead_id_of(admin_db, psid)
    client = await as_role(role)
    resp = await _put(client, lead_id, status="lost", lost_reason="no_answer")
    assert resp.status_code == code, resp.text
    called = await client.post(f"/api/leads/{lead_id}/called", json={"called": True})
    assert called.status_code == code


async def test_write_needs_csrf(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    client = await as_role("s1")
    client.headers.pop("X-CSRF-Token")
    resp = await _put(client, lead_id, status="lost", lost_reason="price")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "csrf_failed"
