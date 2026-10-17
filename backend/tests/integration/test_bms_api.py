"""Kết nối BM, gán Trang, job kiểm tra 6 giờ (Bước 6). Dùng client Graph giả (MOCK_MODE)."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_token_cipher
from app.meta.events import WebhookPayload
from app.mock import payloads as p
from app.models import (
    AdAccount,
    AuditLog,
    BusinessManager,
    ConnectionStatus,
    Contact,
    Lead,
    LeadgenFetchStatus,
    LeadgenSubmission,
    LeadSource,
    Notification,
    Page,
    SyncRun,
)
from app.workers.meta_checks import check_bms
from app.workers.webhook import process_webhook
from tests.integration import factories as f

pytestmark = pytest.mark.integration

BM2 = "MOCK-BM-2"
BM2_PAGES = {"100000000000105", "100000000000106", "100000000000107"}


async def _connect(client: Any, token: str, **extra: Any) -> Any:
    return await client.post("/api/bms", json={"token": token, **extra})


async def test_check_reads_meta_without_saving(as_role: Any, admin_db: AsyncSession) -> None:
    owner = await as_role("owner")
    resp = await owner.post("/api/bms/check", json={"token": BM2})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["business_name"] == "[BM Demo Miền Nam]"
    assert body["can_save"] is True and body["missing_scopes"] == []
    assert {pg["fb_page_id"] for pg in body["pages"]} == BM2_PAGES
    assert all(pg["state"] == "new" for pg in body["pages"])
    assert [c["key"] for c in body["checks"]] == [
        "token_valid",
        "pages",
        "webhooks",
        "ad_accounts",
        "leadgen",
    ]
    saved = await admin_db.scalar(
        select(BusinessManager).where(BusinessManager.fb_business_id == "900000000000002")
    )
    assert saved is None


async def test_connect_second_bm_without_code_changes(
    as_role: Any, admin_db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    owner = await as_role("owner")
    before = (await owner.get("/api/bms")).json()
    with caplog.at_level(logging.DEBUG):
        resp = await _connect(owner, BM2, name="[BM Miền Nam]")
        second = await _connect(owner, "MOCK-BM-NOLEADS")
    assert resp.status_code == 201, resp.text
    assert BM2 not in resp.text and "MOCK-PAGE" not in resp.text
    out = resp.json()
    assert out["name"] == "[BM Miền Nam]" and out["token_last4"] == "BM-2"
    assert out["status"] == "active" and out["page_count"] == 3 and out["ad_account_count"] == 1
    assert second.status_code == 201 and second.json()["status"] == "missing_permissions"
    assert second.json()["missing_scopes"] == ["leads_retrieval"]

    bm = await admin_db.scalar(
        select(BusinessManager).where(BusinessManager.fb_business_id == "900000000000002")
    )
    assert bm is not None and bm.token_ciphertext is not None
    assert BM2.encode() not in bm.token_ciphertext
    assert get_token_cipher().decrypt(bm.token_ciphertext) == BM2
    pages = (await admin_db.scalars(select(Page).where(Page.business_manager_id == bm.id))).all()
    assert {pg.fb_page_id for pg in pages} == BM2_PAGES
    assert all(
        pg.is_tracked and pg.webhook_subscribed_at and pg.page_token_ciphertext for pg in pages
    )
    assert (await admin_db.scalars(select(AdAccount.fb_ad_account_id))).all() == [
        "act_200000000000003"
    ]
    audits = (
        await admin_db.scalars(select(AuditLog).where(AuditLog.entity_type == "business_manager"))
    ).all()
    assert [a.action for a in audits] == ["bm.connected", "bm.connected"]
    assert BM2 not in str([(a.before, a.after) for a in audits])
    assert BM2 not in caplog.text

    overview = (await owner.get("/api/bms")).json()
    assert (
        len(overview["bms"]) == len(before["bms"]) + 2
        and overview["tracked_pages"] == before["tracked_pages"] + 4
        and overview["unassigned_pages"] == before["unassigned_pages"] + 4
    )

    # Webhook vào Trang mới được định tuyến về workspace này; gán người rồi khách mới tính cho họ.
    pages_list = (await owner.get("/api/pages")).json()
    page5 = next(pg for pg in pages_list["pages"] if pg["fb_page_id"] == "100000000000105")
    assert page5["is_new"] and page5["owner"] is None
    s1_id = (await owner.get("/api/me")).json()  # chỉ để chắc phiên còn
    assert s1_id
    staff = next(c for c in pages_list["candidates"] if c["name"].startswith("[Nhân viên"))
    assert (
        await owner.put(f"/api/pages/{page5['id']}/owner", json={"member_id": staff["id"]})
    ).status_code == 204
    now = dt.datetime.now(dt.UTC)
    await process_webhook(
        {"job_try": 1},
        WebhookPayload(
            p.page_payload(
                "100000000000105", messaging=[p.inbound("100000000000105", "bm2-a", "m-bm2-a", now)]
            )
        ),
    )
    lead = await admin_db.scalar(select(Lead).join(Contact).where(Contact.psid == "bm2-a"))
    assert lead is not None and str(lead.owner_member_id) == staff["id"]
    contact = await admin_db.scalar(select(Contact).where(Contact.psid == "bm2-a"))
    assert contact is not None and contact.display_name == "[Khách m2-a]"  # tên lấy qua Graph (giả)


async def test_invalid_token_and_permissions(as_role: Any) -> None:
    owner = await as_role("owner")
    bad = await _connect(owner, "MOCK-INVALID")
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "bm_token_invalid"
    assert "MOCK-INVALID" not in bad.text
    manager = await as_role("manager")
    assert (await manager.get("/api/bms")).json()["can_connect"] is False
    assert (await manager.post("/api/bms/check", json={"token": BM2})).status_code == 403
    assert (await _connect(manager, BM2)).status_code == 403
    staff = await as_role("s1")
    assert (await staff.get("/api/bms")).status_code == 403
    assert (await staff.get("/api/pages")).status_code == 403


async def test_page_tracked_by_other_workspace_is_not_taken(
    as_role: Any, admin_db: AsyncSession
) -> None:
    other = await f.create_workspace(admin_db)
    other_bm = await f.create_business_manager(admin_db, other)
    await f.create_page(admin_db, other, bm=other_bm, fb_page_id="100000000000106")
    other_id = other.id
    await admin_db.commit()
    owner = await as_role("owner")
    check = (await owner.post("/api/bms/check", json={"token": BM2})).json()
    states = {pg["fb_page_id"]: pg["state"] for pg in check["pages"]}
    assert states["100000000000106"] == "other_workspace"
    assert (await _connect(owner, BM2)).json()["page_count"] == 2
    pages = (await owner.get("/api/pages")).json()["pages"]
    taken = [pg for pg in pages if pg["fb_page_id"] == "100000000000106"]
    # "Đang được workspace khác theo dõi": không theo dõi, không đụng bản của workspace kia.
    assert [(pg["is_tracked"], pg["untracked_reason"]) for pg in taken] == [
        (False, "other_workspace")
    ]
    theirs = await admin_db.scalar(
        select(Page).where(Page.fb_page_id == "100000000000106", Page.is_tracked.is_(True))
    )
    assert theirs is not None and theirs.workspace_id == other_id


async def test_rotate_and_disconnect(as_role: Any, admin_db: AsyncSession) -> None:
    owner = await as_role("owner")
    bm_id = (await _connect(owner, BM2)).json()["id"]
    wrong = await owner.put(f"/api/bms/{bm_id}/token", json={"token": "MOCK-BM-1"})
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "bm_token_other_business"
    same = await owner.put(f"/api/bms/{bm_id}/token", json={"token": BM2})
    assert same.status_code == 200
    gone = await owner.post(f"/api/bms/{bm_id}/disconnect")
    assert (
        gone.status_code == 200
        and gone.json()["status"] == "disconnected"
        and gone.json()["token_last4"] is None
    )
    admin_db.expire_all()
    pages = (await admin_db.scalars(select(Page).where(Page.fb_page_id.in_(BM2_PAGES)))).all()
    assert len(pages) == 3 and all(
        not pg.is_tracked
        and pg.untracked_reason == "bm_disconnected"
        and pg.page_token_ciphertext is None
        for pg in pages
    )


async def test_assign_rules(as_role: Any, org: Any) -> None:
    owner = await as_role("owner")
    await _connect(owner, BM2)
    listing = (await owner.get("/api/pages")).json()
    new_pages = [pg for pg in listing["pages"] if pg["fb_page_id"] in BM2_PAGES]
    s1 = org.accounts["s1"].member.id  # s1 đã phụ trách [P1]
    conflict = await owner.put(
        f"/api/pages/{new_pages[0]['id']}/owner", json={"member_id": str(s1)}
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["detail"]["code"] == "member_already_has_page"
    )
    viewer = org.accounts["viewer"].member.id
    assert (
        await owner.put(f"/api/pages/{new_pages[0]['id']}/owner", json={"member_id": str(viewer)})
    ).status_code == 404
    assert str(s1) not in {c["id"] for c in listing["candidates"]}

    manager = await as_role("manager")
    lead_member = org.accounts["manager"].member.id
    assert (
        await manager.put(
            f"/api/pages/{new_pages[0]['id']}/owner", json={"member_id": str(lead_member)}
        )
    ).status_code == 204
    assert (
        await manager.put(f"/api/pages/{new_pages[0]['id']}/owner", json={"member_id": None})
    ).status_code == 204
    staff = await as_role("s1")
    assert (
        await staff.put(f"/api/pages/{new_pages[0]['id']}/owner", json={"member_id": None})
    ).status_code == 403


async def test_six_hour_job(as_role: Any, admin_db: AsyncSession, org: Any) -> None:
    owner_member_id = org.accounts["owner"].member.id
    owner = await as_role("owner")
    bm_id = (await _connect(owner, BM2)).json()["id"]
    bm = await admin_db.get(BusinessManager, bm_id)
    assert bm is not None
    page = await admin_db.scalar(select(Page).where(Page.fb_page_id == "100000000000107"))
    assert page is not None
    page.is_tracked = False
    page.untracked_reason = "removed_from_bm"
    # Form đang pending trên Trang có mã: job lấy bù.
    lead = Lead(
        workspace_id=bm.workspace_id,
        page_id=page.id,
        source=LeadSource.LEADGEN,
        first_inbound_at=dt.datetime.now(dt.UTC),
        result_due_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=48),
    )
    admin_db.add(lead)
    await admin_db.flush()
    lead_id, page_id = lead.id, page.id
    admin_db.add(
        LeadgenSubmission(
            workspace_id=bm.workspace_id,
            leadgen_id="44700",
            page_id=page_id,
            created_time=dt.datetime.now(dt.UTC),
            fetch_status=LeadgenFetchStatus.PENDING,
            lead_id=lead_id,
        )
    )
    await admin_db.commit()

    result = await check_bms({})
    assert result["checked"] >= 1 and result["leadgen_fetched"] == 1 and result["failed"] == 0
    admin_db.expire_all()
    assert (await admin_db.get(Page, page_id)).is_tracked  # type: ignore[union-attr]
    refreshed = await admin_db.get(Lead, lead_id)
    assert refreshed is not None and refreshed.phone == "0900000142"
    runs = (
        await admin_db.scalars(select(SyncRun.kind).where(SyncRun.business_manager_id == bm_id))
    ).all()
    assert "connect" in runs and "health_check" in runs

    # Mã bị thu hồi: BM thành Mất kết nối, Chủ sở hữu nhận nhắc việc trong app.
    bm = await admin_db.get(BusinessManager, bm_id)
    assert bm is not None
    bm.token_ciphertext = get_token_cipher().encrypt("MOCK-INVALID")
    await admin_db.commit()
    result = await check_bms({})
    assert result["worse"] == 1
    admin_db.expire_all()
    bm = await admin_db.get(BusinessManager, bm_id)
    assert bm is not None and bm.status == ConnectionStatus.DISCONNECTED
    notice = await admin_db.scalar(
        select(Notification).where(Notification.member_id == owner_member_id)
    )
    assert notice is not None and "mất kết nối" in notice.body
