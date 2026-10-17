"""Hạn lưu dữ liệu: hàm `app_purge_expired_data` (migration 0003) và job ban đêm."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import _app_sessionmaker
from app.models import (
    Contact,
    Message,
    MessageDirection,
    WebhookEvent,
    WebhookEventStatus,
    Workspace,
)
from app.workers.retention import (
    MESSAGE_TEXT_RETENTION_DAYS,
    WEBHOOK_EVENTS_RETENTION_DAYS,
    purge_expired_data,
)
from app.workers.settings import PURGE_HOUR_UTC, PURGE_MINUTE_UTC, WorkerSettings
from tests.integration import factories as f

pytestmark = pytest.mark.integration

PURGE_SQL = text(
    "SELECT webhook_events_deleted, message_texts_cleared FROM app_purge_expired_data(:w, :m)"
)
SECRET_TEXT = "[Nội dung tin nhắn mẫu]"


@pytest.fixture
async def app_db() -> AsyncIterator[AsyncSession]:
    async with _app_sessionmaker()() as session:
        yield session


def _ago(days: float) -> dt.datetime:
    return dt.datetime.now(dt.UTC) - dt.timedelta(days=days)


async def _seed(db: AsyncSession, tag: str, ages_days: list[float]) -> Workspace:
    """Mỗi tuổi (ngày) tạo một webhook_event và một tin nhắn có nội dung."""
    ws = await f.create_workspace(db, f"[Workspace {tag}]")
    page = await f.create_page(db, ws)
    contact = Contact(
        workspace_id=ws.id, page_id=page.id, psid=f"psid-{tag}", first_seen_at=_ago(400)
    )
    db.add(contact)
    await db.flush()
    for i, age in enumerate(ages_days):
        db.add(
            WebhookEvent(
                workspace_id=ws.id,
                received_at=_ago(age),
                object="page",
                fb_page_id=page.fb_page_id,
                kind="message",
                dedupe_key=f"mid:{tag}-{i}",
                payload={"text": SECRET_TEXT},
                status=WebhookEventStatus.PROCESSED,
            )
        )
        db.add(
            Message(
                workspace_id=ws.id,
                page_id=page.id,
                contact_id=contact.id,
                mid=f"m_{tag}_{i}",
                direction=MessageDirection.IN,
                sent_at=_ago(age),
                text=SECRET_TEXT,
            )
        )
    await db.flush()
    return ws


async def _ages_left(db: AsyncSession) -> tuple[list[int], list[int]]:
    """(tuổi các webhook_event còn lại, tuổi các tin còn nội dung), làm tròn theo ngày."""
    now = dt.datetime.now(dt.UTC)
    events = await db.scalars(select(WebhookEvent.received_at))
    texts = await db.scalars(select(Message.sent_at).where(Message.text.is_not(None)))
    return (
        sorted(round((now - t).total_seconds() / 86400) for t in events),
        sorted(round((now - t).total_seconds() / 86400) for t in texts),
    )


async def test_purge_removes_only_expired_rows_across_workspaces(
    admin_db: AsyncSession, app_db: AsyncSession
) -> None:
    # 29.9 / 179.9 ngày: sát mốc nhưng còn hạn, phải giữ.
    ages = [1, 29.9, 31, 179.9, 181, 400]
    await _seed(admin_db, "A", ages)
    await _seed(admin_db, "B", ages)
    await admin_db.commit()

    # Không đặt workspace: tài khoản ứng dụng không thấy dòng nào, nhưng hàm xử lý mọi workspace.
    assert await app_db.scalar(select(func.count()).select_from(WebhookEvent)) == 0
    deleted, cleared = (await app_db.execute(PURGE_SQL, {"w": 30, "m": 180})).one()
    await app_db.commit()
    assert (deleted, cleared) == (2 * 4, 2 * 2)

    events_left, texts_left = await _ages_left(admin_db)
    assert events_left == [1, 1, 30, 30]
    assert texts_left == [1, 1, 30, 30, 31, 31, 180, 180]
    # Tin nhắn vẫn giữ dòng và số liệu, chỉ mất nội dung.
    assert await admin_db.scalar(select(func.count()).select_from(Message)) == 2 * len(ages)

    # Chạy lại không còn gì để xử lý.
    assert tuple((await app_db.execute(PURGE_SQL, {"w": 30, "m": 180})).one()) == (0, 0)


async def test_larger_threshold_keeps_more(admin_db: AsyncSession, app_db: AsyncSession) -> None:
    await _seed(admin_db, "A", [31, 181, 400])
    await admin_db.commit()
    assert tuple((await app_db.execute(PURGE_SQL, {"w": 60, "m": 365})).one()) == (2, 1)
    await app_db.commit()
    assert await _ages_left(admin_db) == ([31], [31, 181])


@pytest.mark.parametrize(
    ("webhook_days", "message_text_days"),
    [(29, 180), (30, 179), (0, 0), (-1, 180), (None, 180), (30, None)],
)
async def test_threshold_below_minimum_is_rejected(
    admin_db: AsyncSession,
    app_db: AsyncSession,
    webhook_days: int | None,
    message_text_days: int | None,
) -> None:
    await _seed(admin_db, "A", [1, 31, 181])
    await admin_db.commit()
    with pytest.raises(DBAPIError, match="phải >="):
        await app_db.execute(PURGE_SQL, {"w": webhook_days, "m": message_text_days})
    await app_db.rollback()
    assert await _ages_left(admin_db) == ([1, 31, 181], [1, 31, 181])


async def test_purge_function_is_locked_down(admin_db: AsyncSession) -> None:
    row = (
        await admin_db.execute(
            text(
                "SELECT p.prosecdef, p.proconfig,"
                " has_function_privilege(:r, p.oid, 'EXECUTE'),"
                " has_function_privilege('public', p.oid, 'EXECUTE')"
                " FROM pg_proc p WHERE p.proname = 'app_purge_expired_data'"
            ),
            {"r": get_settings().postgres_app_user},
        )
    ).one()
    secdef, config, app_can, public_can = row
    assert secdef is True
    assert "search_path=pg_catalog, pg_temp" in config
    assert app_can is True
    assert public_can is False


async def test_app_role_still_cannot_delete_webhook_events_directly(
    admin_db: AsyncSession, app_db: AsyncSession
) -> None:
    await _seed(admin_db, "A", [400])
    await admin_db.commit()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_db.execute(delete(WebhookEvent))
    await app_db.rollback()


async def test_nightly_job_purges_and_logs_only_counts(
    admin_db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await _seed(admin_db, "A", [1, 31, 181])
    await admin_db.commit()
    with caplog.at_level(logging.DEBUG, logger="app.workers.retention"):
        counts = await purge_expired_data({})
    assert counts == {"webhook_events_deleted": 2, "message_texts_cleared": 1}
    assert await _ages_left(admin_db) == ([1], [1, 31])
    assert "xóa 2 webhook_events" in caplog.text
    assert "nội dung 1 tin nhắn" in caplog.text
    assert SECRET_TEXT not in caplog.text


def test_job_uses_documented_minimums_and_runs_nightly() -> None:
    assert (WEBHOOK_EVENTS_RETENTION_DAYS, MESSAGE_TEXT_RETENTION_DAYS) == (30, 180)
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:purge_expired_data")
    assert (job.hour, job.minute, job.second) == (PURGE_HOUR_UTC, PURGE_MINUTE_UTC, 0)
    assert WorkerSettings.timezone is dt.UTC
    # 02:30 giờ Việt Nam.
    assert (PURGE_HOUR_UTC + 7) % 24 == 2
