"""Danh sách Trang và gán người phụ trách (Bước 6, quyền `page.assign`)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessManager,
    Lead,
    MemberRole,
    MemberStatus,
    Page,
    PageAssignment,
    User,
    WorkspaceMember,
    WorkspaceSettings,
)
from app.schemas.bms import NamedRefOpt, PageList, PageRow
from app.services import audit
from app.services.assignment import assign_page, end_assignment
from app.services.errors import ServiceError

if TYPE_CHECKING:
    from app.api.deps import AuthContext

NEW_PAGE_DAYS = 7


async def list_pages(
    db: AsyncSession, ctx: AuthContext, *, now: dt.datetime | None = None
) -> PageList:
    now = now or dt.datetime.now(dt.UTC)
    rows = (
        await db.execute(
            select(Page, BusinessManager.name.label("bm_name"))
            .join(BusinessManager, BusinessManager.id == Page.business_manager_id)
            .order_by(Page.is_tracked.desc(), Page.name)
        )
    ).all()
    current = {
        page_id: (member_id, since, name)
        for page_id, member_id, since, name in (
            await db.execute(
                select(
                    PageAssignment.page_id,
                    PageAssignment.member_id,
                    PageAssignment.valid_from,
                    User.full_name,
                )
                .join(WorkspaceMember, WorkspaceMember.id == PageAssignment.member_id)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(PageAssignment.valid_to.is_(None))
            )
        ).all()
    }
    leads = dict(
        (
            await db.execute(
                select(Lead.page_id, func.count())
                .where(
                    Lead.first_inbound_at >= now - dt.timedelta(days=7),
                    Lead.merged_into_lead_id.is_(None),
                )
                .group_by(Lead.page_id)
            )
        ).all()
    )
    pages = []
    for row in rows:
        page: Page = row.Page
        owner = current.get(page.id)
        pages.append(
            PageRow(
                id=page.id,
                fb_page_id=page.fb_page_id,
                name=page.name,
                business_manager=row.bm_name,
                is_tracked=page.is_tracked,
                untracked_reason=page.untracked_reason,
                webhook_subscribed=page.webhook_subscribed_at is not None,
                owner=NamedRefOpt(id=owner[0], name=owner[2]) if owner else None,
                owner_since=owner[1] if owner else None,
                leads_7d=int(leads.get(page.id, 0)),
                is_new=page.created_at >= now - dt.timedelta(days=NEW_PAGE_DAYS) and owner is None,
            )
        )
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    one_page = bool(settings and settings.one_page_per_member)
    busy = {owner[0] for owner in current.values()}
    candidates = [
        NamedRefOpt(id=mid, name=name)
        for mid, name in (
            await db.execute(
                select(WorkspaceMember.id, User.full_name)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(
                    WorkspaceMember.status == MemberStatus.ACTIVE,
                    WorkspaceMember.role != MemberRole.VIEWER,
                )
                .order_by(User.full_name)
            )
        ).all()
        if not (one_page and mid in busy)
    ]
    return PageList(pages=pages, candidates=candidates, one_page_per_member=one_page)


async def set_owner(
    db: AsyncSession,
    ctx: AuthContext,
    page_id: uuid.UUID,
    member_id: uuid.UUID | None,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Đổi người phụ trách từ bây giờ. Khách cũ giữ người cũ (gán theo lúc tin đầu tiên)."""
    now = now or dt.datetime.now(dt.UTC)
    page = await db.scalar(select(Page).where(Page.id == page_id))
    if page is None:
        raise ServiceError("page_not_found", 404)
    if not page.is_tracked:
        raise ServiceError("page_not_tracked", 409)
    before = await db.scalar(
        select(PageAssignment.member_id).where(
            PageAssignment.page_id == page.id, PageAssignment.valid_to.is_(None)
        )
    )
    if member_id is None:
        await end_assignment(db, page, now)
    else:
        member = await db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.id == member_id,
                WorkspaceMember.status == MemberStatus.ACTIVE,
                WorkspaceMember.role != MemberRole.VIEWER,
            )
        )
        if member is None:
            raise ServiceError("member_not_found", 404)
        assigned_by = await db.get(WorkspaceMember, ctx.member_id)
        await assign_page(
            db, page, member, now, assigned_by=assigned_by, reason="[Gán trên màn hình Kết nối BM]"
        )
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="page.assigned" if member_id else "page.unassigned",
        entity_type="page",
        entity_id=page.id,
        before={"member_id": str(before) if before else None},
        after={"member_id": str(member_id) if member_id else None},
        ip=ctx.ip,
    )
    await db.commit()
