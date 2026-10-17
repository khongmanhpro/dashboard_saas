"""Bảng của Bước 2: RLS, hàm định tuyến webhook, ràng buộc người phụ trách."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import TenantContext, _app_sessionmaker, set_tenant
from app.models import (
    BusinessManager,
    Contact,
    Lead,
    LeadSource,
    MemberRole,
    Message,
    MessageDirection,
    Page,
    PageAssignment,
    WorkspaceStatus,
)
from tests.integration import factories as f

pytestmark = pytest.mark.integration

T0 = dt.datetime(2026, 10, 1, 2, 0, tzinfo=dt.UTC)


@pytest.fixture
async def app_db() -> AsyncIterator[AsyncSession]:
    async with _app_sessionmaker()() as session:
        yield session


async def _seed_workspace(db: AsyncSession, tag: str) -> dict[str, object]:
    ws = await f.create_workspace(db, f"[Workspace {tag}]")
    page = await f.create_page(db, ws, name=f"[Trang {tag}]")
    contact = Contact(workspace_id=ws.id, page_id=page.id, psid=f"psid-{tag}", first_seen_at=T0)
    db.add(contact)
    await db.flush()
    lead = Lead(
        workspace_id=ws.id,
        page_id=page.id,
        contact_id=contact.id,
        source=LeadSource.MESSAGE,
        first_inbound_at=T0,
        result_due_at=T0 + dt.timedelta(hours=48),
    )
    db.add(lead)
    await db.flush()
    db.add(
        Message(
            workspace_id=ws.id,
            page_id=page.id,
            contact_id=contact.id,
            lead_id=lead.id,
            mid=f"m_{tag}",
            direction=MessageDirection.IN,
            sent_at=T0,
            text="[Tin nhắn mẫu]",
        )
    )
    await db.flush()
    return {"ws": ws, "page": page}


async def test_app_role_sees_only_current_workspace(
    admin_db: AsyncSession, app_db: AsyncSession
) -> None:
    a = await _seed_workspace(admin_db, "A")
    await _seed_workspace(admin_db, "B")
    await admin_db.commit()

    for model in (BusinessManager, Page, Contact, Lead, Message):
        assert await app_db.scalar(select(func.count()).select_from(model)) == 0, model

    await set_tenant(app_db, TenantContext(workspace_id=a["ws"].id, user_id=None))  # type: ignore[attr-defined]
    for model in (BusinessManager, Page, Contact, Lead, Message):
        assert await app_db.scalar(select(func.count()).select_from(model)) == 1, model


async def test_route_page_returns_only_workspace_id(
    admin_db: AsyncSession, app_db: AsyncSession
) -> None:
    ws = await f.create_workspace(admin_db)
    tracked = await f.create_page(admin_db, ws)
    untracked = await f.create_page(admin_db, ws, is_tracked=False)
    suspended_ws = await f.create_workspace(admin_db)
    suspended_ws.status = WorkspaceStatus.SUSPENDED
    on_suspended = await f.create_page(admin_db, suspended_ws)
    await admin_db.commit()

    async def route(fb_page_id: str) -> object:
        return await app_db.scalar(text("SELECT app_route_page(:p)"), {"p": fb_page_id})

    # Không có ngữ cảnh tenant: không đọc được pages, nhưng vẫn định tuyến được.
    assert await app_db.scalar(select(func.count()).select_from(Page)) == 0
    assert await route(tracked.fb_page_id) == ws.id
    assert await route(untracked.fb_page_id) is None
    assert await route(on_suspended.fb_page_id) is None
    assert await route("không-tồn-tại") is None


async def test_route_page_function_is_locked_down(admin_db: AsyncSession) -> None:
    row = (
        await admin_db.execute(
            text(
                "SELECT p.prosecdef, p.proconfig,"
                " has_function_privilege(:r, 'app_route_page(text)', 'EXECUTE'),"
                " has_function_privilege('public', 'app_route_page(text)', 'EXECUTE')"
                " FROM pg_proc p WHERE p.proname = 'app_route_page'"
            ),
            {"r": get_settings().postgres_app_user},
        )
    ).one()
    secdef, config, app_can, public_can = row
    assert secdef is True
    assert any(c.startswith("search_path=") for c in config)
    assert app_can is True
    assert public_can is False


async def test_page_cannot_have_two_owners_at_once(admin_db: AsyncSession) -> None:
    ws = await f.create_workspace(admin_db)
    page = await f.create_page(admin_db, ws)
    m1 = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
    m2 = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
    admin_db.add(
        PageAssignment(
            workspace_id=ws.id,
            page_id=page.id,
            member_id=m1.id,
            valid_from=T0,
            valid_to=T0 + dt.timedelta(days=5),
        )
    )
    # Nối tiếp ngay tại mốc kết thúc: hợp lệ (khoảng nửa mở).
    admin_db.add(
        PageAssignment(
            workspace_id=ws.id,
            page_id=page.id,
            member_id=m2.id,
            valid_from=T0 + dt.timedelta(days=5),
        )
    )
    await admin_db.commit()

    admin_db.add(
        PageAssignment(
            workspace_id=ws.id,
            page_id=page.id,
            member_id=m1.id,
            valid_from=T0 + dt.timedelta(days=9),
        )
    )
    with pytest.raises((IntegrityError, DBAPIError), match="ex_page_assignments_no_overlap"):
        await admin_db.commit()


async def test_tracked_fb_page_id_is_unique_across_workspaces(admin_db: AsyncSession) -> None:
    ws_a = await f.create_workspace(admin_db)
    ws_b = await f.create_workspace(admin_db)
    await f.create_page(admin_db, ws_a, fb_page_id="100000000000001")
    # Workspace khác lưu cùng Trang nhưng không theo dõi thì được.
    await f.create_page(admin_db, ws_b, fb_page_id="100000000000001", is_tracked=False)
    await admin_db.commit()
    await f.create_page(admin_db, ws_b, fb_page_id="100000000000002")
    page = await admin_db.scalar(
        select(Page).where(Page.fb_page_id == "100000000000001", Page.workspace_id == ws_b.id)
    )
    assert page is not None
    page.is_tracked = True
    with pytest.raises(IntegrityError, match="uq_pages_tracked_fb_page_id"):
        await admin_db.commit()
