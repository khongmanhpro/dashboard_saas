from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Identity, Index, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col


class AuditLog(Base):
    """Nhật ký thao tác quan trọng. Tài khoản ứng dụng chỉ được INSERT và SELECT.

    Không bao giờ ghi mật khẩu, mã truy cập hay SĐT đầy đủ vào `before`/`after`.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_audit_logs_actor",
        ),
        Index("ix_audit_logs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Không index riêng: ix_audit_logs_workspace_created đã bắt đầu bằng workspace_id.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    actor_member_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[dt.datetime] = created_at_col()
