"""Lệnh giả lập: toàn bộ kịch bản trong fixture phải ra đúng số phút.

Chạy trong tiến trình test: POST qua ASGI vào app thật, worker arq chạy chế độ burst.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from arq.worker import Worker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import admin_sessionmaker
from app.core.queue import close_queue, get_queue
from app.meta.signature import SIGNATURE_HEADER
from app.mock.seed import DEMO_PAGES, ensure_demo_workspace, load_demo_workspace
from app.mock.simulate import Simulator, load_scenarios, main
from app.workers.meta_sync import sync_meta
from app.workers.settings import WorkerSettings

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _fresh_queue() -> AsyncIterator[None]:
    yield
    await close_queue()


async def _simulator(client: httpx.AsyncClient, admin_db: AsyncSession) -> Simulator:
    await ensure_demo_workspace(admin_db)
    await admin_db.commit()
    demo = await load_demo_workspace(admin_db)
    assert demo is not None
    await sync_meta({})  # như `make seed` / `make simulate`: có quảng cáo để gắn chiến dịch
    queue = await get_queue()

    async def post(body: bytes, signature: str) -> int:
        resp = await client.post(
            "/webhooks/meta",
            content=body,
            headers={"Content-Type": "application/json", SIGNATURE_HEADER: signature},
        )
        return resp.status_code

    async def wait(_job_id: str) -> None:
        worker = Worker(
            functions=WorkerSettings.functions, redis_pool=queue, burst=True, poll_delay=0.01
        )
        # Không gọi worker.close(): nó đóng luôn pool hàng đợi dùng chung của test.
        await worker.main()

    return Simulator(
        demo, admin_sessionmaker(), post, wait, get_settings().meta_app_secret.get_secret_value()
    )


async def test_all_scenarios_pass(client: httpx.AsyncClient, admin_db: AsyncSession) -> None:
    sim = await _simulator(client, admin_db)
    scenarios = load_scenarios()
    assert {sc["page"] for sc in scenarios} == {name for _, name, _ in DEMO_PAGES}
    checks = await sim.run_all(scenarios)
    failed = [c for c in checks if not c.ok]
    assert not failed, failed
    assert len(checks) == sum(len(sc["expect"]) for sc in scenarios)


async def test_rerun_uses_new_customers(client: httpx.AsyncClient, admin_db: AsyncSession) -> None:
    sim = await _simulator(client, admin_db)
    only = load_scenarios(["in_hours"])
    assert all(c.ok for c in await sim.run_all(only))
    again = await _simulator(client, admin_db)
    assert again.run_id != sim.run_id
    assert all(c.ok for c in await again.run_all(only))


async def test_seed_is_idempotent(admin_db: AsyncSession) -> None:
    first = await ensure_demo_workspace(admin_db)
    second = await ensure_demo_workspace(admin_db)
    assert {n: pg.id for n, pg in first.pages.items()} == {
        n: pg.id for n, pg in second.pages.items()
    }


async def test_refuses_outside_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "mock_mode", False)
    assert await main([]) == 2


async def test_refuses_without_seed() -> None:
    assert await main(["--url", "http://127.0.0.1:9/webhooks/meta"]) == 2
