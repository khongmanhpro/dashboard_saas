"""Dữ liệu nhận từ webhook: nhật ký sự kiện và form khách hàng tiềm năng."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, uuid_pk, workspace_fk
from app.models.enums import LeadgenFetchStatus, WebhookEventStatus


class WebhookEvent(Base):
    """Một sự kiện webhook đã định tuyến được sang workspace. Xóa sau 30 ngày.

    `dedupe_key` (ví dụ `mid:<mid>`, `leadgen:<id>`) chặn xử lý lặp khi Meta gửi lại.
    `error` không bao giờ chứa nội dung tin nhắn hay SĐT.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key"),
        Index("ix_webhook_events_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Không index riêng: uq (workspace_id, dedupe_key) đã bắt đầu bằng workspace_id.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    received_at: Mapped[dt.datetime] = created_at_col()
    object: Mapped[str] = mapped_column(String(32))
    fb_page_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[WebhookEventStatus] = mapped_column(
        str_enum(WebhookEventStatus, "webhook_event_status")
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    error: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[dt.datetime | None]


class LeadgenSubmission(Base):
    """Một lần khách gửi form khách hàng tiềm năng. `field_data` chỉ giữ trường cần dùng."""

    __tablename__ = "leadgen_submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_leadgen_submissions_page",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="SET NULL (lead_id)",
            name="fk_leadgen_submissions_lead",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    leadgen_id: Mapped[str] = mapped_column(String(32), unique=True)
    page_id: Mapped[uuid.UUID] = mapped_column(index=True)
    form_id: Mapped[str | None] = mapped_column(String(32))
    fb_ad_id: Mapped[str | None] = mapped_column(String(32))
    created_time: Mapped[dt.datetime]
    field_data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    fetch_status: Mapped[LeadgenFetchStatus] = mapped_column(
        str_enum(LeadgenFetchStatus, "leadgen_fetch_status")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    created_at: Mapped[dt.datetime] = created_at_col()
