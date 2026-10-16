"""Row-Level Security: tài khoản ứng dụng chỉ thấy dữ liệu của workspace đang đặt."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import TenantContext, _app_sessionmaker, set_tenant
from app.models import AuditLog, MemberRole, Team, Workspace, WorkspaceMember, WorkspaceSettings
from tests.integration import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_workspaces(admin_db: AsyncSession) -> dict[str, object]:
    ws_a = await f.create_workspace(admin_db, "[Workspace A]")
    ws_b = await f.create_workspace(admin_db, "[Workspace B]")
    shared_user = await f.create_user(admin_db)
    member_a = await f.create_member(admin_db, ws_a, shared_user, MemberRole.STAFF)
    member_b = await f.create_member(admin_db, ws_b, shared_user, MemberRole.MANAGER)
    other_b = await f.create_member(admin_db, ws_b, await f.create_user(admin_db), MemberRole.STAFF)
    await f.create_team(admin_db, ws_a, "[Nhóm A]")
    await f.create_team(admin_db, ws_b, "[Nhóm B]")
    await admin_db.commit()
    return {
        "a": ws_a.id,
        "b": ws_b.id,
        "user": shared_user.id,
        "member_a": member_a.id,
        "member_b": member_b.id,
        "other_b": other_b.id,
    }


@pytest.fixture
async def app_db() -> AsyncIterator[AsyncSession]:
    async with _app_sessionmaker()() as session:
        yield session


async def _count(db: AsyncSession, model: type) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_without_tenant_context_sees_nothing(
    app_db: AsyncSession, two_workspaces: dict
) -> None:
    for model in (WorkspaceMember, Team, WorkspaceSettings, Workspace):
        assert await _count(app_db, model) == 0, model.__tablename__


async def test_sees_only_current_workspace(app_db: AsyncSession, two_workspaces: dict) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["a"], user_id=None))
    teams = (await app_db.scalars(select(Team.name))).all()
    assert teams == ["[Nhóm A]"]
    members = (await app_db.scalars(select(WorkspaceMember.id))).all()
    assert members == [two_workspaces["member_a"]]
    workspaces = (await app_db.scalars(select(Workspace.id))).all()
    assert workspaces == [two_workspaces["a"]]
    # Raw SQL cũng không vượt được RLS.
    raw = await app_db.scalar(text("SELECT count(*) FROM workspace_members"))
    assert raw == 1


async def test_context_survives_commit(app_db: AsyncSession, two_workspaces: dict) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["b"], user_id=None))
    assert await _count(app_db, WorkspaceMember) == 2
    await app_db.commit()
    # Transaction mới: after_begin phải đặt lại ngữ cảnh.
    assert await _count(app_db, WorkspaceMember) == 2


async def test_cannot_write_into_other_workspace(
    app_db: AsyncSession, two_workspaces: dict
) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["a"], user_id=None))
    app_db.add(Team(workspace_id=two_workspaces["b"], name="[Nhóm lấn sân]"))
    with pytest.raises(ProgrammingError, match="row-level security"):
        await app_db.flush()


async def test_cannot_update_rows_of_other_workspace(
    app_db: AsyncSession, two_workspaces: dict
) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["a"], user_id=None))
    result = await app_db.execute(
        text("UPDATE teams SET name = 'x' WHERE workspace_id = :b"), {"b": two_workspaces["b"]}
    )
    assert result.rowcount == 0  # type: ignore[attr-defined]


async def test_user_context_lists_own_memberships_across_workspaces(
    app_db: AsyncSession, two_workspaces: dict
) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=None, user_id=two_workspaces["user"]))
    members = set((await app_db.scalars(select(WorkspaceMember.id))).all())
    assert members == {two_workspaces["member_a"], two_workspaces["member_b"]}
    workspaces = set((await app_db.scalars(select(Workspace.id))).all())
    assert workspaces == {two_workspaces["a"], two_workspaces["b"]}


async def test_app_cannot_create_workspace(app_db: AsyncSession, two_workspaces: dict) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["a"], user_id=None))
    app_db.add(Workspace(name="[Lén tạo]", slug="len-tao"))
    with pytest.raises(DBAPIError, match="permission denied"):
        await app_db.flush()


async def test_app_cannot_delete_audit_logs(app_db: AsyncSession, two_workspaces: dict) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=two_workspaces["a"], user_id=None))
    app_db.add(AuditLog(workspace_id=two_workspaces["a"], action="test", entity_type="test"))
    await app_db.commit()
    with pytest.raises(DBAPIError, match="permission denied"):
        await app_db.execute(text("DELETE FROM audit_logs"))


async def test_unknown_workspace_id_sees_nothing(
    app_db: AsyncSession, two_workspaces: dict
) -> None:
    await set_tenant(app_db, TenantContext(workspace_id=uuid.uuid4(), user_id=None))
    assert await _count(app_db, WorkspaceMember) == 0
