"""Job arq tính điểm mỗi đêm (01:00 giờ Việt Nam) cho mọi workspace đang hoạt động.

Tài khoản ứng dụng (bị RLS) không đọc được danh sách workspace, nên lấy qua
`app_active_workspace_ids()` (SECURITY DEFINER, migration 0005), rồi đặt từng workspace để tính.
Một workspace lỗi không làm dừng các workspace khác. Log chỉ ghi số đếm.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from sqlalchemy import text

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.services.score_service import recompute_workspace

log = logging.getLogger(__name__)


async def _workspace_ids() -> list[uuid.UUID]:
    async with app_sessionmaker()() as db:
        return list((await db.scalars(text("SELECT app_active_workspace_ids()"))).all())


async def recompute_one(workspace_id: uuid.UUID, now: dt.datetime) -> dict[str, int]:
    async with app_sessionmaker()() as db:
        await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
        counts = await recompute_workspace(db, workspace_id, now)
        await db.commit()
        return counts


async def nightly_scores(ctx: dict[str, Any], now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    done = failed = 0
    for workspace_id in await _workspace_ids():
        try:
            counts = await recompute_one(workspace_id, now)
        except Exception:
            failed += 1
            log.exception("lỗi tính điểm", extra={"ctx": {"workspace_id": str(workspace_id)}})
            continue
        done += 1
        log.info("đã tính điểm", extra={"ctx": {"workspace_id": str(workspace_id), **counts}})
    return {"workspaces": done, "failed": failed}
