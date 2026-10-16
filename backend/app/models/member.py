from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk, workspace_fk
from app.models.enums import MemberRole, MemberStatus


class WorkspaceMember(Base):
    """Một người trong một workspace, với đúng một vai trò.

    Việc phụ trách Trang nằm ở `page_assignments` (Bước 2), độc lập với vai trò:
    Trưởng nhóm hay Quản lý cũng có thể phụ trách Trang.
    """

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "team_id"],
            ["teams.workspace_id", "teams.id"],
            ondelete="SET NULL (team_id)",
            use_alter=True,
            name="fk_workspace_members_team",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[MemberRole] = mapped_column(str_enum(MemberRole, "member_role"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    status: Mapped[MemberStatus] = mapped_column(
        str_enum(MemberStatus, "member_status"), server_default=MemberStatus.ACTIVE.value
    )
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Team(Base):
    """Nhóm nhân viên, có thể có một Trưởng nhóm."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "lead_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (lead_member_id)",
            name="fk_teams_lead_member",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    name: Mapped[str] = mapped_column(String(120))
    lead_member_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()
