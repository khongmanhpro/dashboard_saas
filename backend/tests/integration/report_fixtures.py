"""Fixture dùng chung cho test Bước 7: BM demo đã đồng bộ, 2 nhóm, khách từ quảng cáo."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ad, MemberRole, Page
from app.services.assignment import assign_page
from app.workers.meta_sync import sync_meta
from app.workers.scoring import nightly_scores
from tests.integration import factories as f

NOW = dt.datetime.now(dt.UTC)
SOFTWARE, FISS, RABBIT, SMART = (
    "100000000000101",
    "100000000000102",
    "100000000000103",
    "100000000000104",
)


@dataclass
class Demo:
    accounts: dict[str, f.Account]
    pages: dict[str, Page]
    campaign_id: str


@pytest.fixture
async def demo(admin_db: AsyncSession) -> Demo:
    """BM demo đã đồng bộ. Nhóm 1: s1 (Phần Mềm), trưởng nhóm (Shop Thỏ). Nhóm 2: s2 (FISS).
    Mua Sắm Thông Minh chưa có người phụ trách.

    - FISS: 12 khách từ QC "[Tin nhắn - Giải pháp tài chính]" trong 3 ngày qua, chốt 4 × 2 triệu.
    - Phần Mềm: 10 khách tự nhiên, chốt 2 × 1 triệu, có SĐT 5.
    """
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
    await f.connect_mock_bm(admin_db, ws)
    pages = {p.fb_page_id: p for p in await admin_db.scalars(select(Page))}
    since = NOW - dt.timedelta(days=40)
    for fb, who in ((SOFTWARE, "s1"), (FISS, "s2"), (RABBIT, "lead")):
        await assign_page(admin_db, pages[fb], acc[who].member, since)
    await admin_db.commit()
    await sync_meta({})

    ad = await admin_db.scalar(select(Ad).where(Ad.fb_ad_id == "23800000000000101"))
    assert ad is not None
    for i in range(12):
        lead = await f.create_lead(
            admin_db,
            pages[FISS],
            acc["s2"].member,
            NOW - dt.timedelta(hours=2 + i * 5),
            phone="0912345678" if i < 8 else None,
            won_value_vnd=2_000_000 if i < 4 else None,
        )
        lead.fb_ad_id, lead.ad_id, lead.campaign_id = ad.fb_ad_id, ad.id, ad.campaign_id
    for i in range(10):
        await f.create_lead(
            admin_db,
            pages[SOFTWARE],
            acc["s1"].member,
            NOW - dt.timedelta(hours=1 + i * 6),
            phone="0987654321" if i < 5 else None,
            won_value_vnd=1_000_000 if i < 2 else None,
        )
    await admin_db.commit()
    await nightly_scores({}, now=NOW)
    return Demo(acc, pages, str(ad.campaign_id))


@pytest.fixture
async def as_user(client: httpx.AsyncClient, demo: Demo) -> AsyncIterator[Any]:
    async def login(role: str) -> httpx.AsyncClient:
        client.cookies.clear()
        await f.login(client, demo.accounts[role])
        return client

    yield login
