"""Cảnh báo Telegram (Bước 7). Nội dung gửi đi không có SĐT, không có nội dung tin nhắn."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, updated_at_col, uuid_pk, workspace_fk


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (UniqueConstraint("workspace_id", "type"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    type: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[dt.datetime] = updated_at_col()


class AlertDelivery(Base):
    """Một lần gửi. `dedupe_key` = quy tắc × đối tượng × ngày: mỗi khóa chỉ gửi một lần."""

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key"),
        CheckConstraint("status IN ('sent', 'failed', 'mock')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    target: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[dt.datetime]
