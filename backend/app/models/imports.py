"""Nhật ký nhập Excel (Bước 6). Không lưu file gốc, không lưu mật khẩu."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk, workspace_fk


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (created_by_member_id)",
            name="fk_import_jobs_created_by",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    type: Mapped[str] = mapped_column(String(32))  # members
    file_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))  # previewed | applied
    rows_total: Mapped[int] = mapped_column(Integer)
    rows_ok: Mapped[int] = mapped_column(Integer)
    rows_failed: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_member_id: Mapped[uuid.UUID | None]
    created_at: Mapped[dt.datetime] = created_at_col()
    applied_at: Mapped[dt.datetime | None]
