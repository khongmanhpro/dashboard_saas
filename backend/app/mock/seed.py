"""Dữ liệu demo cho máy dev: một workspace, các nhóm và tài khoản đủ 5 vai trò.

    docker compose run --rm migrate python -m app.mock.seed

Tên đều là tên giả. Mật khẩu sinh ngẫu nhiên, ghi vào `backend/.dev-credentials`
(đã nằm trong .gitignore, quyền 600), không in ra màn hình.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path

from sqlalchemy import select

from app.cli import ensure_member, get_or_create_workspace
from app.core.config import get_settings
from app.core.db import admin_sessionmaker, dispose_engines
from app.models import MemberRole, Team

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


async def seed() -> None:
    if get_settings().app_env != "development":
        raise SystemExit("Chỉ chạy seed demo ở môi trường development.")
    lines = [f"# Tài khoản demo workspace '{WORKSPACE_NAME}'. KHÔNG commit file này."]
    async with admin_sessionmaker()() as db:
        ws = await get_or_create_workspace(db, WORKSPACE_NAME, WORKSPACE_SLUG)
        teams: dict[str, Team] = {}
        for name in TEAMS:
            team = await db.scalar(
                select(Team).where(Team.workspace_id == ws.id, Team.name == name)
            )
            if team is None:
                team = Team(workspace_id=ws.id, name=name)
                db.add(team)
                await db.flush()
            teams[name] = team
        for email, full_name, role, team_name in ACCOUNTS:
            password = secrets.token_urlsafe(12)
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
            lines.append(f"{role.value:<10} {email:<28} {password}")
        await db.commit()
    await dispose_engines()

    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(CREDENTIALS_FILE, 0o600)
    print(f"Đã tạo dữ liệu demo. Tài khoản và mật khẩu: backend/{CREDENTIALS_FILE.name}")


if __name__ == "__main__":
    asyncio.run(seed())
