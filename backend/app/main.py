from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.db import dispose_engines
from app.core.logging import setup_logging
from app.core.redis import close_redis


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engines()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="Fanpage Staff Metrics",
        lifespan=lifespan,
        # Không công khai tài liệu API ở production.
        docs_url=None if settings.is_production_like else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production_like else "/api/openapi.json",
    )
    app.include_router(health.router)
    return app


app = create_app()
