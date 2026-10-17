from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, health, leads, members, public, staff, webhooks
from app.core.config import get_settings
from app.core.db import dispose_engines
from app.core.logging import setup_logging
from app.core.queue import close_queue
from app.core.redis import close_redis
from app.services.errors import ServiceError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engines()
    await close_redis()
    await close_queue()


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
    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(leads.router)
    app.include_router(staff.router)
    app.include_router(webhooks.router)

    @app.exception_handler(ServiceError)
    async def _service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": {"code": exc.code, **exc.extra}}
        )

    return app


app = create_app()
