"""Job arq mỗi giờ: đồng bộ quảng cáo, bài đăng và số liệu Trang (Bước 7).

Xuyên workspace qua `app_active_workspace_ids()`; mỗi workspace một transaction, lỗi ở một
workspace không chặn workspace khác. Log chỉ ghi số đếm, không bao giờ ghi mã truy cập.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.services import meta_sync
from app.workers.scoring import _workspace_ids

log = logging.getLogger(__name__)


async def sync_meta(ctx: dict[str, Any], now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    totals: dict[str, int] = {"workspaces": 0, "failed_workspaces": 0}
    for workspace_id in await _workspace_ids():
        try:
            async with app_sessionmaker()() as db:
                await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
                counts = await meta_sync.sync_workspace(db, workspace_id, now)
                await db.commit()
        except Exception:
            totals["failed_workspaces"] += 1
            log.exception("lỗi đồng bộ Meta", extra={"ctx": {"workspace_id": str(workspace_id)}})
            continue
        totals["workspaces"] += 1
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
    log.info("đã đồng bộ Meta", extra={"ctx": totals})
    return totals
