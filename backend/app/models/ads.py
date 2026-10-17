"""Quảng cáo (Bước 7): cấu trúc chiến dịch, số liệu theo ngày, tỉ giá của workspace.

Tiền gốc của tài khoản QC lưu ở `*_minor` (đơn vị nhỏ nhất của `currency`); `spend_vnd` quy đổi
qua `fx_rates`, NULL khi thiếu tỉ giá (decisions.md mục I).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk, workspace_fk

INSIGHT_LEVELS = ("campaign", "adset", "ad")


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_campaign_id"),
        ForeignKeyConstraint(
            ["workspace_id", "ad_account_id"],
            ["ad_accounts.workspace_id", "ad_accounts.id"],
            ondelete="CASCADE",
            name="fk_campaigns_ad_account",
        ),
        Index("ix_campaigns_ad_account_id", "ad_account_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    ad_account_id: Mapped[uuid.UUID]
    fb_campaign_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(400))
    objective: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))
    daily_budget_minor: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class AdSet(Base):
    __tablename__ = "ad_sets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_ad_set_id"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
            name="fk_ad_sets_campaign",
        ),
        Index("ix_ad_sets_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    campaign_id: Mapped[uuid.UUID]
    fb_ad_set_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(400))
    status: Mapped[str | None] = mapped_column(String(32))
    daily_budget_minor: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "fb_ad_id"),
        ForeignKeyConstraint(
            ["workspace_id", "ad_set_id"],
            ["ad_sets.workspace_id", "ad_sets.id"],
            ondelete="CASCADE",
            name="fk_ads_ad_set",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
            name="fk_ads_campaign",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="SET NULL (page_id)",
            name="fk_ads_page",
        ),
        Index("ix_ads_ad_set_id", "ad_set_id"),
        Index("ix_ads_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    ad_set_id: Mapped[uuid.UUID]
    campaign_id: Mapped[uuid.UUID]
    page_id: Mapped[uuid.UUID | None]
    fb_ad_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(400))
    status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class AdInsightDaily(Base):
    """Số liệu một ngày (theo múi giờ tài khoản QC) của một chiến dịch / nhóm / quảng cáo.

    `object_id` trỏ tới `campaigns` / `ad_sets` / `ads` tùy `level` nên không có khóa ngoại;
    `campaign_id` luôn có để lọc nhanh. `results` NULL khi mục tiêu không phải tin nhắn/form.
    """

    __tablename__ = "ad_insights_daily"
    __table_args__ = (
        UniqueConstraint("workspace_id", "level", "object_id", "date"),
        CheckConstraint("level IN ('campaign', 'adset', 'ad')", name="level_valid"),
        CheckConstraint("spend_minor >= 0", name="spend_non_negative"),
        ForeignKeyConstraint(
            ["workspace_id", "ad_account_id"],
            ["ad_accounts.workspace_id", "ad_accounts.id"],
            ondelete="CASCADE",
            name="fk_ad_insights_daily_ad_account",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
            name="fk_ad_insights_daily_campaign",
        ),
        Index("ix_ad_insights_daily_ws_level_date", "workspace_id", "level", "date"),
        Index("ix_ad_insights_daily_campaign_date", "campaign_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    ad_account_id: Mapped[uuid.UUID]
    campaign_id: Mapped[uuid.UUID]
    level: Mapped[str] = mapped_column(String(16))
    object_id: Mapped[uuid.UUID]
    date: Mapped[dt.date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    spend_minor: Mapped[int] = mapped_column(BigInteger)
    spend_vnd: Mapped[int | None] = mapped_column(BigInteger)
    impressions: Mapped[int] = mapped_column(BigInteger, server_default="0")
    reach: Mapped[int] = mapped_column(BigInteger, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, server_default="0")
    messaging_starts: Mapped[int] = mapped_column(Integer, server_default="0")
    leads: Mapped[int] = mapped_column(Integer, server_default="0")
    results: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[dt.datetime] = updated_at_col()


class FxRate(Base):
    """Tỉ giá do Chủ sở hữu nhập. Ngày D dùng dòng có `effective_from` gần nhất ≤ D."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "currency", "effective_from"),
        CheckConstraint("vnd_per_unit > 0", name="rate_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (created_by_member_id)",
            name="fk_fx_rates_created_by",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    currency: Mapped[str] = mapped_column(String(3))
    effective_from: Mapped[dt.date] = mapped_column(Date)
    vnd_per_unit: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    created_by_member_id: Mapped[uuid.UUID | None]
    created_at: Mapped[dt.datetime] = created_at_col()
