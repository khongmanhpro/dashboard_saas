"""Tài sản Meta: BM, Trang, và lịch sử người phụ trách Trang."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk, workspace_fk
from app.models.enums import ConnectionStatus


class BusinessManager(Base):
    """Một BM kết nối bằng người dùng hệ thống "Dashboard".

    Mã truy cập chỉ lưu dạng mã hóa Fernet (`token_ciphertext`); giao diện chỉ hiện `token_last4`.
    BM của chế độ giả lập không có mã.
    """

    __tablename__ = "business_managers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_business_id"),
        ForeignKeyConstraint(
            ["workspace_id", "connected_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (connected_by_member_id)",
            name="fk_business_managers_connected_by",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    fb_business_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    verification_status: Mapped[str | None] = mapped_column(String(32))
    system_user_id: Mapped[str | None] = mapped_column(String(32))
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_last4: Mapped[str | None] = mapped_column(String(4))
    token_fingerprint: Mapped[str | None] = mapped_column(String(64))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    status: Mapped[ConnectionStatus] = mapped_column(
        str_enum(ConnectionStatus, "bm_status"), server_default=ConnectionStatus.ACTIVE.value
    )
    status_detail: Mapped[str | None] = mapped_column(String(500))
    last_checked_at: Mapped[dt.datetime | None]
    last_synced_at: Mapped[dt.datetime | None]
    connected_by_member_id: Mapped[uuid.UUID | None]
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Page(Base):
    """Một Fanpage. Một `fb_page_id` chỉ được một workspace theo dõi (quyết định #22)."""

    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_page_id"),
        ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            ondelete="RESTRICT",
            name="fk_pages_business_manager",
        ),
        # Toàn hệ thống, không chỉ trong workspace: định tuyến webhook dựa vào đây.
        Index(
            "uq_pages_tracked_fb_page_id",
            "fb_page_id",
            unique=True,
            postgresql_where=text("is_tracked"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    business_manager_id: Mapped[uuid.UUID] = mapped_column(index=True)
    fb_page_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(120))
    page_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    webhook_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    webhook_subscribed_at: Mapped[dt.datetime | None]
    is_tracked: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    access_status: Mapped[ConnectionStatus] = mapped_column(
        str_enum(ConnectionStatus, "page_access_status"),
        server_default=ConnectionStatus.ACTIVE.value,
    )
    # Vì sao không theo dõi: other_workspace (#22), removed_from_bm, bm_disconnected.
    untracked_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class AdAccount(Base):
    """Tài khoản quảng cáo đọc được qua BM (chi tiêu đồng bộ ở Bước 7)."""

    __tablename__ = "ad_accounts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_ad_account_id"),
        ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            ondelete="CASCADE",
            name="fk_ad_accounts_business_manager",
        ),
        Index("ix_ad_accounts_business_manager_id", "business_manager_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    business_manager_id: Mapped[uuid.UUID]
    fb_ad_account_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str | None] = mapped_column(String(3))
    timezone_name: Mapped[str | None] = mapped_column(String(64))
    account_status: Mapped[int | None] = mapped_column(SmallInteger)
    access_status: Mapped[ConnectionStatus] = mapped_column(
        str_enum(ConnectionStatus, "ad_access_status"),
        server_default=ConnectionStatus.ACTIVE.value,
    )
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class SyncRun(Base):
    """Một lần kiểm tra hoặc đồng bộ với Meta. `usage`: header giới hạn gọi API, không có mã."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            ondelete="CASCADE",
            name="fk_sync_runs_business_manager",
        ),
        Index("ix_sync_runs_bm_started", "business_manager_id", "started_at"),
        Index("ix_sync_runs_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    business_manager_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[dt.datetime]
    finished_at: Mapped[dt.datetime | None]
    status: Mapped[str] = mapped_column(String(16))  # running | ok | warning | failed
    error: Mapped[str | None] = mapped_column(String(500))
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PageAssignment(Base):
    """Ai phụ trách Trang trong khoảng [valid_from, valid_to). `valid_to` NULL = đang hiệu lực.

    Migration thêm `EXCLUDE USING gist (page_id WITH =, tstzrange(valid_from, valid_to) WITH &&)`
    để một Trang không bao giờ có hai người cùng lúc (Alembic không so sánh EXCLUDE).
    """

    __tablename__ = "page_assignments"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_range"),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_page_assignments_page",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="RESTRICT",
            name="fk_page_assignments_member",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "assigned_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (assigned_by_member_id)",
            name="fk_page_assignments_assigned_by",
        ),
        Index("ix_page_assignments_member_id", "member_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    page_id: Mapped[uuid.UUID]
    member_id: Mapped[uuid.UUID]
    valid_from: Mapped[dt.datetime]
    valid_to: Mapped[dt.datetime | None]
    assigned_by_member_id: Mapped[uuid.UUID | None]
    reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = created_at_col()
