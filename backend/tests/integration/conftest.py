"""Fixture cho test tích hợp: DB test tạo mới mỗi lần chạy, dọn dữ liệu sau mỗi test."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import admin_sessionmaker, dispose_engines, get_admin_engine
from app.core.redis import close_redis, get_redis
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def admin_url_for(database: str) -> str:
    base = get_settings().database_admin_url
    return base.rsplit("/", 1)[0] + "/" + database


async def _admin_connect() -> asyncpg.Connection:
    s = get_settings()
    return await asyncpg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password.get_secret_value(),
        database="postgres",
    )


async def recreate_database(name: str) -> None:
    # Chặn tuyệt đối việc xóa nhầm DB dev hoặc production.
    assert name.endswith("_test"), f"Từ chối xóa DB không phải DB test: {name}"
    s = get_settings()
    conn = await _admin_connect()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
        role = s.postgres_app_user
        if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
            await conn.execute(
                f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'
            )
        alter = await conn.fetchval(
            "SELECT format('ALTER ROLE %I WITH PASSWORD %L', $1::text, $2::text)",
            role,
            s.postgres_app_password.get_secret_value(),
        )
        await conn.execute(alter)
        await conn.execute(f'GRANT CONNECT ON DATABASE "{name}" TO "{role}"')
    finally:
        await conn.close()


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
