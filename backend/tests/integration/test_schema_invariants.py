"""Quy ước bắt buộc của schema (CLAUDE.md mục 1, 5, 6). Bảng mới vi phạm thì test fail."""

from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Base

pytestmark = pytest.mark.integration

# Bảng toàn cục, không thuộc workspace (xem docs/architecture/data-model.md).
GLOBAL_TABLES = {"users", "workspaces"}
# Có workspace_id nhưng không bật RLS vì phải tra trước khi biết workspace.
RLS_EXEMPT = {"auth_sessions"}


def test_every_business_table_has_workspace_id() -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in GLOBAL_TABLES:
            continue
        col = table.columns.get("workspace_id")
        assert col is not None, f"{table.name} thiếu workspace_id"
        assert not col.nullable, f"{table.name}.workspace_id phải NOT NULL"


def test_every_datetime_is_timezone_aware() -> None:
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, DateTime):
                assert col.type.timezone, f"{table.name}.{col.name} phải có múi giờ"


def test_money_columns_are_bigint() -> None:
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if col.name.endswith("_vnd"):
                assert isinstance(col.type, BigInteger), f"{table.name}.{col.name} phải BIGINT"


async def test_rls_enabled_on_every_workspace_table(admin_db: AsyncSession) -> None:
    rows = await admin_db.execute(
        text(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c"
            " JOIN information_schema.columns col"
            "   ON col.table_name = c.relname AND col.column_name = 'workspace_id'"
            " WHERE col.table_schema = 'public' AND c.relkind = 'r'"
        )
    )
    tables = {name: enabled for name, enabled in rows.all()}
    assert tables, "không tìm thấy bảng nào có workspace_id"
    for name, enabled in tables.items():
        if name in RLS_EXEMPT:
            continue
        assert enabled, f"{name} có workspace_id nhưng chưa bật RLS"
    rls_ws = await admin_db.scalar(
        text("SELECT relrowsecurity FROM pg_class WHERE relname = 'workspaces'")
    )
    assert rls_ws


async def test_app_role_is_restricted(admin_db: AsyncSession) -> None:
    role = get_settings().postgres_app_user
    row = (
        await admin_db.execute(
            text("SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname = :r"),
            {"r": role},
        )
    ).one()
    assert row == (False, False, False)
    can_touch_version = await admin_db.scalar(
        text("SELECT has_table_privilege(:r, 'alembic_version', 'SELECT')"), {"r": role}
    )
    assert can_touch_version is False


@pytest.mark.parametrize("privilege", ["UPDATE", "DELETE", "TRUNCATE"])
async def test_app_role_cannot_rewrite_audit_logs(admin_db: AsyncSession, privilege: str) -> None:
    role = get_settings().postgres_app_user
    allowed = await admin_db.scalar(
        text("SELECT has_table_privilege(:r, 'audit_logs', :p)"), {"r": role, "p": privilege}
    )
    assert allowed is False
