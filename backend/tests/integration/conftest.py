"""Fixture cho test tích hợp: DB test tạo mới mỗi lần chạy, dọn dữ liệu sau mỗi test."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic import command
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import admin_sessionmaker, dispose_engines, get_admin_engine
from app.core.redis import close_redis, get_redis
from app.mock.sandbox import alembic_config, ensure_database
from app.models import Base

# Fixture dữ liệu khách dùng chung cho nhiều file test (org, as_role).
from tests.integration.leads_fixtures import as_role, org  # noqa: F401
from tests.integration.report_fixtures import as_user, demo  # noqa: F401


def admin_url_for(database: str) -> str:
    base = get_settings().database_admin_url
    return base.rsplit("/", 1)[0] + "/" + database


async def recreate_database(name: str) -> None:
    """Chỉ nhận DB tên kết thúc `_test` (app.mock.sandbox chặn)."""
    await ensure_database(name, recreate=True)


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[None]:
    s = get_settings()
    await recreate_database(s.postgres_db)
    await asyncio.to_thread(command.upgrade, alembic_config(s.database_admin_url), "head")
    yield
    await dispose_engines()


@pytest.fixture(autouse=True)
async def _clean_state(database: None) -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with get_admin_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()
    await close_redis()


@pytest.fixture
async def admin_db() -> AsyncIterator[AsyncSession]:
    """Session quản trị (bỏ qua RLS) để chuẩn bị dữ liệu cho test."""
    async with admin_sessionmaker()() as session:
        yield session


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    yield get_redis()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
