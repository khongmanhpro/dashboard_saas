"""Tạo dữ liệu mẫu cho test. Chỉ dùng tên giả theo quy ước `[Nhân viên 186]`."""

from __future__ import annotations

import itertools

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemberRole, Team, User, Workspace, WorkspaceMember, WorkspaceSettings

_seq = itertools.count(1)


async def create_workspace(db: AsyncSession, name: str | None = None) -> Workspace:
    n = next(_seq)
    ws = Workspace(name=name or f"[Workspace {n}]", slug=f"ws-{n}")
    db.add(ws)
    await db.flush()
    db.add(WorkspaceSettings(workspace_id=ws.id))
    await db.flush()
    return ws


async def create_user(
    db: AsyncSession,
    email: str | None = None,
    full_name: str | None = None,
    password_hash: str | None = None,
    must_change_password: bool = False,
    is_active: bool = True,
) -> User:
    n = next(_seq)
    user = User(
        email=email or f"user{n}@example.test",
        full_name=full_name or f"[Nhân viên {n}]",
        password_hash=password_hash,
        must_change_password=must_change_password,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def create_member(
    db: AsyncSession,
    workspace: Workspace,
    user: User,
    role: MemberRole,
    team: Team | None = None,
) -> WorkspaceMember:
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
        team_id=team.id if team else None,
    )
    db.add(member)
    await db.flush()
    return member


async def create_team(db: AsyncSession, workspace: Workspace, name: str | None = None) -> Team:
    team = Team(workspace_id=workspace.id, name=name or f"[Nhóm {next(_seq)}]")
    db.add(team)
    await db.flush()
    return team
