"""Cấu hình worker arq: `arq app.workers.settings.WorkerSettings`.

- `heartbeat`: mỗi phút, để giám sát biết worker còn chạy.
- `process_webhook`: xử lý webhook Meta (app.workers.webhook).
- `purge_expired_data`: 02:30 giờ Việt Nam mỗi đêm, hạn lưu dữ liệu (app.workers.retention).
- `nightly_scores`: 01:00 giờ Việt Nam mỗi đêm, tính điểm và chốt tuần (app.workers.scoring).
- `send_reminders`: mỗi 5 phút, nhắc việc và thông báo đẩy (app.workers.reminders).
- `check_bms`: mỗi 6 giờ, kiểm tra mã, quyền BM, Trang mới, form leadgen (app.workers.meta_checks).

Đồng bộ định kỳ thêm ở các bước sau.
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
from app.workers.meta_checks import check_bms
from app.workers.reminders import send_reminders
from app.workers.retention import purge_expired_data
from app.workers.scoring import nightly_scores
from app.workers.webhook import MAX_TRIES, process_webhook

HEARTBEAT_KEY = "worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 300
# Lịch cron tính theo UTC (khai báo rõ, không phụ thuộc múi giờ của container).
PURGE_HOUR_UTC = 19  # 02:30 Asia/Ho_Chi_Minh
PURGE_MINUTE_UTC = 30
PURGE_TIMEOUT_SECONDS = 30 * 60
SCORES_HOUR_UTC = 18  # 01:00 Asia/Ho_Chi_Minh
SCORES_TIMEOUT_SECONDS = 60 * 60

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
    cron_jobs: ClassVar[list[Any]] = [
        cron(heartbeat, second=0, run_at_startup=False),
        cron(
            purge_expired_data,
            hour=PURGE_HOUR_UTC,
            minute=PURGE_MINUTE_UTC,
            second=0,
            timeout=PURGE_TIMEOUT_SECONDS,
            run_at_startup=False,
        ),
        cron(
            check_bms,
            hour={0, 6, 12, 18},
            minute=15,
            second=0,
            timeout=30 * 60,
            run_at_startup=False,
        ),
        cron(
            send_reminders,
            minute=set(range(0, 60, 5)),
            second=30,
            timeout=4 * 60,
            run_at_startup=False,
        ),
        cron(
            nightly_scores,
            hour=SCORES_HOUR_UTC,
            minute=0,
            second=0,
            timeout=SCORES_TIMEOUT_SECONDS,
            run_at_startup=False,
        ),
    ]
    timezone = dt.UTC
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = queue_redis_settings()
    # Kết quả job chỉ là số đếm, nhưng không cần ghi vào log.
    log_results = False
