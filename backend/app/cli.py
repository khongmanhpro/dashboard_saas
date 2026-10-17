"""Lệnh quản trị. Chạy trong container `migrate` (có tài khoản quản trị DB):

    docker compose run --rm migrate python -m app.cli bootstrap-owner
    docker compose run --rm -T migrate python -m app.cli e2e-seed < accounts.json

Không bao giờ in mật khẩu ra màn hình hay log.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
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


def _e2e_event(fb_page_id: str, psid: str, kind: str, mid: str, at: Any, text: str) -> Any:
    from app.meta.events import MessageEvent

    return MessageEvent(
        kind=kind,
        fb_page_id=fb_page_id,
        psid=psid,
        mid=mid,
        sent_at=at,
        text=text,
        has_attachments=False,
        app_id=None,
        metadata=None,
        referral=None,
        raw={},
    )


async def _seed_e2e_leads(
    db: AsyncSession,
    ws: Workspace,
    members: dict[str, WorkspaceMember],
    specs: list[dict[str, Any]],
) -> dict[str, str]:
    """Mỗi lần chạy tạo khách mới (PSID mới) trên Trang E2E, đi qua đúng service của worker."""
    from app.models import BusinessManager, Contact, Lead, Page
    from app.services import inbound
    from app.services.assignment import assign_page, owner_at

    now = dt.datetime.now(dt.UTC)
    bm = await db.scalar(
        select(BusinessManager).where(
            BusinessManager.workspace_id == ws.id,
            BusinessManager.fb_business_id == "900000000000900",
        )
    )
    if bm is None:
        bm = BusinessManager(workspace_id=ws.id, fb_business_id="900000000000900", name="[BM E2E]")
        db.add(bm)
        await db.flush()
    rules = await inbound.load_rules(db, ws.id)
    lead_ids: dict[str, str] = {}
    for spec in specs:
        page = await db.scalar(
            select(Page).where(Page.workspace_id == ws.id, Page.fb_page_id == spec["fb_page_id"])
        )
        if page is None:
            page = Page(
                workspace_id=ws.id,
                business_manager_id=bm.id,
                fb_page_id=spec["fb_page_id"],
                name=spec["page"],
            )
            db.add(page)
            await db.flush()
        member = members[spec["owner"]]
        if await owner_at(db, page.id, now - dt.timedelta(minutes=10)) != member.id:
            await assign_page(db, page, member, now - dt.timedelta(minutes=30), reason="[E2E]")
        # `count` > 1: tạo nhiều khách (để người phụ trách đủ số khách tối thiểu được tính điểm).
        count = int(spec.get("count", 1))
        reply_seconds = spec.get("reply_seconds")
        for i in range(count):
            psid = spec["psid"] if count == 1 else f"{spec['psid']}-{i}"
            sent_at = now - dt.timedelta(minutes=10) + dt.timedelta(seconds=i)

            await inbound.handle_message(
                db,
                page,
                rules,
                _e2e_event(page.fb_page_id, psid, "in", f"m_{psid}", sent_at, spec["text"]),
            )
            if reply_seconds is not None:
                reply_at = sent_at + dt.timedelta(seconds=int(reply_seconds))
                await inbound.handle_message(
                    db,
                    page,
                    rules,
                    _e2e_event(
                        page.fb_page_id, psid, "echo", f"m_{psid}_r", reply_at, "[Trả lời E2E]"
                    ),
                )
            contact = await db.scalar(
                select(Contact).where(Contact.page_id == page.id, Contact.psid == psid)
            )
            if contact is None:
                raise CliError("không tạo được khách e2e")
            contact.display_name = spec["name"] if count == 1 else f"{spec['name']} {i}"
            lead_id = await db.scalar(select(Lead.id).where(Lead.contact_id == contact.id))
            if spec.get("ad_id"):
                # Khách bấm quảng cáo: gắn chiến dịch khi đồng bộ (Bước 7).
                lead_row = await db.get(Lead, lead_id)
                if lead_row is not None:
                    lead_row.fb_ad_id = str(spec["ad_id"])
            if i == 0:
                lead_ids[spec["key"]] = str(lead_id)
    return lead_ids


async def _connect_e2e_ads(db: AsyncSession, ws: Workspace, token: str) -> None:
    """BM giả có tài khoản quảng cáo cho e2e Bước 7. Chỉ nhận mã `MOCK-...` của client Graph giả."""
    from app.core.crypto import get_token_cipher, last4
    from app.meta.graph import MockGraphClient
    from app.models import BusinessManager
    from app.services.bm_service import sync_bm

    if not token.startswith("MOCK-") or not get_settings().mock_mode:
        raise CliError("ads_token chỉ nhận mã giả khi MOCK_MODE=true")
    info = await MockGraphClient().inspect_token(token)
    bm = await db.scalar(
        select(BusinessManager).where(
            BusinessManager.workspace_id == ws.id,
            BusinessManager.fb_business_id == info.business_ids[0],
        )
    )
    if bm is None:
        bm = BusinessManager(
            workspace_id=ws.id, fb_business_id=info.business_ids[0], name="[BM E2E quảng cáo]"
        )
        db.add(bm)
        await db.flush()
    bm.token_ciphertext = get_token_cipher().encrypt(token)
    bm.token_last4 = last4(token)
    await sync_bm(db, bm, dt.datetime.now(dt.UTC), MockGraphClient(), kind="e2e")


async def e2e_seed(payload: dict[str, Any]) -> str:
    """Tạo workspace, tài khoản và (tùy chọn) khách cho Playwright. Chỉ chạy ở development/test.

    Có `leads` trong payload thì in ra JSON `{"leads": {key: lead_id}}` để test mở thẳng hồ sơ.
    """
    if get_settings().app_env not in ("development", "test"):
        raise CliError("e2e-seed chỉ chạy ở môi trường development/test")
    async with admin_sessionmaker()() as db:
        ws = await get_or_create_workspace(db, payload["workspace"], slugify(payload["workspace"]))
        members: dict[str, WorkspaceMember] = {}
        for acc in payload["accounts"]:
            _, members[acc["email"]], _ = await ensure_member(
                db,
                ws,
                email=acc["email"],
                full_name=acc["full_name"],
                role=MemberRole(acc["role"]),
                password=acc["password"],
                must_change_password=bool(acc.get("must_change_password", False)),
                reset_password=True,
            )
        lead_ids = await _seed_e2e_leads(db, ws, members, payload.get("leads", []))
        if payload.get("ads_token"):
            await _connect_e2e_ads(db, ws, str(payload["ads_token"]))
        await db.commit()
    if payload.get("ads_token"):
        from app.core.db import TenantContext, app_sessionmaker, set_tenant
        from app.services import meta_sync

        async with app_sessionmaker()() as app_db:
            await set_tenant(app_db, TenantContext(workspace_id=ws.id, user_id=None))
            await meta_sync.sync_workspace(app_db, ws.id, dt.datetime.now(dt.UTC))
            await app_db.commit()
    if payload.get("leads"):
        return json.dumps({"leads": lead_ids})
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
