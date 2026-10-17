"""Dữ liệu demo cho máy dev: một workspace, các nhóm, tài khoản đủ 5 vai trò, 1 BM giả và
4 Trang demo kèm người phụ trách.

    docker compose run --rm migrate python -m app.mock.seed

Tên người đều là tên giả. Mật khẩu sinh ngẫu nhiên, ghi vào `backend/.dev-credentials`
(đã nằm trong .gitignore, quyền 600), không in ra màn hình. ID Trang và BM là ID giả.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import ensure_member, get_or_create_workspace
from app.core.config import get_settings
from app.core.crypto import get_token_cipher, last4
from app.core.db import admin_sessionmaker, dispose_engines
from app.meta.graph import MockGraphClient
from app.mock.history import seed_history
from app.models import (
    BusinessManager,
    MemberRole,
    Page,
    PageAssignment,
    Team,
    User,
    Workspace,
    WorkspaceMember,
)
from app.services.assignment import assign_page
from app.services.bm_service import sync_bm
from app.workers.meta_sync import sync_meta
from app.workers.scoring import nightly_scores

WORKSPACE_NAME = "FISS Demo"
WORKSPACE_SLUG = "fiss-demo"
CREDENTIALS_FILE = Path(__file__).resolve().parents[2] / ".dev-credentials"

TEAMS = ["[Nhóm Phần mềm]", "[Nhóm Bán lẻ]"]
ACCOUNTS: list[tuple[str, str, MemberRole, str | None]] = [
    ("owner@demo.example.com", "[Chủ sở hữu]", MemberRole.OWNER, None),
    ("manager@demo.example.com", "[Quản lý 01]", MemberRole.MANAGER, None),
    ("lead@demo.example.com", "[Trưởng nhóm 01]", MemberRole.TEAM_LEAD, TEAMS[0]),
    ("staff186@demo.example.com", "[Nhân viên 186]", MemberRole.STAFF, TEAMS[0]),
    ("staff187@demo.example.com", "[Nhân viên 187]", MemberRole.STAFF, TEAMS[1]),
    ("viewer@demo.example.com", "[Chỉ xem 01]", MemberRole.VIEWER, None),
]

DEMO_BM = ("900000000000000", "[BM Demo]")
MOCK_BM_TOKEN = "MOCK-BM-1"  # noqa: S105 — mã giả của client Graph giả, không phải bí mật
# (fb_page_id giả, tên Trang, tài khoản phụ trách hoặc None). Trưởng nhóm cũng phụ trách
# được Trang (quyết định #14). Mua Sắm Thông Minh để trống để thử Trang chưa có người.
DEMO_PAGES: list[tuple[str, str, str | None]] = [
    ("100000000000101", "Phần Mềm Giá Rẻ", "staff186"),
    ("100000000000102", "FISS", "staff187"),
    ("100000000000103", "Shop Thỏ", "lead"),
    ("100000000000104", "Mua Sắm Thông Minh", None),
]
ASSIGNED_FROM = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


@dataclass
class DemoWorkspace:
    workspace: Workspace
    members: dict[str, WorkspaceMember]  # theo phần trước @ của email: "staff186", "lead"…
    pages: dict[str, Page]  # theo tên Trang
    passwords: dict[str, str]


async def ensure_demo_workspace(
    db: AsyncSession, password_for: Callable[[str], str] = lambda _email: secrets.token_urlsafe(12)
) -> DemoWorkspace:
    """Tạo (hoặc bổ sung) workspace demo. Chạy lại nhiều lần không tạo trùng."""
    ws = await get_or_create_workspace(db, WORKSPACE_NAME, WORKSPACE_SLUG)
    teams: dict[str, Team] = {}
    for name in TEAMS:
        team = await db.scalar(select(Team).where(Team.workspace_id == ws.id, Team.name == name))
        if team is None:
            team = Team(workspace_id=ws.id, name=name)
            db.add(team)
            await db.flush()
        teams[name] = team

    members: dict[str, WorkspaceMember] = {}
    passwords: dict[str, str] = {}
    for email, full_name, role, team_name in ACCOUNTS:
        password = password_for(email)
        _, member, _ = await ensure_member(
            db,
            ws,
            email=email,
            full_name=full_name,
            role=role,
            password=password,
            must_change_password=False,
            reset_password=True,
        )
        if team_name:
            member.team_id = teams[team_name].id
            if role == MemberRole.TEAM_LEAD:
                teams[team_name].lead_member_id = member.id
        key = email.split("@", 1)[0]
        members[key] = member
        passwords[email] = password

    bm = await db.scalar(
        select(BusinessManager).where(
            BusinessManager.workspace_id == ws.id, BusinessManager.fb_business_id == DEMO_BM[0]
        )
    )
    if bm is None:
        bm = BusinessManager(workspace_id=ws.id, fb_business_id=DEMO_BM[0], name=DEMO_BM[1])
        db.add(bm)
        await db.flush()
    if get_settings().mock_mode and bm.token_ciphertext is None:
        # Mã giả của client Graph giả (tests/fixtures/meta/graph_mock.json), không phải mã thật.
        bm.token_ciphertext = get_token_cipher().encrypt(MOCK_BM_TOKEN)
        bm.token_last4 = last4(MOCK_BM_TOKEN)

    pages: dict[str, Page] = {}
    for fb_page_id, name, owner_key in DEMO_PAGES:
        page = await db.scalar(
            select(Page).where(Page.workspace_id == ws.id, Page.fb_page_id == fb_page_id)
        )
        if page is None:
            page = Page(
                workspace_id=ws.id,
                business_manager_id=bm.id,
                fb_page_id=fb_page_id,
                name=name,
                webhook_fields=[
                    "messages",
                    "message_echoes",
                    "messaging_referrals",
                    "leadgen",
                    "feed",
                ],
            )
            db.add(page)
            await db.flush()
        pages[name] = page
        has_history = await db.scalar(
            select(PageAssignment.id).where(PageAssignment.page_id == page.id).limit(1)
        )
        if owner_key is not None and has_history is None:
            await assign_page(db, page, members[owner_key], ASSIGNED_FROM, reason="[Dữ liệu demo]")
    if get_settings().mock_mode:
        # Gắn mã Trang giả và đăng ký webhook giả như khi kết nối BM thật (Bước 6).
        await sync_bm(db, bm, dt.datetime.now(dt.UTC), MockGraphClient(), kind="seed")
    return DemoWorkspace(ws, members, pages, passwords)


async def load_demo_workspace(db: AsyncSession) -> DemoWorkspace | None:
    """Đọc workspace demo đã seed (không đổi mật khẩu). None nếu chưa chạy seed."""
    ws = await db.scalar(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
    if ws is None:
        return None
    members: dict[str, WorkspaceMember] = {}
    for email, *_ in ACCOUNTS:
        member = await db.scalar(
            select(WorkspaceMember)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == ws.id, User.email == email)
        )
        if member is not None:
            members[email.split("@", 1)[0]] = member
    pages = {
        page.name: page
        for page in await db.scalars(
            select(Page).where(
                Page.workspace_id == ws.id,
                Page.fb_page_id.in_([fb for fb, _, _ in DEMO_PAGES]),
            )
        )
    }
    if len(pages) != len(DEMO_PAGES) or len(members) != len(ACCOUNTS):
        return None
    return DemoWorkspace(ws, members, pages, {})


async def seed() -> None:
    if get_settings().app_env != "development":
        raise SystemExit("Chỉ chạy seed demo ở môi trường development.")
    lines = [f"# Tài khoản demo workspace '{WORKSPACE_NAME}'. KHÔNG commit file này."]
    history = 0
    async with admin_sessionmaker()() as db:
        demo = await ensure_demo_workspace(db)
        for email, _, role, _ in ACCOUNTS:
            lines.append(f"{role.value:<10} {email:<28} {demo.passwords[email]}")
        if get_settings().mock_mode:
            owners = {name: demo.members[key] if key else None for _, name, key in DEMO_PAGES}
            history = await seed_history(
                db, demo.workspace.id, demo.pages, owners, dt.datetime.now(dt.UTC)
            )
        await db.commit()
    if get_settings().mock_mode:
        # Như worker chạy thật: đồng bộ quảng cáo, bài đăng (client Graph giả), rồi tính điểm.
        await sync_meta({})
        await nightly_scores({})
    await dispose_engines()

    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(CREDENTIALS_FILE, 0o600)
    print(f"Đã tạo dữ liệu demo. Tài khoản và mật khẩu: backend/{CREDENTIALS_FILE.name}")
    print("4 Trang demo: " + ", ".join(name for _, name, _ in DEMO_PAGES))
    if history:
        print(f"Thêm {history} khách mẫu trong 30 ngày, đã đồng bộ quảng cáo và tính điểm.")


if __name__ == "__main__":
    asyncio.run(seed())
