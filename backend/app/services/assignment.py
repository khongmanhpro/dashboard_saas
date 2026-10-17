"""Người phụ trách Trang theo thời gian (`page_assignments`).

Khách tính cho người phụ trách Trang **tại thời điểm tin đầu tiên** của đợt. Đổi người thì đóng
khoảng cũ (`valid_to`) và mở khoảng mới; khách cũ giữ người cũ.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page, PageAssignment, WorkspaceMember, WorkspaceSettings
from app.services.errors import ServiceError


async def owner_at(db: AsyncSession, page_id: uuid.UUID, at: dt.datetime) -> uuid.UUID | None:
    """Người phụ trách Trang tại thời điểm `at`, hoặc None nếu Trang chưa có ai."""
    result: uuid.UUID | None = await db.scalar(
        select(PageAssignment.member_id).where(
            PageAssignment.page_id == page_id,
            PageAssignment.valid_from <= at,
            (PageAssignment.valid_to.is_(None)) | (PageAssignment.valid_to > at),
        )
    )
    return result


async def _current(db: AsyncSession, page_id: uuid.UUID) -> PageAssignment | None:
    return await db.scalar(
        select(PageAssignment)
        .where(PageAssignment.page_id == page_id, PageAssignment.valid_to.is_(None))
        .with_for_update()
    )


async def end_assignment(db: AsyncSession, page: Page, at: dt.datetime) -> None:
    """Trang không còn người phụ trách kể từ `at`."""
    current = await _current(db, page.id)
    if current is None:
        return
    if at < current.valid_from:
        raise ServiceError("assignment_before_current", 409)
    current.valid_to = at
    await db.flush()


async def assign_page(
    db: AsyncSession,
    page: Page,
    member: WorkspaceMember,
    at: dt.datetime,
    *,
    assigned_by: WorkspaceMember | None = None,
    reason: str | None = None,
) -> PageAssignment:
    """Giao Trang cho `member` kể từ `at`. Người đang phụ trách (nếu có) kết thúc tại `at`."""
    if member.workspace_id != page.workspace_id:
        raise ServiceError("member_not_found", 404)
    settings = await db.get(WorkspaceSettings, page.workspace_id)
    if settings is not None and settings.one_page_per_member:
        other = await db.scalar(
            select(PageAssignment.page_id).where(
                PageAssignment.member_id == member.id,
                PageAssignment.page_id != page.id,
                PageAssignment.valid_to.is_(None),
            )
        )
        if other is not None:
            raise ServiceError("member_already_has_page", 409)

    current = await _current(db, page.id)
    if current is not None:
        if current.member_id == member.id:
            return current
        if at <= current.valid_from:
            raise ServiceError("assignment_before_current", 409)
        current.valid_to = at
        await db.flush()

    assignment = PageAssignment(
        workspace_id=page.workspace_id,
        page_id=page.id,
        member_id=member.id,
        valid_from=at,
        assigned_by_member_id=assigned_by.id if assigned_by else None,
        reason=reason,
    )
    db.add(assignment)
    await db.flush()
    return assignment
