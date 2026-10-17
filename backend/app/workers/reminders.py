"""Job arq nhắc việc, chạy mỗi 5 phút cho mọi workspace đang hoạt động (quyết định Bước 5).

Danh sách workspace lấy qua `app_active_workspace_ids()`; mỗi workspace một transaction riêng,
lỗi ở một workspace không chặn các workspace khác. Log chỉ ghi số đếm.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.core.db import TenantContext, app_sessionmaker, set_tenant
from app.services.notify_service import deliver, due_for_workspace
from app.workers.scoring import _workspace_ids

log = logging.getLogger(__name__)


async def send_reminders(ctx: dict[str, Any], now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    created = failed = 0
    for workspace_id in await _workspace_ids():
        try:
            async with app_sessionmaker()() as db:
                await set_tenant(db, TenantContext(workspace_id=workspace_id, user_id=None))
                created += await deliver(db, await due_for_workspace(db, workspace_id, now), now)
                await db.commit()
        except Exception:
            failed += 1
            log.exception("lỗi nhắc việc", extra={"ctx": {"workspace_id": str(workspace_id)}})
    if created:
        log.info("đã tạo nhắc việc", extra={"ctx": {"created": created}})
    return {"created": created, "failed": failed}
