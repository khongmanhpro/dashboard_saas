"""Khách (cặp Trang + PSID), các đợt khách, tin nhắn và lịch sử của đợt."""

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
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk, workspace_fk
from app.models.enums import (
    LeadEventType,
    LeadSource,
    LeadStatus,
    LostReason,
    MessageDirection,
)


class Contact(Base):
    """Một người nhắn tin vào một Trang (PSID là ID riêng theo Trang).

    Mở đợt mới phải khóa dòng này (`SELECT … FOR UPDATE`) để hai sự kiện đến cùng lúc
    không tạo ra hai đợt.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("page_id", "psid"),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_contacts_page",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    page_id: Mapped[uuid.UUID]
    psid: Mapped[str] = mapped_column(String(64))
    # Tên hiển thị: từ form leadgen, sau này từ Graph API. NULL thì giao diện hiện "Khách ···1234".
    display_name: Mapped[str | None] = mapped_column(String(200))
    first_seen_at: Mapped[dt.datetime]
    last_inbound_at: Mapped[dt.datetime | None]
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Lead(Base):
    """Một đợt khách. Người phụ trách cố định tại thời điểm tin đầu tiên của đợt.

    `response_business_seconds`: số giây **trong giờ làm việc** từ tin đầu tiên của khách tới
    tin trả lời đầu tiên không tự động của Trang. NULL khi chưa trả lời hoặc khách đến từ form.
    """

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("contact_id", "episode_no"),
        CheckConstraint(
            "status <> 'won' OR (won_value_vnd IS NOT NULL AND won_value_vnd > 0)",
            name="won_has_value",
        ),
        CheckConstraint("status <> 'lost' OR lost_reason IS NOT NULL", name="lost_has_reason"),
        CheckConstraint(
            "status <> 'callback' OR callback_at IS NOT NULL", name="callback_has_time"
        ),
        CheckConstraint("episode_no >= 1", name="episode_positive"),
        CheckConstraint(
            "response_business_seconds IS NULL OR response_business_seconds >= 0",
            name="response_non_negative",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_leads_page",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
            name="fk_leads_contact",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "owner_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="RESTRICT",
            name="fk_leads_owner",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "merged_into_lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="SET NULL (merged_into_lead_id)",
            name="fk_leads_merged_into",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "ad_id"],
            ["ads.workspace_id", "ads.id"],
            ondelete="SET NULL (ad_id)",
            name="fk_leads_ad",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="SET NULL (campaign_id)",
            name="fk_leads_campaign",
        ),
        Index("ix_leads_campaign_first_inbound", "campaign_id", "first_inbound_at"),
        Index("ix_leads_workspace_owner", "workspace_id", "owner_member_id"),
        Index("ix_leads_page_first_inbound", "page_id", "first_inbound_at"),
        Index("ix_leads_workspace_first_inbound", "workspace_id", "first_inbound_at"),
        Index("ix_leads_workspace_phone", "workspace_id", "phone"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    page_id: Mapped[uuid.UUID]
    contact_id: Mapped[uuid.UUID | None]
    episode_no: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("1"))
    owner_member_id: Mapped[uuid.UUID | None]
    source: Mapped[LeadSource] = mapped_column(str_enum(LeadSource, "lead_source"))
    fb_ad_id: Mapped[str | None] = mapped_column(String(32))
    # Gắn qua fb_ad_id khi QC đã đồng bộ (Bước 7).
    ad_id: Mapped[uuid.UUID | None]
    campaign_id: Mapped[uuid.UUID | None]
    referral: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_inbound_at: Mapped[dt.datetime]
    first_inbound_mid: Mapped[str | None] = mapped_column(String(200))
    first_reply_at: Mapped[dt.datetime | None]
    first_reply_mid: Mapped[str | None] = mapped_column(String(200))
    response_business_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[LeadStatus] = mapped_column(
        str_enum(LeadStatus, "lead_status"), server_default=LeadStatus.NEW.value
    )
    status_changed_at: Mapped[dt.datetime | None]
    callback_at: Mapped[dt.datetime | None]
    won_value_vnd: Mapped[int | None] = mapped_column(BigInteger)
    lost_reason: Mapped[LostReason | None] = mapped_column(str_enum(LostReason, "lost_reason"))
    lost_note: Mapped[str | None] = mapped_column(String(500))
    called_at: Mapped[dt.datetime | None]
    phone: Mapped[str | None] = mapped_column(String(15))
    phone_source: Mapped[str | None] = mapped_column(String(32))
    phone_captured_at: Mapped[dt.datetime | None]
    result_due_at: Mapped[dt.datetime]
    result_at: Mapped[dt.datetime | None]
    last_inbound_at: Mapped[dt.datetime | None]
    # Đợt từ form đã gộp vào đợt nhắn tin cùng SĐT (quyết định #16): ẩn khỏi danh sách và điểm.
    merged_into_lead_id: Mapped[uuid.UUID | None]
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class LeadPhone(Base):
    """Mọi SĐT nhận được của một đợt khách. `leads.phone` là số đầu tiên."""

    __tablename__ = "lead_phones"
    __table_args__ = (
        UniqueConstraint("lead_id", "phone"),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="CASCADE",
            name="fk_lead_phones_lead",
        ),
        Index("ix_lead_phones_workspace_phone", "workspace_id", "phone"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    lead_id: Mapped[uuid.UUID]
    phone: Mapped[str] = mapped_column(String(15))
    source: Mapped[str] = mapped_column(String(16))  # message | leadgen
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    detected_at: Mapped[dt.datetime]


class Message(Base):
    """Một tin nhắn. `lead_id` NULL khi Trang nhắn trước hoặc echo đến trước tin của khách.

    `text` bị xóa sau 180 ngày (quyết định #19), số liệu giữ lại.
    """

    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_messages_page",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
            name="fk_messages_contact",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="SET NULL (lead_id)",
            name="fk_messages_lead",
        ),
        Index("ix_messages_contact_sent", "contact_id", "sent_at"),
        Index("ix_messages_lead_id", "lead_id"),
        Index("ix_messages_workspace_id", "workspace_id"),
        # Cho job hạn lưu (app_purge_expired_data): chỉ những tin còn nội dung.
        Index(
            "ix_messages_sent_at_with_text",
            "sent_at",
            postgresql_where=sql_text("text IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    page_id: Mapped[uuid.UUID]
    contact_id: Mapped[uuid.UUID]
    lead_id: Mapped[uuid.UUID | None]
    mid: Mapped[str] = mapped_column(String(200), unique=True)
    direction: Mapped[MessageDirection] = mapped_column(
        str_enum(MessageDirection, "message_direction")
    )
    is_echo: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    app_id: Mapped[str | None] = mapped_column(String(32))
    is_automated: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    sent_at: Mapped[dt.datetime]
    text: Mapped[str | None] = mapped_column(Text)
    has_attachments: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = created_at_col()


class LeadEvent(Base):
    """Lịch sử của một đợt khách (tạo, trả lời, đổi trạng thái…)."""

    __tablename__ = "lead_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="CASCADE",
            name="fk_lead_events_lead",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (actor_member_id)",
            name="fk_lead_events_actor",
        ),
        Index("ix_lead_events_lead_occurred", "lead_id", "occurred_at"),
        Index("ix_lead_events_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    lead_id: Mapped[uuid.UUID]
    type: Mapped[LeadEventType] = mapped_column(str_enum(LeadEventType, "lead_event_type"))
    actor_member_id: Mapped[uuid.UUID | None]
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[dt.datetime] = created_at_col()
