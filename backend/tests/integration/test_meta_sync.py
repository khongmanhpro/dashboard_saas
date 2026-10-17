"""Đồng bộ mỗi giờ (Bước 7): quảng cáo 3 cấp, tỉ giá, gắn khách với QC, bài đăng, số liệu Trang."""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_token_cipher
from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.meta.events import WebhookPayload
from app.meta.graph import GraphError, MockGraphClient, set_graph
from app.mock import payloads as p
from app.models import (
    Ad,
    AdAccount,
    AdInsightDaily,
    Campaign,
    ConnectionStatus,
    FxRate,
    Lead,
    Page,
    PageInsightDaily,
    PagePost,
    SyncRun,
    Workspace,
)
from app.services import meta_sync
from app.services.bm_service import sync_bm
from app.workers.meta_sync import sync_meta
from app.workers.webhook import process_webhook
from tests.integration import factories as f

pytestmark = pytest.mark.integration

TOKEN = "MOCK-BM-1"  # mã giả của client Graph giả
FISS = "100000000000102"
FISS_AD = "23800000000000101"
NOW = dt.datetime.now(dt.UTC)


async def _demo_workspace(admin_db: AsyncSession) -> Workspace:
    """Workspace có BM demo (MOCK-BM-1): 4 Trang có mã Trang, 2 tài khoản QC (VND và USD)."""
    ws = await f.create_workspace(admin_db)
    bm = await f.create_business_manager(admin_db, ws)
    bm.fb_business_id = "900000000000000"
    bm.token_ciphertext = get_token_cipher().encrypt(TOKEN)
    await sync_bm(admin_db, bm, NOW, MockGraphClient(), kind="test")
    await admin_db.commit()
    return ws


async def _count(admin_db: AsyncSession, model: Any, *where: Any) -> int:
    return int(await admin_db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_sync_stores_three_levels_and_converts_currency(
    admin_db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await _demo_workspace(admin_db)
    with caplog.at_level(logging.DEBUG):
        totals = await sync_meta({})
    assert totals["workspaces"] == 1 and totals["failed"] == 0
    assert totals["ad_accounts"] == 2 and totals["pages"] == 4
    assert TOKEN not in caplog.text and "MOCK-PAGE" not in caplog.text

    assert await _count(admin_db, Campaign) == 5
    ad = await admin_db.scalar(select(Ad).where(Ad.fb_ad_id == FISS_AD))
    page = await admin_db.scalar(select(Page).where(Page.fb_page_id == FISS))
    assert ad is not None and page is not None and ad.page_id == page.id

    # Ba cấp cộng lại bằng nhau; lần đầu lấy bù 30 ngày.
    spend = {
        level: await admin_db.scalar(
            select(func.sum(AdInsightDaily.spend_minor)).where(AdInsightDaily.level == level)
        )
        for level in ("campaign", "adset", "ad")
    }
    assert len(set(spend.values())) == 1 and spend["ad"]
    days = await admin_db.scalar(select(func.count(func.distinct(AdInsightDaily.date))))
    assert days == 30

    # VND: spend_vnd = spend_minor. USD chưa có tỉ giá: NULL.
    vnd = (
        await admin_db.execute(
            select(AdInsightDaily.spend_minor, AdInsightDaily.spend_vnd).where(
                AdInsightDaily.currency == "VND"
            )
        )
    ).all()
    assert vnd and all(minor == v for minor, v in vnd)
    assert await _count(admin_db, AdInsightDaily, AdInsightDaily.currency == "USD") > 0
    assert (
        await _count(
            admin_db,
            AdInsightDaily,
            AdInsightDaily.currency == "USD",
            AdInsightDaily.spend_vnd.is_not(None),
        )
        == 0
    )

    # Chủ sở hữu nhập tỉ giá: tính lại spend_vnd của mọi dòng USD.
    ws_id = await admin_db.scalar(select(Workspace.id))
    admin_db.add(
        FxRate(
            workspace_id=ws_id,
            currency="USD",
            effective_from=dt.date(2020, 1, 1),
            vnd_per_unit=Decimal("25000"),
        )
    )
    await admin_db.commit()
    async with app_sessionmaker()() as db:
        await set_tenant(db, TenantContext(workspace_id=ws_id, user_id=None))
        await meta_sync.apply_fx(db, "USD")
        await db.commit()
    usd = (
        await admin_db.execute(
            select(AdInsightDaily.spend_minor, AdInsightDaily.spend_vnd).where(
                AdInsightDaily.currency == "USD"
            )
        )
    ).all()
    assert all(v == round(minor * 250) for minor, v in usd)

    run = await admin_db.scalar(select(SyncRun).where(SyncRun.kind == "hourly_sync"))
    assert run is not None and run.status == "ok"


async def test_results_depend_on_objective(admin_db: AsyncSession) -> None:
    await _demo_workspace(admin_db)
    await sync_meta({})
    rows = dict(
        (
            await admin_db.execute(
                select(Campaign.fb_campaign_id, func.sum(AdInsightDaily.results))
                .join(AdInsightDaily, AdInsightDaily.object_id == Campaign.id)
                .where(AdInsightDaily.level == "campaign")
                .group_by(Campaign.fb_campaign_id)
            )
        ).all()
    )
    assert rows["23800000000000003"] > 0  # form khách tiềm năng
    assert rows["23800000000000001"] > 0  # tin nhắn
    # Chiến dịch tương tác không có tin nhắn/form: "Kết quả" là "–" (NULL).
    assert rows["23800000000000004"] is None


async def test_paused_campaign_has_no_recent_spend(admin_db: AsyncSession) -> None:
    await _demo_workspace(admin_db)
    await sync_meta({})
    paused = await admin_db.scalar(
        select(Campaign.id).where(Campaign.fb_campaign_id == "23800000000000004")
    )
    latest = await admin_db.scalar(
        select(func.max(AdInsightDaily.date)).where(AdInsightDaily.campaign_id == paused)
    )
    assert latest is not None and latest <= dt.date.today() - dt.timedelta(days=9)


async def test_second_run_updates_without_duplicates(admin_db: AsyncSession) -> None:
    await _demo_workspace(admin_db)
    await sync_meta({})
    rows = await _count(admin_db, AdInsightDaily)
    posts = await _count(admin_db, PagePost)
    insights = await _count(admin_db, PageInsightDaily)
    await sync_meta({})
    assert await _count(admin_db, AdInsightDaily) == rows
    assert await _count(admin_db, PagePost) == posts
    assert await _count(admin_db, PageInsightDaily) == insights


async def test_leads_are_linked_to_ads(admin_db: AsyncSession) -> None:
    ws = await _demo_workspace(admin_db)
    page = await admin_db.scalar(select(Page).where(Page.fb_page_id == FISS))
    assert page is not None
    # Khách đến trước khi QC được đồng bộ: job gắn bù.
    early = await f.create_lead(admin_db, page, None, NOW - dt.timedelta(hours=5))
    early.fb_ad_id = FISS_AD
    await admin_db.commit()
    totals = await sync_meta({})
    assert totals["leads_linked"] == 1
    await admin_db.refresh(early)
    campaign = await admin_db.scalar(
        select(Campaign).where(Campaign.fb_campaign_id == "23800000000000002")
    )
    assert campaign is not None and early.campaign_id == campaign.id and early.ad_id is not None

    # Khách đến sau khi QC đã có: gắn ngay khi xử lý webhook.
    await process_webhook(
        {"job_try": 1},
        WebhookPayload(
            p.page_payload(
                FISS,
                messaging=[p.inbound(FISS, "psid-ad", "m-ad-1", NOW, "chào shop", ad_id=FISS_AD)],
            )
        ),
    )
    lead = await admin_db.scalar(
        select(Lead).where(
            Lead.workspace_id == ws.id, Lead.fb_ad_id == FISS_AD, Lead.id != early.id
        )
    )
    assert lead is not None and lead.campaign_id == campaign.id


async def test_posts_and_page_insights(admin_db: AsyncSession) -> None:
    await _demo_workspace(admin_db)
    await sync_meta({})
    page = await admin_db.scalar(select(Page).where(Page.fb_page_id == "100000000000101"))
    assert page is not None and page.content_synced_at is not None
    posts = list(await admin_db.scalars(select(PagePost).where(PagePost.page_id == page.id)))
    assert posts and all(len(post.excerpt or "") <= 200 for post in posts)
    assert all(post.created_time >= NOW - dt.timedelta(days=31) for post in posts)
    assert await _count(admin_db, PageInsightDaily, PageInsightDaily.page_id == page.id) == 30


class _NoAccess(MockGraphClient):
    """Tài khoản USD bị gỡ quyền: các tài khoản và Trang khác vẫn đồng bộ."""

    async def campaigns(self, token: str, account_id: str) -> Any:
        if account_id == "act_200000000000002":
            raise GraphError("permission", 200, 403)
        return await super().campaigns(token, account_id)


async def test_one_account_without_permission_does_not_block_others(
    admin_db: AsyncSession,
) -> None:
    await _demo_workspace(admin_db)
    set_graph(_NoAccess())
    try:
        totals = await sync_meta({})
    finally:
        set_graph(None)
    assert totals["ad_accounts"] == 1 and totals["pages"] == 4 and totals["failed"] == 1
    usd = await admin_db.scalar(
        select(AdAccount).where(AdAccount.fb_ad_account_id == "act_200000000000002")
    )
    assert usd is not None and usd.access_status == ConnectionStatus.MISSING_PERMISSIONS
    run = await admin_db.scalar(select(SyncRun).where(SyncRun.kind == "hourly_sync"))
    assert run is not None and run.status == "warning" and run.error == "ad_account:permission"


def test_fx_table_uses_latest_rate_before_day() -> None:
    fx = meta_sync.FxTable(
        [
            ("USD", dt.date(2026, 1, 1), Decimal("25000")),
            ("USD", dt.date(2026, 6, 1), Decimal("26000")),
        ]
    )
    assert fx.rate("USD", dt.date(2025, 12, 31)) is None
    assert fx.to_vnd(1000, "USD", dt.date(2026, 5, 31)) == 250_000
    assert fx.to_vnd(1000, "USD", dt.date(2026, 6, 1)) == 260_000
    assert fx.to_vnd(123_456, "VND", dt.date(2026, 6, 1)) == 123_456
    assert fx.to_vnd(5, "EUR", dt.date(2026, 6, 1)) is None
