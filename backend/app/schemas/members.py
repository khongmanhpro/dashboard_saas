from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import MemberRole, MemberStatus


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: MemberRole
    team_id: uuid.UUID | None
    status: MemberStatus
    created_at: dt.datetime


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: MemberRole
    team_id: uuid.UUID | None = None
    # Mật khẩu tạm do Quản lý đặt; người dùng bị bắt đổi ở lần đăng nhập đầu.
    temp_password: str = Field(min_length=1, max_length=256)


class MemberUpdate(BaseModel):
    """Chỉ trường nào được gửi lên mới được đổi. `team_id: null` nghĩa là rời nhóm."""

    model_config = ConfigDict(extra="forbid")

    role: MemberRole | None = None
    team_id: uuid.UUID | None = None
    status: MemberStatus | None = None


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    lead_member_id: uuid.UUID | None
    member_count: int


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    lead_member_id: uuid.UUID | None = None


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    lead_member_id: uuid.UUID | None = None
