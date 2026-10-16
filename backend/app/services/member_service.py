"""Thành viên và nhóm của workspace.

Mọi truy vấn đều lọc `workspace_id` tường minh (lớp 1), RLS là lớp 2.
Phạm vi dữ liệu (toàn bộ / nhóm / của mình) áp ngay trong câu truy vấn.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, Select, false, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Perm, Scope, can_manage_role
from app.core.security import PasswordPolicyError, hash_password, validate_password
from app.models import AuthSession, MemberRole, MemberStatus, Team, User, WorkspaceMember
from app.schemas.members import (
    MemberCreate,
    MemberOut,
    MemberUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)
from app.services import audit
from app.services.auth_service import normalize_email
from app.services.errors import ServiceError

if TYPE_CHECKING:
    from app.api.deps import AuthContext

TEAM_LEAD_ROLES = {MemberRole.OWNER, MemberRole.MANAGER, MemberRole.TEAM_LEAD}


# ---------------- Phạm vi ----------------


async def visible_team_ids(db: AsyncSession, ctx: AuthContext) -> set[uuid.UUID]:
    """Nhóm mà người này dẫn dắt hoặc đang thuộc về."""
    led = await db.scalars(
        select(Team.id).where(
            Team.workspace_id == ctx.workspace_id, Team.lead_member_id == ctx.member_id
        )
    )
    ids = set(led.all())
    if ctx.team_id:
        ids.add(ctx.team_id)
    return ids


async def _member_scope_filter(
    db: AsyncSession, ctx: AuthContext, perm: Perm
) -> ColumnElement[bool] | None:
    scope = ctx.scope(perm)
    if scope == Scope.ALL:
        return None
    if scope == Scope.TEAM:
        teams = await visible_team_ids(db, ctx)
        return or_(WorkspaceMember.team_id.in_(teams), WorkspaceMember.id == ctx.member_id)
    if scope == Scope.OWN:
        return WorkspaceMember.id == ctx.member_id
    return false()


def _members_stmt(ctx: AuthContext) -> Select[tuple[WorkspaceMember, User]]:
    return (
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id)
    )


def _member_out(member: WorkspaceMember, user: User) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        team_id=member.team_id,
        status=member.status,
        created_at=member.created_at,
    )


def _snapshot(member: WorkspaceMember) -> dict[str, Any]:
    return {
        "role": member.role.value,
        "team_id": str(member.team_id) if member.team_id else None,
        "status": member.status.value,
    }


# ---------------- Thành viên ----------------


async def list_members(db: AsyncSession, ctx: AuthContext) -> list[MemberOut]:
    stmt = _members_stmt(ctx).order_by(User.full_name)
    condition = await _member_scope_filter(db, ctx, Perm.MEMBER_VIEW)
    if condition is not None:
        stmt = stmt.where(condition)
    rows = (await db.execute(stmt)).all()
    return [_member_out(m, u) for m, u in rows]


async def _get_team(db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID) -> Team:
    team = await db.scalar(
        select(Team).where(Team.id == team_id, Team.workspace_id == ctx.workspace_id)
    )
    if team is None:
        raise ServiceError("team_not_found", 422)
    return team


async def create_member(db: AsyncSession, ctx: AuthContext, data: MemberCreate) -> MemberOut:
    if not can_manage_role(ctx.role, data.role):
        raise ServiceError("role_not_assignable", 403)
    email = normalize_email(str(data.email))
    try:
        validate_password(data.temp_password, email)
    except PasswordPolicyError as exc:
        raise ServiceError(exc.code, 422) from None
    if data.team_id:
        await _get_team(db, ctx, data.team_id)

    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=data.full_name.strip(),
            password_hash=hash_password(data.temp_password),
            must_change_password=True,
        )
        db.add(user)
    # Người đã có tài khoản ở workspace khác: chỉ thêm membership, không đổi mật khẩu của họ.
    try:
        await db.flush()
        member = WorkspaceMember(
            workspace_id=ctx.workspace_id,
            user_id=user.id,
            role=data.role,
            team_id=data.team_id,
        )
        db.add(member)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ServiceError("member_exists", 409) from None

    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="member.create",
        entity_type="member",
        entity_id=member.id,
        after={**_snapshot(member), "email": email},
        ip=ctx.ip,
    )
    await db.commit()
    await db.refresh(member)
    return _member_out(member, user)


async def update_member(
    db: AsyncSession, ctx: AuthContext, member_id: uuid.UUID, data: MemberUpdate
) -> MemberOut:
    stmt = _members_stmt(ctx).where(WorkspaceMember.id == member_id)
    row = (await db.execute(stmt)).first()
    if row is None:
        raise ServiceError("member_not_found", 404)
    target, user = row
    fields = data.model_fields_set

    if target.id == ctx.member_id and fields & {"role", "status"}:
        raise ServiceError("cannot_modify_self", 403)
    if not can_manage_role(ctx.role, target.role):
        raise ServiceError("role_not_assignable", 403)
    if "role" in fields:
        if data.role is None:
            raise ServiceError("role_required", 422)
        if not can_manage_role(ctx.role, data.role):
            raise ServiceError("role_not_assignable", 403)
    if "status" in fields and data.status is None:
        raise ServiceError("status_required", 422)
    if "team_id" in fields and data.team_id is not None:
        await _get_team(db, ctx, data.team_id)

    new_role = data.role if "role" in fields and data.role else target.role
    new_status = data.status if "status" in fields and data.status else target.status
    losing_owner = target.role == MemberRole.OWNER and (
        new_role != MemberRole.OWNER or new_status != MemberStatus.ACTIVE
    )
    if losing_owner:
        other_owners = await db.scalar(
            select(func.count()).where(
                WorkspaceMember.workspace_id == ctx.workspace_id,
                WorkspaceMember.role == MemberRole.OWNER,
                WorkspaceMember.status == MemberStatus.ACTIVE,
                WorkspaceMember.id != target.id,
            )
        )
        if not other_owners:
            raise ServiceError("last_owner", 409)

    before = _snapshot(target)
    target.role = new_role
    target.status = new_status
    if "team_id" in fields:
        target.team_id = data.team_id
    if new_status == MemberStatus.DISABLED and before["status"] != MemberStatus.DISABLED.value:
        # Khóa tài khoản thì đăng xuất ngay mọi thiết bị.
        await db.execute(
            update(AuthSession)
            .where(AuthSession.member_id == target.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=dt.datetime.now(dt.UTC))
        )
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="member.update",
        entity_type="member",
        entity_id=target.id,
        before=before,
        after=_snapshot(target),
        ip=ctx.ip,
    )
    await db.commit()
    await db.refresh(target)
    return _member_out(target, user)


# ---------------- Nhóm ----------------


async def list_teams(db: AsyncSession, ctx: AuthContext) -> list[TeamOut]:
    count = (
        select(func.count())
        .where(
            WorkspaceMember.team_id == Team.id,
            WorkspaceMember.workspace_id == Team.workspace_id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
        )
        .correlate(Team)
        .scalar_subquery()
    )
    stmt = (
        select(Team, count.label("member_count"))
        .where(Team.workspace_id == ctx.workspace_id)
        .order_by(Team.name)
    )
    if ctx.scope(Perm.TEAM_VIEW) != Scope.ALL:
        stmt = stmt.where(Team.id.in_(await visible_team_ids(db, ctx)))
    rows = (await db.execute(stmt)).all()
    return [_team_out(team, n) for team, n in rows]


def _team_out(team: Team, member_count: int) -> TeamOut:
    return TeamOut(
        id=team.id, name=team.name, lead_member_id=team.lead_member_id, member_count=member_count
    )


async def _validate_lead(db: AsyncSession, ctx: AuthContext, member_id: uuid.UUID) -> None:
    lead = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == ctx.workspace_id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
        )
    )
    if lead is None or lead.role not in TEAM_LEAD_ROLES:
        raise ServiceError("invalid_team_lead", 422)


async def _team_member_count(db: AsyncSession, team: Team) -> int:
    n = await db.scalar(
        select(func.count()).where(
            WorkspaceMember.team_id == team.id, WorkspaceMember.status == MemberStatus.ACTIVE
        )
    )
    return int(n or 0)


async def _save_team(db: AsyncSession, ctx: AuthContext, team: Team, action: str) -> TeamOut:
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ServiceError("team_name_taken", 409) from None
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action=action,
        entity_type="team",
        entity_id=team.id,
        after={
            "name": team.name,
            "lead_member_id": str(team.lead_member_id) if team.lead_member_id else None,
        },
        ip=ctx.ip,
    )
    await db.commit()
    await db.refresh(team)
    return _team_out(team, await _team_member_count(db, team))


async def create_team(db: AsyncSession, ctx: AuthContext, data: TeamCreate) -> TeamOut:
    if data.lead_member_id:
        await _validate_lead(db, ctx, data.lead_member_id)
    team = Team(
        workspace_id=ctx.workspace_id, name=data.name.strip(), lead_member_id=data.lead_member_id
    )
    db.add(team)
    return await _save_team(db, ctx, team, "team.create")


async def update_team(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID, data: TeamUpdate
) -> TeamOut:
    team = await db.scalar(
        select(Team).where(Team.id == team_id, Team.workspace_id == ctx.workspace_id)
    )
    if team is None:
        raise ServiceError("team_not_found", 404)
    fields = data.model_fields_set
    if "name" in fields:
        if not data.name:
            raise ServiceError("name_required", 422)
        team.name = data.name.strip()
    if "lead_member_id" in fields:
        if data.lead_member_id:
            await _validate_lead(db, ctx, data.lead_member_id)
        team.lead_member_id = data.lead_member_id
    return await _save_team(db, ctx, team, "team.update")
