from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthContext, DbSession, require
from app.core.rbac import Perm
from app.schemas.members import (
    MemberCreate,
    MemberOut,
    MemberUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)
from app.services import member_service

router = APIRouter(prefix="/api", tags=["members"])

CanViewMembers = Annotated[AuthContext, Depends(require(Perm.MEMBER_VIEW))]
CanManageMembers = Annotated[AuthContext, Depends(require(Perm.MEMBER_MANAGE))]
CanViewTeams = Annotated[AuthContext, Depends(require(Perm.TEAM_VIEW))]
CanManageTeams = Annotated[AuthContext, Depends(require(Perm.TEAM_MANAGE))]


@router.get("/members", response_model=list[MemberOut])
async def list_members(ctx: CanViewMembers, db: DbSession) -> list[MemberOut]:
    return await member_service.list_members(db, ctx)


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def create_member(body: MemberCreate, ctx: CanManageMembers, db: DbSession) -> MemberOut:
    return await member_service.create_member(db, ctx, body)


@router.patch("/members/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: uuid.UUID, body: MemberUpdate, ctx: CanManageMembers, db: DbSession
) -> MemberOut:
    return await member_service.update_member(db, ctx, member_id, body)


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(ctx: CanViewTeams, db: DbSession) -> list[TeamOut]:
    return await member_service.list_teams(db, ctx)


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(body: TeamCreate, ctx: CanManageTeams, db: DbSession) -> TeamOut:
    return await member_service.create_team(db, ctx, body)


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: uuid.UUID, body: TeamUpdate, ctx: CanManageTeams, db: DbSession
) -> TeamOut:
    return await member_service.update_team(db, ctx, team_id, body)
