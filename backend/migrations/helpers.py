"""Hàm dùng chung cho migration: RLS và cấp quyền cho tài khoản ứng dụng.

Quy ước: mọi bảng có `workspace_id` phải gọi `enable_tenant_rls()` và `grant_app()`.
`tests/integration/test_schema_invariants.py` kiểm tra điều này.
"""

from __future__ import annotations

import re

from alembic import op

from app.core.config import get_settings

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def app_role() -> str:
    role = get_settings().postgres_app_user
    if not _IDENT.match(role):
        raise ValueError("POSTGRES_APP_USER chỉ được chứa a-z, 0-9, _")
    return role


def enable_tenant_rls(table: str) -> None:
    """Chỉ thấy và ghi được dòng thuộc workspace đang đặt trong `app.workspace_id`."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table}"
        " USING (workspace_id = app_current_workspace())"
        " WITH CHECK (workspace_id = app_current_workspace())"
    )


def grant_app(table: str, privileges: str = "SELECT, INSERT, UPDATE, DELETE") -> None:
    op.execute(f'GRANT {privileges} ON {table} TO "{app_role()}"')


def revoke_app(table: str) -> None:
    op.execute(f'REVOKE ALL ON {table} FROM "{app_role()}"')
