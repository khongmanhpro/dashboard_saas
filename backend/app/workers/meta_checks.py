"""Job arq mỗi 6 giờ: kiểm tra mã và quyền của từng BM, Trang mới, lấy bù form leadgen (Bước 6).

Xuyên workspace qua `app_active_workspace_ids()`; mỗi workspace một transaction. Log chỉ ghi số đếm,
không bao giờ ghi mã truy cập.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.services import bm_service, inbound
from app.workers.scoring import _workspace_ids

log = logging.getLogger(__name__)


async def check_bms(ctx: dict[str, Any], now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    totals = {"checked": 0, "worse": 0, "new_pages": 0, "leadgen_fetched": 0, "failed": 0}
    for workspace_id in await _workspace_ids():
        try:
            async with app_sessionmaker()() as db:
                await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
                counts = await bm_service.check_workspace(db, workspace_id, now)
                counts["leadgen_fetched"] = await inbound.refresh_pending_leadgen(db)
                await db.commit()
        except Exception:
            totals["failed"] += 1
            log.exception("lỗi kiểm tra BM", extra={"ctx": {"workspace_id": str(workspace_id)}})
            continue
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
    log.info("đã kiểm tra BM", extra={"ctx": totals})
    return totals
