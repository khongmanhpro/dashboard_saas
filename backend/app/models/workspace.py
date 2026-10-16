from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, String, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import WorkspaceStatus


class Workspace(Base):
    """Một doanh nghiệp dùng hệ thống (tenant)."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Ho_Chi_Minh")
    plan_code: Mapped[str] = mapped_column(String(32), server_default="internal")
    status: Mapped[WorkspaceStatus] = mapped_column(
        str_enum(WorkspaceStatus, "workspace_status"), server_default=WorkspaceStatus.ACTIVE.value
    )
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class WorkspaceSettings(Base):
    """Quy tắc đo lường của workspace. Giá trị mặc định lấy từ .env khi tạo workspace."""

    __tablename__ = "workspace_settings"
    __table_args__ = (
        CheckConstraint("work_start < work_end", name="work_hours_order"),
        CheckConstraint(
            "slow_reply_minutes > 0 AND result_deadline_hours > 0 AND lead_session_gap_days > 0"
            " AND posts_per_week_target >= 0 AND min_leads_for_ranking >= 0",
            name="positive_values",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    work_start: Mapped[dt.time] = mapped_column(Time, server_default=text("'08:00'"))
    work_end: Mapped[dt.time] = mapped_column(Time, server_default=text("'22:00'"))
    slow_reply_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="30")
    result_deadline_hours: Mapped[int] = mapped_column(SmallInteger, server_default="48")
    lead_session_gap_days: Mapped[int] = mapped_column(SmallInteger, server_default="30")
    posts_per_week_target: Mapped[int] = mapped_column(SmallInteger, server_default="5")
    min_leads_for_ranking: Mapped[int] = mapped_column(SmallInteger, server_default="10")
    one_page_per_member: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    staff_can_see_leaderboard: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[dt.datetime] = updated_at_col()
