"""Kết nối PostgreSQL.

- `app` engine dùng tài khoản ứng dụng, bị Row-Level Security giới hạn.
- `admin` engine dùng tài khoản quản trị, chỉ cho migration, CLI và test.

Ngữ cảnh tenant (`app.workspace_id`, `app.user_id`) được đặt bằng `set_config(..., true)`
ở đầu **mỗi** transaction, nên sau `commit()` vẫn giữ đúng workspace.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.core.config import get_settings

_SET_TENANT_SQL = text(
    "SELECT set_config('app.workspace_id', :workspace_id, true),"
    " set_config('app.user_id', :user_id, true)"
)
_TENANT_KEY = "tenant"


@dataclass(frozen=True, slots=True)
class TenantContext:
    workspace_id: uuid.UUID | None
    user_id: uuid.UUID | None


def _tenant_params(ctx: TenantContext) -> dict[str, str]:
    return {
        "workspace_id": str(ctx.workspace_id) if ctx.workspace_id else "",
        "user_id": str(ctx.user_id) if ctx.user_id else "",
    }


@event.listens_for(Session, "after_begin")
def _apply_tenant_on_begin(session: Session, _transaction: Any, connection: Any) -> None:
    ctx = session.info.get(_TENANT_KEY)
    if isinstance(ctx, TenantContext):
        connection.execute(_SET_TENANT_SQL, _tenant_params(ctx))


async def set_tenant(session: AsyncSession, ctx: TenantContext) -> None:
    """Gắn ngữ cảnh tenant cho session: áp dụng ngay và cho mọi transaction sau."""
    session.info[_TENANT_KEY] = ctx
    if session.in_transaction():
        await session.execute(_SET_TENANT_SQL, _tenant_params(ctx))


def _make_engine(url: str) -> AsyncEngine:
    # hide_parameters: lỗi SQL không kèm giá trị tham số (nội dung tin nhắn, SĐT) khi ghi log.
    return create_async_engine(
        url, pool_pre_ping=True, pool_size=10, max_overflow=10, hide_parameters=True
    )


@lru_cache
def get_app_engine() -> AsyncEngine:
    return _make_engine(get_settings().database_url)


@lru_cache
def get_admin_engine() -> AsyncEngine:
    return _make_engine(get_settings().database_admin_url)


@lru_cache
def _app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False)


def app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session của tài khoản ứng dụng (bị RLS). Worker đặt tenant bằng `set_tenant`."""
    return _app_sessionmaker()


@lru_cache
def admin_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_admin_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: một session cho mỗi request. Handler tự `commit()` khi ghi."""
    async with _app_sessionmaker()() as session:
        yield session


async def dispose_engines() -> None:
    for factory in (get_app_engine, get_admin_engine):
        if factory.cache_info().currsize:
            await factory().dispose()
            factory.cache_clear()
    _app_sessionmaker.cache_clear()
    admin_sessionmaker.cache_clear()
