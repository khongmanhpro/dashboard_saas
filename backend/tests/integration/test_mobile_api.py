"""API ứng dụng điện thoại: khách của tôi, ba tab, nhắc thủ công, hộp nhắc việc, đăng ký đẩy."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationType, PushSubscription
from tests.integration.leads_fixtures import lead_id_of

pytestmark = pytest.mark.integration


async def _tab(client: Any, tab: str) -> list[dict[str, Any]]:
    resp = await client.get("/api/m/leads", params={"tab": tab})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_home_and_tabs_show_only_my_leads(as_role: Any, admin_db: AsyncSession) -> None:
    s1 = await as_role("s1")
    home = (await s1.get("/api/m/home")).json()
    assert home["pages"] == ["[P1]"]
    assert home["tabs"] == {"todo": 2, "callback": 0, "done": 0}
    assert home["phone_not_called"] == 1
    assert home["unread"] == 0 and home["score"] is None

    todo = await _tab(s1, "todo")
    # Quá hạn 48 giờ đứng trước khách chưa trả lời.
    assert [x["id"] for x in todo] == [
        await lead_id_of(admin_db, "p1-b"),
        await lead_id_of(admin_db, "p1-a"),
    ]
    assert todo[1]["snippet"] == "số em 0912 345 218"
    assert todo[1]["waiting_business_seconds"] is not None

    manager = await as_role("manager")
    assert await _tab(manager, "todo") == []  # /m chỉ hiện khách của chính mình


async def test_results_move_leads_between_tabs(as_role: Any, admin_db: AsyncSession) -> None:
    s1 = await as_role("s1")
    a, b = await lead_id_of(admin_db, "p1-a"), await lead_id_of(admin_db, "p1-b")
    later = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=3)).isoformat()
    assert (
        await s1.put(f"/api/leads/{a}/result", json={"status": "callback", "callback_at": later})
    ).status_code == 200
    assert (
        await s1.put(f"/api/leads/{b}/result", json={"status": "won", "won_value_vnd": 850_000})
    ).status_code == 200
    assert await _tab(s1, "todo") == []
    assert [x["id"] for x in await _tab(s1, "callback")] == [a]
    done = await _tab(s1, "done")
    assert [x["id"] for x in done] == [b] and done[0]["won_value_vnd"] == 850_000
    home = (await s1.get("/api/m/home")).json()
    assert home["tabs"] == {"todo": 0, "callback": 1, "done": 1}


async def test_home_score_after_recompute(as_role: Any) -> None:
    owner = await as_role("owner")
    assert (await owner.post("/api/score/recompute")).status_code == 200
    s1 = await as_role("s1")
    score = (await s1.get("/api/m/home")).json()["score"]
    assert (
        score["insufficient_data"] is True and score["lead_count"] == 2 and score["min_leads"] == 10
    )


@pytest.mark.parametrize(
    ("role", "psid", "code"),
    [
        ("lead", "p1-a", 204),  # khách của nhân viên trong nhóm
        ("lead", "p2-a", 404),  # nhóm khác
        ("manager", "p2-a", 204),
        ("s1", "p1-a", 403),
        ("viewer", "p1-a", 403),
    ],
)
async def test_manual_reminder_permissions(
    as_role: Any, admin_db: AsyncSession, role: str, psid: str, code: int
) -> None:
    client = await as_role(role)
    resp = await client.post(f"/api/leads/{await lead_id_of(admin_db, psid)}/remind")
    assert resp.status_code == code, resp.text


async def test_manual_reminder_reaches_owner_inbox(as_role: Any, admin_db: AsyncSession) -> None:
    lead_id = await lead_id_of(admin_db, "p1-a")
    leader = await as_role("lead")
    detail = (await leader.get(f"/api/leads/{lead_id}")).json()
    assert detail["permissions"]["can_remind"] is True
    assert (await leader.post(f"/api/leads/{lead_id}/remind")).status_code == 204
    again = await leader.post(f"/api/leads/{lead_id}/remind")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "reminder_too_soon"

    s2 = await as_role("s2")
    assert (await s2.get("/api/notifications")).json() == {"items": [], "unread": 0}

    s1 = await as_role("s1")
    inbox = (await s1.get("/api/notifications")).json()
    assert inbox["unread"] == 1
    item = inbox["items"][0]
    assert item["type"] == NotificationType.MANUAL.value and item["lead_id"] == lead_id
    assert "0912" not in item["body"] and "nhắc bạn xử lý" in item["body"]
    assert (await s1.get("/api/m/home")).json()["unread"] == 1
    assert (await s1.post(f"/api/notifications/{item['id']}/read")).status_code == 204
    assert (await s1.get("/api/notifications")).json()["unread"] == 0

    s2 = await as_role("s2")
    assert (await s2.post(f"/api/notifications/{item['id']}/read")).status_code == 404
    row = await admin_db.scalar(select(Notification).where(Notification.id == item["id"]))
    assert row is not None and row.actor_member_id is not None


async def test_push_subscription_lifecycle(as_role: Any, admin_db: AsyncSession, org: Any) -> None:
    s1 = await as_role("s1")
    assert (await s1.get("/api/push/config")).json() == {"enabled": False, "public_key": None}
    body = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "k", "auth": "a"},
        "expirationTime": None,
    }
    assert (await s1.post("/api/push/subscriptions", json=body)).status_code == 204
    assert (await s1.post("/api/push/subscriptions", json=body)).status_code == 204
    rows = (await admin_db.scalars(select(PushSubscription))).all()
    assert len(rows) == 1 and rows[0].member_id == org.accounts["s1"].member.id
    for endpoint in (
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://push.example/abc",
        "https://10.0.0.5/noi-bo",
        "https://fcm.googleapis.com:8443/fcm/send/abc",
    ):
        bad = {**body, "endpoint": endpoint}
        assert (await s1.post("/api/push/subscriptions", json=bad)).status_code == 422, endpoint
    assert (
        await s1.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]})
    ).status_code == 204
    admin_db.expire_all()
    assert (await admin_db.scalars(select(PushSubscription))).all() == []
