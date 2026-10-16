"""Cấu hình worker arq: `arq app.workers.settings.WorkerSettings`.

Bước 1 chỉ có job heartbeat. Webhook, đồng bộ và tính điểm ban đêm thêm ở các bước sau.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging

HEARTBEAT_KEY = "worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 300

log = logging.getLogger(__name__)


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Ghi thời điểm worker còn chạy, để giám sát biết worker không bị treo."""
    now = dt.datetime.now(dt.UTC).isoformat()
    await ctx["redis"].set(HEARTBEAT_KEY, now, ex=HEARTBEAT_TTL_SECONDS)
    return now


async def _startup(ctx: dict[str, Any]) -> None:
    setup_logging(get_settings().log_level)
    await heartbeat(ctx)
    log.info("worker đã khởi động")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat]
    cron_jobs: ClassVar[list[Any]] = [cron(heartbeat, second=0, run_at_startup=False)]
    on_startup = _startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
