"""Xóa dữ liệu một khách theo yêu cầu (decisions.md mục U4): lệnh `delete-customer`."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.models import (
    AuditLog,
    Contact,
    Lead,
    LeadgenFetchStatus,
    LeadgenSubmission,
    LeadPhone,
    Message,
    Page,
    WebhookEvent,
)
from tests.integration.leads_fixtures import Org

pytestmark = pytest.mark.integration


async def _contacts(db: AsyncSession) -> set[str]:
    return set((await db.scalars(select(Contact.psid))).all())


async def _webhooks_with(db: AsyncSession, text: str) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(func.strpos(cast(WebhookEvent.payload, Text), text) > 0)
        )
        or 0
    )


async def _orphan_form(
    db: AsyncSession, org: Org, page_name: str, leadgen_id: str, phone: str
) -> None:
    page = await db.scalar(select(Page).where(Page.fb_page_id == org.fb[page_name]))
    assert page is not None
    db.add(
        LeadgenSubmission(
            workspace_id=page.workspace_id,
            leadgen_id=leadgen_id,
            page_id=page.id,
            created_time=dt.datetime.now(dt.UTC),
            field_data={"phone_number": phone, "full_name": "[Khách 1042]"},
            fetch_status=LeadgenFetchStatus.FETCHED,
        )
    )
    await db.commit()


async def test_delete_by_page_and_psid_removes_only_that_customer(
    admin_db: AsyncSession, org: Org
) -> None:
    assert await _webhooks_with(admin_db, '"p1-a"') > 0
    before_msgs = await admin_db.scalar(select(func.count()).select_from(Message))

    out = await cli.delete_customer(org.fb["P1"], "p1-a", None)

    assert "Đã xóa" in out and "p1-a" not in out and "0912345218" not in out
    admin_db.expire_all()
    assert await _contacts(admin_db) == {"p1-b", "p2-a", "p3-a"}
    assert await _webhooks_with(admin_db, '"p1-a"') == 0
    assert await _webhooks_with(admin_db, '"p1-b"') > 0
    assert await admin_db.scalar(select(func.count()).where(LeadPhone.phone == "0912345218")) == 0
    assert await admin_db.scalar(select(func.count()).where(Lead.phone == "0912345218")) == 0
    after_msgs = await admin_db.scalar(select(func.count()).select_from(Message))
    assert after_msgs == before_msgs - 1

    audit = (
        await admin_db.scalars(select(AuditLog).where(AuditLog.action == "customer.erase"))
    ).all()
    assert len(audit) == 1
    logged = json.dumps(audit[0].after)
    assert audit[0].after["contacts"] == 1
    assert "p1-a" not in logged and "0912345218" not in logged


async def test_delete_by_phone_any_format_and_orphan_form(admin_db: AsyncSession, org: Org) -> None:
    await _orphan_form(admin_db, org, "P2", "lg-1", "+84 387 654 321")
    await _orphan_form(admin_db, org, "P2", "lg-2", "0901 222 333")

    out = await cli.delete_customer(None, None, "+84387654321")

    assert "contacts: 1" in out and "leadgen_submissions: 1" in out
    admin_db.expire_all()
    assert await _contacts(admin_db) == {"p1-a", "p1-b", "p3-a"}
    left = set((await admin_db.scalars(select(LeadgenSubmission.leadgen_id))).all())
    assert left == {"lg-2"}


async def test_not_found_deletes_nothing(admin_db: AsyncSession, org: Org) -> None:
    out = await cli.delete_customer(org.fb["P1"], "khong-co", None)
    assert "Không tìm thấy" in out
    admin_db.expire_all()
    assert len(await _contacts(admin_db)) == 4
    assert (
        await admin_db.scalar(select(func.count()).where(AuditLog.action == "customer.erase")) == 0
    )


@pytest.mark.parametrize(
    ("page", "psid", "phone", "message"),
    [
        (None, "p1-a", None, "--page"),
        (None, None, "12345", "không hợp lệ"),
        (None, None, None, "đúng một"),
        ("x", "p1-a", "0912345218", "đúng một"),
    ],
)
async def test_rejects_bad_input(
    org: Org, page: str | None, psid: str | None, phone: str | None, message: str
) -> None:
    with pytest.raises(cli.CliError, match=message):
        await cli.delete_customer(page, psid, phone)
