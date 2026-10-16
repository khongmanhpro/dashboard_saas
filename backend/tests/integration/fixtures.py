"""Fixture cho test tích hợp (DB, Redis, client API)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.core.redis import close_redis, get_redis


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = get_redis()
    await client.flushdb()
    yield client
    await client.flushdb()
    await close_redis()
