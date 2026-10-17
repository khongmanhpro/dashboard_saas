"""DB riêng cho giả lập và e2e (decisions.md mục L): dọn được sau khi chạy, không đụng DB dev."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.mock import sandbox

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("url", "index"),
    [("redis://redis:6379/13", 13), ("redis://redis:6379/0", 0), ("redis://redis:6379", 0)],
)
def test_redis_db_index(url: str, index: int) -> None:
    assert sandbox.redis_db_index(url) == index


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("postgres_db", "fanpage"),
        ("redis_url", "redis://redis:6379/0"),
        ("redis_url", "redis://redis:6379"),
    ],
)
async def test_drop_refuses_dev_database_or_redis(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    monkeypatch.setattr(get_settings(), field, value)
    with pytest.raises(SystemExit, match="Từ chối"):
        await sandbox.drop()


async def test_drop_removes_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "fanpage_sandbox_drop_test"
    pytest_db = get_settings().postgres_db
    await sandbox.ensure_database(name)
    monkeypatch.setattr(get_settings(), "postgres_db", name)
    await sandbox.drop()
    conn = await sandbox._admin_connect()
    try:
        assert await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name) is None
        # DB của pytest vẫn còn nguyên.
        assert await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", pytest_db)
    finally:
        await conn.close()
