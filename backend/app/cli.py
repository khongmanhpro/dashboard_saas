"""Lệnh quản trị. Chạy trong container `migrate` (có tài khoản quản trị DB):

    docker compose run --rm migrate python -m app.cli bootstrap-owner
    docker compose run --rm -T migrate python -m app.cli e2e-seed < accounts.json

Không bao giờ in mật khẩu ra màn hình hay log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import admin_sessionmaker, dispose_engines
from app.core.security import PasswordPolicyError, hash_password, validate_password
from app.models import MemberRole, MemberStatus, User, Workspace, WorkspaceMember
from app.services.auth_service import normalize_email
from app.services.workspace_service import create_workspace, slugify


class CliError(Exception):
    pass


async def ensure_member(
    db: AsyncSession,
    workspace: Workspace,
    *,
    email: str,
    full_name: str,
    role: MemberRole,
    password: str,
    must_change_password: bool,
    reset_password: bool,
) -> tuple[User, WorkspaceMember, bool]:
    """Tạo user + membership nếu chưa có. Trả về (user, membership, user_mới_tạo)."""
    email = normalize_email(email)
    try:
        validate_password(password, email)
    except PasswordPolicyError as exc:
        raise CliError(f"Mật khẩu không đạt yêu cầu: {exc.code}") from None
    user = await db.scalar(select(User).where(User.email == email))
    created = user is None
    if user is None:
        user = User(email=email, full_name=full_name)
        db.add(user)
    if created or reset_password:
        user.password_hash = hash_password(password)
        user.must_change_password = must_change_password
        user.is_active = True
    await db.flush()
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id
        )
    )
    if member is None:
        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
        db.add(member)
    else:
        member.role = role
        member.status = MemberStatus.ACTIVE
    await db.flush()
    return user, member, created


async def get_or_create_workspace(db: AsyncSession, name: str, slug: str) -> Workspace:
    ws = await db.scalar(select(Workspace).where(Workspace.slug == slug))
    return ws or await create_workspace(db, name, slug)


async def bootstrap_owner() -> str:
    s = get_settings()
    name = s.bootstrap_workspace_name.strip()
    email = s.bootstrap_owner_email.strip()
    password = s.bootstrap_owner_password.get_secret_value()
    if not (name and email and password):
        raise CliError(
            "Cần điền BOOTSTRAP_WORKSPACE_NAME, BOOTSTRAP_OWNER_EMAIL, BOOTSTRAP_OWNER_PASSWORD"
        )
    async with admin_sessionmaker()() as db:
        ws = await get_or_create_workspace(db, name, slugify(name))
        _, _, created = await ensure_member(
            db,
            ws,
            email=email,
            full_name="Chủ sở hữu",
            role=MemberRole.OWNER,
            password=password,
            must_change_password=True,
            reset_password=False,
        )
        await db.commit()
    if created:
        return f"Đã tạo chủ sở hữu cho workspace '{name}'. Hãy đăng nhập và đổi mật khẩu."
    return "Tài khoản đã tồn tại, giữ nguyên mật khẩu hiện tại."


async def e2e_seed(payload: dict[str, Any]) -> str:
    """Tạo workspace và tài khoản cho Playwright. Chỉ chạy ở development/test."""
    if get_settings().app_env not in ("development", "test"):
        raise CliError("e2e-seed chỉ chạy ở môi trường development/test")
    async with admin_sessionmaker()() as db:
        ws = await get_or_create_workspace(db, payload["workspace"], slugify(payload["workspace"]))
        for acc in payload["accounts"]:
            await ensure_member(
                db,
                ws,
                email=acc["email"],
                full_name=acc["full_name"],
                role=MemberRole(acc["role"]),
                password=acc["password"],
                must_change_password=bool(acc.get("must_change_password", False)),
                reset_password=True,
            )
        await db.commit()
    return f"Đã chuẩn bị {len(payload['accounts'])} tài khoản e2e."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "bootstrap-owner", help="Tạo workspace và chủ sở hữu đầu tiên từ biến BOOTSTRAP_*"
    )
    sub.add_parser("e2e-seed", help="Đọc JSON từ stdin, tạo tài khoản cho test giao diện")
    args = parser.parse_args(argv)

    async def run() -> str:
        try:
            if args.command == "bootstrap-owner":
                return await bootstrap_owner()
            return await e2e_seed(json.load(sys.stdin))
        finally:
            await dispose_engines()

    try:
        print(asyncio.run(run()))
    except CliError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
