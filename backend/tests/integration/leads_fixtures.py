"""Fixture dùng chung cho test API khách: một workspace đủ 6 vai trò, 3 Trang, 4 khách.

- P1 (nhân viên s1, nhóm 1): khách p1-a có SĐT, chưa trả lời; khách p1-b đã trả lời, quá 48 giờ.
- P2 (nhân viên s2, nhóm 2): khách p2-a có SĐT.
- P3 (trưởng nhóm 1 tự phụ trách): khách p3-a.
"""

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

NOW = dt.datetime.now(dt.UTC)


@dataclass
class Org:
    accounts: dict[str, f.Account]
    fb: dict[str, str]  # tên Trang → fb_page_id


async def send(fb: str, *items: dict[str, Any]) -> None:
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
    await send(fb["P1"], p.inbound(fb["P1"], "p1-a", "m-p1-a", NOW - 3 * h, "số em 0912 345 218"))
    # P1: khách đã được trả lời, quá 48 giờ chưa có kết quả.
    await send(
        fb["P1"],
        p.inbound(fb["P1"], "p1-b", "m-p1-b", NOW - 72 * h, "hỏi giá"),
        p.echo(fb["P1"], "p1-b", "m-p1-b-r", NOW - 71 * h, "dạ"),
    )
    # P2 và P3: mỗi Trang một khách.
    await send(fb["P2"], p.inbound(fb["P2"], "p2-a", "m-p2-a", NOW - 2 * h, "0387654321"))
    await send(fb["P3"], p.inbound(fb["P3"], "p3-a", "m-p3-a", NOW - 1 * h, "xin chào"))
    return Org(acc, fb)


@pytest.fixture
async def as_role(client: httpx.AsyncClient, org: Org) -> AsyncIterator[Any]:
    async def login(role: str) -> httpx.AsyncClient:
        client.cookies.clear()
        await f.login(client, org.accounts[role])
        return client

    yield login


async def lead_id_of(admin_db: AsyncSession, psid: str) -> str:
    lead_id = await admin_db.scalar(
        select(Lead.id).join(Contact, Contact.id == Lead.contact_id).where(Contact.psid == psid)
    )
    assert lead_id is not None
    return str(lead_id)
