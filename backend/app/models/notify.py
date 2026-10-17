"""Nhắc việc và đăng ký thông báo đẩy (Bước 5)."""

from __future__ import annotations

import datetime as dt
import uuid

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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, uuid_pk, workspace_fk
from app.models.enums import NotificationType


class Notification(Base):
    """Một lần nhắc việc. `dedupe_key` bảo đảm mỗi mốc chỉ nhắc một lần.

    `title`/`body` không bao giờ chứa SĐT hay nội dung tin nhắn của khách.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key"),
        ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="CASCADE",
            name="fk_notifications_member",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="SET NULL (lead_id)",
            name="fk_notifications_lead",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (actor_member_id)",
            name="fk_notifications_actor",
        ),
        Index("ix_notifications_member_created", "member_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Không index riêng: uq (workspace_id, dedupe_key) đã bắt đầu bằng workspace_id.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    member_id: Mapped[uuid.UUID]
    lead_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_member_id: Mapped[uuid.UUID | None]
    type: Mapped[NotificationType] = mapped_column(str_enum(NotificationType, "notification_type"))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = created_at_col()
    read_at: Mapped[dt.datetime | None]
    sent_via: Mapped[str | None] = mapped_column(String(32))  # "push" nếu gửi được ít nhất 1 máy


class PushSubscription(Base):
    """Một trình duyệt/điện thoại đã cho phép nhận thông báo đẩy."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "endpoint"),
        ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="CASCADE",
            name="fk_push_subscriptions_member",
        ),
        Index("ix_push_subscriptions_member_id", "member_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    member_id: Mapped[uuid.UUID]
    endpoint: Mapped[str] = mapped_column(String(1000))
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = created_at_col()
    last_success_at: Mapped[dt.datetime | None]
    failure_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
