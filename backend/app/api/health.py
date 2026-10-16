from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.db import get_app_engine
from app.core.redis import get_redis

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Tiến trình còn sống. Không kiểm tra phụ thuộc."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    """Sẵn sàng nhận request: DB và Redis đều trả lời được."""
    checks: dict[str, str] = {}
    try:
        async with get_app_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        log.exception("readyz: database lỗi")
        checks["database"] = "error"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        log.exception("readyz: redis lỗi")
        checks["redis"] = "error"
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "error", **checks}
