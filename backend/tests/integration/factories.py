"""Tạo dữ liệu mẫu cho test. Chỉ dùng tên giả theo quy ước `[Nhân viên 186]`."""

from __future__ import annotations

import datetime as dt
import itertools
import secrets
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import (
    BusinessManager,
    MemberRole,
    Page,
    ScoreFormula,
    Team,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)

_seq = itertools.count(1)


async def create_workspace(db: AsyncSession, name: str | None = None) -> Workspace:
    n = next(_seq)
    ws = Workspace(name=name or f"[Workspace {n}]", slug=f"ws-{n}")
    db.add(ws)
    await db.flush()
    db.add(WorkspaceSettings(workspace_id=ws.id))
    db.add(
        ScoreFormula(
            workspace_id=ws.id, version=1, effective_from=dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        )
    )
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
        email=email or f"user{n}@example.com",
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


@dataclass
class Account:
    workspace: Workspace
    user: User
    member: WorkspaceMember
    password: str

    @property
    def email(self) -> str:
        return self.user.email


async def create_account(
    db: AsyncSession,
    role: MemberRole = MemberRole.STAFF,
    *,
    workspace: Workspace | None = None,
    team: Team | None = None,
    must_change_password: bool = False,
) -> Account:
    """Tạo người dùng có mật khẩu (sinh ngẫu nhiên) và membership. Gọi commit sau đó."""
    ws = workspace or await create_workspace(db)
    password = "pw-" + secrets.token_urlsafe(12)
    user = await create_user(
        db, password_hash=hash_password(password), must_change_password=must_change_password
    )
    member = await create_member(db, ws, user, role, team)
    return Account(ws, user, member, password)


async def login(client: httpx.AsyncClient, account: Account) -> str:
    """Đăng nhập, cookie lưu trong client. Trả về CSRF token để gửi kèm request ghi."""
    resp = await client.post(
        "/api/auth/login", json={"email": account.email, "password": account.password}
    )
    assert resp.status_code == 200, resp.text
    client.headers["X-CSRF-Token"] = resp.json()["csrf_token"]
    return str(resp.json()["csrf_token"])


async def create_business_manager(
    db: AsyncSession, workspace: Workspace, name: str | None = None
) -> BusinessManager:
    n = next(_seq)
    bm = BusinessManager(
        workspace_id=workspace.id, fb_business_id=f"9{n:014d}", name=name or f"[BM {n}]"
    )
    db.add(bm)
    await db.flush()
    return bm


async def create_page(
    db: AsyncSession,
    workspace: Workspace,
    *,
    bm: BusinessManager | None = None,
    fb_page_id: str | None = None,
    name: str | None = None,
    is_tracked: bool = True,
) -> Page:
    n = next(_seq)
    bm = bm or await create_business_manager(db, workspace)
    page = Page(
        workspace_id=workspace.id,
        business_manager_id=bm.id,
        fb_page_id=fb_page_id or f"1{n:014d}",
        name=name or f"[Trang {n}]",
        is_tracked=is_tracked,
    )
    db.add(page)
    await db.flush()
    return page
