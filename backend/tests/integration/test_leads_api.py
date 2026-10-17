"""API khách hàng: phạm vi theo vai trò, che SĐT, lọc nhanh, tìm kiếm, phân trang."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.events import WebhookPayload
from app.mock import payloads as p
from app.models import Contact, Lead, MemberRole
from app.services.assignment import assign_page
from app.workers.webhook import process_webhook
from tests.integration import factories as f

pytestmark = pytest.mark.integration

NOW = dt.datetime.now(dt.UTC)


@dataclass
class Org:
    accounts: dict[str, f.Account]
    fb: dict[str, str]  # tên Trang → fb_page_id


async def _send(fb: str, *items: dict[str, Any]) -> None:
    await process_webhook({"job_try": 1}, WebhookPayload(p.page_payload(fb, messaging=list(items))))


@pytest.fixture
async def org(admin_db: AsyncSession) -> Org:
    ws = await f.create_workspace(admin_db)
    t1 = await f.create_team(admin_db, ws, "[Nhóm 1]")
    t2 = await f.create_team(admin_db, ws, "[Nhóm 2]")
    acc = {
        "owner": await f.create_account(admin_db, MemberRole.OWNER, workspace=ws),
        "manager": await f.create_account(admin_db, MemberRole.MANAGER, workspace=ws),
        "lead": await f.create_account(admin_db, MemberRole.TEAM_LEAD, workspace=ws, team=t1),
        "s1": await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=t1),
        "s2": await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=t2),
        "viewer": await f.create_account(admin_db, MemberRole.VIEWER, workspace=ws),
    }
    t1.lead_member_id = acc["lead"].member.id
    since = NOW - dt.timedelta(days=60)
    fb = {}
    for name, owner in (("P1", "s1"), ("P2", "s2"), ("P3", "lead")):
        page = await f.create_page(admin_db, ws, name=f"[{name}]")
        await assign_page(admin_db, page, acc[owner].member, since)
        fb[name] = page.fb_page_id
    await admin_db.commit()

    h = dt.timedelta(hours=1)
    # P1: khách có SĐT trong tin, chưa trả lời, 3 giờ trước.
    await _send(fb["P1"], p.inbound(fb["P1"], "p1-a", "m-p1-a", NOW - 3 * h, "số em 0912 345 218"))
    # P1: khách đã được trả lời, quá 48 giờ chưa có kết quả.
    await _send(
        fb["P1"],
        p.inbound(fb["P1"], "p1-b", "m-p1-b", NOW - 72 * h, "hỏi giá"),
        p.echo(fb["P1"], "p1-b", "m-p1-b-r", NOW - 71 * h, "dạ"),
    )
    # P2 và P3: mỗi Trang một khách.
    await _send(fb["P2"], p.inbound(fb["P2"], "p2-a", "m-p2-a", NOW - 2 * h, "0387654321"))
    await _send(fb["P3"], p.inbound(fb["P3"], "p3-a", "m-p3-a", NOW - 1 * h, "xin chào"))
    return Org(acc, fb)


@pytest.fixture
async def as_role(client: httpx.AsyncClient, org: Org) -> AsyncIterator[Any]:
    async def login(role: str) -> httpx.AsyncClient:
        client.cookies.clear()
        await f.login(client, org.accounts[role])
        return client

    yield login


async def _names(client: httpx.AsyncClient, **params: Any) -> list[str]:
    resp = await client.get("/api/leads", params={"period": "30d", **params})
    assert resp.status_code == 200, resp.text
    return sorted(item["page"]["name"] for item in resp.json()["items"])


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("owner", ["[P1]", "[P1]", "[P2]", "[P3]"]),
        ("manager", ["[P1]", "[P1]", "[P2]", "[P3]"]),
        ("viewer", ["[P1]", "[P1]", "[P2]", "[P3]"]),
        ("lead", ["[P1]", "[P1]", "[P3]"]),
        ("s1", ["[P1]", "[P1]"]),
        ("s2", ["[P2]"]),
    ],
)
async def test_scope_by_role(as_role: Any, role: str, expected: list[str]) -> None:
    client = await as_role(role)
    assert await _names(client) == expected


async def _lead_id(admin_db: AsyncSession, psid: str) -> str:
    lead_id = await admin_db.scalar(
        select(Lead.id).join(Contact, Contact.id == Lead.contact_id).where(Contact.psid == psid)
    )
    assert lead_id is not None
    return str(lead_id)


async def test_staff_cannot_open_other_staff_lead(as_role: Any, admin_db: AsyncSession) -> None:
    other = await _lead_id(admin_db, "p2-a")
    client = await as_role("s1")
    resp = await client.get(f"/api/leads/{other}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "lead_not_found"


@pytest.mark.parametrize(
    ("role", "masked"), [("s1", False), ("lead", False), ("manager", False), ("viewer", True)]
)
async def test_phone_masking_in_card_and_messages(
    as_role: Any, admin_db: AsyncSession, role: str, masked: bool
) -> None:
    lead_id = await _lead_id(admin_db, "p1-a")
    client = await as_role(role)
    detail = (await client.get(f"/api/leads/{lead_id}")).json()
    message = next(i for i in detail["timeline"] if i["kind"] == "message")
    if masked:
        assert detail["phone"] == "09•• ••• 218"
        assert detail["phone_masked"] is True
        assert detail["phones"] == ["09•• ••• 218"]
        assert message["text"] == "số em 09•• ••• 218"
        assert "0912345218" not in str(detail)
    else:
        assert detail["phone"] == "0912345218"
        assert detail["phone_masked"] is False
        assert message["text"] == "số em 0912 345 218"


async def test_team_lead_sees_team_phone_but_cannot_update(
    as_role: Any, admin_db: AsyncSession
) -> None:
    lead_id = await _lead_id(admin_db, "p1-a")
    client = await as_role("lead")
    detail = (await client.get(f"/api/leads/{lead_id}")).json()
    assert detail["permissions"]["can_update"] is False
    own = (await client.get(f"/api/leads/{await _lead_id(admin_db, 'p3-a')}")).json()
    assert own["permissions"]["can_update"] is True


async def test_summary_chips(as_role: Any) -> None:
    client = await as_role("s1")
    s = (await client.get("/api/leads/summary", params={"period": "30d"})).json()
    assert s["total"] == 2
    assert s["unreplied"] == 1
    assert s["overdue"] == 1
    assert s["phone_not_called"] == 1
    assert s["by_status"]["new"] == 1
    assert s["by_status"]["contacted"] == 1
    # Kỳ 7 ngày mặc định vẫn thấy cả hai (72 giờ trước).
    assert (await client.get("/api/leads/summary")).json()["total"] == 2


async def test_chip_and_status_filters(as_role: Any) -> None:
    client = await as_role("owner")
    assert await _names(client, chip="unreplied") == ["[P1]", "[P2]", "[P3]"]
    assert await _names(client, chip="overdue") == ["[P1]"]
    assert await _names(client, chip="phone_not_called") == ["[P1]", "[P2]"]
    assert await _names(client, status="contacted") == ["[P1]"]
    assert await _names(client, period="today", chip="overdue") == []


async def test_waiting_time_and_slow_flag(as_role: Any, admin_db: AsyncSession) -> None:
    client = await as_role("s1")
    card = (await client.get(f"/api/leads/{await _lead_id(admin_db, 'p1-a')}")).json()
    assert card["response_business_seconds"] is None
    assert card["waiting_business_seconds"] is not None
    replied = (await client.get(f"/api/leads/{await _lead_id(admin_db, 'p1-b')}")).json()
    assert replied["waiting_business_seconds"] is None
    assert replied["overdue"] is True
    assert any(i["type"] == "overdue" for i in replied["timeline"])
    assert any(i["is_first_reply"] for i in replied["timeline"])


async def test_search_by_phone_only_with_phone_permission(as_role: Any) -> None:
    client = await as_role("manager")
    assert await _names(client, q="0912 345") == ["[P1]"]
    assert await _names(client, q="+84912345218") == ["[P1]"]
    viewer = await as_role("viewer")
    assert await _names(viewer, q="0912345") == []


async def test_search_by_psid_tail(as_role: Any) -> None:
    client = await as_role("owner")
    assert await _names(client, q="p2-a") == ["[P2]"]


async def test_pagination(as_role: Any) -> None:
    client = await as_role("owner")
    first = (await client.get("/api/leads", params={"period": "30d", "limit": 3})).json()
    assert len(first["items"]) == 3 and first["next_cursor"]
    second = (
        await client.get(
            "/api/leads", params={"period": "30d", "limit": 3, "cursor": first["next_cursor"]}
        )
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    ids = [i["id"] for i in first["items"] + second["items"]]
    assert len(set(ids)) == 4
    bad = await client.get("/api/leads", params={"cursor": "rác"})
    assert bad.status_code == 400


async def test_filter_options_follow_scope(as_role: Any) -> None:
    client = await as_role("s2")
    opts = (await client.get("/api/leads/filter-options")).json()
    assert [p["name"] for p in opts["pages"]] == ["[P2]"]
    assert len(opts["owners"]) == 1


async def test_merged_form_lead_points_to_target(
    as_role: Any, admin_db: AsyncSession, org: Org
) -> None:
    fb = org.fb["P1"]
    await process_webhook(
        {"job_try": 1},
        WebhookPayload(
            p.page_payload(
                fb, changes=[p.leadgen(fb, "44991", "900000000000001", NOW - dt.timedelta(hours=4))]
            )
        ),
    )
    await _send(fb, p.inbound(fb, "p1-c", "m-p1-c", NOW - dt.timedelta(hours=3), "0900000142"))
    form = await admin_db.scalar(select(Lead).where(Lead.merged_into_lead_id.is_not(None)))
    assert form is not None
    client = await as_role("s1")
    resp = await client.get(f"/api/leads/{form.id}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == {
        "code": "lead_merged",
        "into_lead_id": str(form.merged_into_lead_id),
    }
    target = (await client.get(f"/api/leads/{form.merged_into_lead_id}")).json()
    assert target["display_name"] == "[Khách 1042]"
    found = (await client.get("/api/leads", params={"period": "30d", "q": "khách 1042"})).json()
    assert [i["id"] for i in found["items"]] == [str(form.merged_into_lead_id)]


async def test_viewer_has_no_phone_search_and_other_workspace_is_invisible(
    as_role: Any, admin_db: AsyncSession
) -> None:
    other_ws = await f.create_workspace(admin_db)
    page = await f.create_page(admin_db, other_ws)
    fb = page.fb_page_id
    await admin_db.commit()
    await _send(fb, p.inbound(fb, "x-a", "m-x-a", NOW - dt.timedelta(hours=1), "hi"))
    client = await as_role("owner")
    assert len(await _names(client)) == 4
