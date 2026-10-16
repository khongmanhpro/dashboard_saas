from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models import MemberRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str


class MembershipOut(BaseModel):
    id: uuid.UUID
    role: MemberRole
    team_id: uuid.UUID | None


class MeResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    member: MembershipOut
    must_change_password: bool
    permissions: list[str]


class LoginResponse(MeResponse):
    csrf_token: str


class PublicConfig(BaseModel):
    mock_mode: bool
    app_env: str
