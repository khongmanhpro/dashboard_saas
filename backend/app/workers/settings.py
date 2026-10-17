"""Cấu hình worker arq: `arq app.workers.settings.WorkerSettings`.

- `heartbeat`: mỗi phút, để giám sát biết worker còn chạy.
- `process_webhook`: xử lý webhook Meta (app.workers.webhook).

Đồng bộ định kỳ và tính điểm ban đêm thêm ở các bước sau.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, ClassVar

from arq import cron, func

from app.core.config import get_settings
from app.core.db import dispose_engines
from app.core.logging import setup_logging
from app.core.queue import redis_settings as queue_redis_settings
from app.workers.webhook import MAX_TRIES, process_webhook

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


async def _shutdown(_ctx: dict[str, Any]) -> None:
    await dispose_engines()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat, func(process_webhook, max_tries=MAX_TRIES)]
    cron_jobs: ClassVar[list[Any]] = [cron(heartbeat, second=0, run_at_startup=False)]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = queue_redis_settings()
    # Kết quả job chỉ là số đếm, nhưng không cần ghi vào log.
    log_results = False
