from __future__ import annotations

import datetime as dt

import pytest
from redis.asyncio import Redis

from app.workers.settings import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, WorkerSettings, heartbeat

pytestmark = pytest.mark.integration


async def test_heartbeat_writes_timestamp_with_ttl(redis: Redis) -> None:
    returned = await heartbeat({"redis": redis})
    stored = await redis.get(HEARTBEAT_KEY)
    assert stored == returned
    assert dt.datetime.fromisoformat(stored).tzinfo is not None
    ttl = await redis.ttl(HEARTBEAT_KEY)
    assert 0 < ttl <= HEARTBEAT_TTL_SECONDS


def test_heartbeat_is_scheduled_every_minute() -> None:
    names = [job.name for job in WorkerSettings.cron_jobs]
    assert "cron:heartbeat" in names


def test_webhook_job_is_registered_with_retries() -> None:
    from app.workers.webhook import MAX_TRIES, retry_delay_seconds

    funcs = {f.name: f for f in WorkerSettings.functions if hasattr(f, "name")}
    assert funcs["process_webhook"].max_tries == MAX_TRIES
    assert [retry_delay_seconds(n) for n in (1, 2, 3, 7, 20)] == [10, 20, 40, 600, 600]
    assert WorkerSettings.log_results is False


def test_nightly_scores_runs_at_1am_vietnam_time() -> None:
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:nightly_scores")
    assert job.hour == 18 and job.minute == 0  # 18:00 UTC = 01:00 Asia/Ho_Chi_Minh


def test_reminders_run_every_five_minutes() -> None:
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:send_reminders")
    assert job.minute == set(range(0, 60, 5))
