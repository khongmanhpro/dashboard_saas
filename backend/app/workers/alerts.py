"""Job arq mỗi giờ: cảnh báo Telegram theo quy tắc và tóm tắt buổi sáng (Bước 7).

Xuyên workspace qua `app_active_workspace_ids()`; mỗi workspace một transaction. Log chỉ ghi số
đếm, không bao giờ ghi mã bot.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.services import alert_service
from app.workers.scoring import _workspace_ids

log = logging.getLogger(__name__)


async def send_alerts(ctx: dict[str, Any], now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    totals = {"workspaces": 0, "sent": 0, "failed": 0, "failed_workspaces": 0}
    for workspace_id in await _workspace_ids():
        try:
            async with app_sessionmaker()() as db:
                await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
                counts = await alert_service.run_workspace(db, workspace_id, now)
                await db.commit()
        except Exception:
            totals["failed_workspaces"] += 1
            log.exception("lỗi gửi cảnh báo", extra={"ctx": {"workspace_id": str(workspace_id)}})
            continue
        totals["workspaces"] += 1
        totals["sent"] += counts["sent"]
        totals["failed"] += counts["failed"]
    log.info("đã kiểm tra cảnh báo", extra={"ctx": totals})
    return totals
