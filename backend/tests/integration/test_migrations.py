from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base
from tests.integration.conftest import admin_url_for, alembic_config, recreate_database

pytestmark = pytest.mark.integration

MIGRATION_DB = "fanpage_migration_test"


def _diff(conn: Connection) -> list[object]:
    ctx = MigrationContext.configure(
        conn, opts={"compare_type": True, "compare_server_default": True}
    )
    return list(compare_metadata(ctx, Base.metadata))


async def test_upgrade_downgrade_upgrade_and_models_match() -> None:
    await recreate_database(MIGRATION_DB)
    url = admin_url_for(MIGRATION_DB)
    cfg = alembic_config(url)

    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "base")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            leftover = await conn.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                )
            )
        assert leftover == 0, "downgrade base phải xóa hết bảng"

        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with engine.connect() as conn:
            diff = await conn.run_sync(_diff)
        assert diff == [], f"Model và migration lệch nhau: {diff}"
    finally:
        await engine.dispose()


async def test_downgrade_0003_drops_purge_function() -> None:
    await recreate_database(MIGRATION_DB)
    url = admin_url_for(MIGRATION_DB)
    cfg = alembic_config(url)
    exists_sql = text(
        "SELECT count(*) FROM pg_proc WHERE proname = 'app_purge_expired_data'"
        " UNION ALL SELECT count(*) FROM pg_indexes"
        " WHERE indexname = 'ix_messages_sent_at_with_text'"
    )

    await asyncio.to_thread(command.upgrade, cfg, "0003")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            assert list(await conn.scalars(exists_sql)) == [1, 1]
        await asyncio.to_thread(command.downgrade, cfg, "0002")
        async with engine.connect() as conn:
            assert list(await conn.scalars(exists_sql)) == [0, 0]
            # Hàm của 0002 vẫn còn.
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM pg_proc WHERE proname = 'app_route_page'")
                )
                == 1
            )
    finally:
        await engine.dispose()
