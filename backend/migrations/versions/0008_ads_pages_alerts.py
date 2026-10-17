"""Bước 7: chiến dịch / nhóm / quảng cáo, số liệu QC theo ngày, tỉ giá theo workspace, bài đăng
và số liệu Trang, quy tắc và nhật ký cảnh báo Telegram; gắn khách với quảng cáo.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import enable_tenant_rls, grant_app, revoke_app

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_GRANTS = (
    ("campaigns", "SELECT, INSERT, UPDATE"),
    ("ad_sets", "SELECT, INSERT, UPDATE"),
    ("ads", "SELECT, INSERT, UPDATE"),
    ("ad_insights_daily", "SELECT, INSERT, UPDATE"),
    ("fx_rates", "SELECT, INSERT, UPDATE, DELETE"),
    ("page_posts", "SELECT, INSERT, UPDATE"),
    ("page_insights_daily", "SELECT, INSERT, UPDATE"),
    ("alert_rules", "SELECT, INSERT, UPDATE"),
    ("alert_deliveries", "SELECT, INSERT, UPDATE"),
)


def upgrade() -> None:
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('sent', 'failed', 'mock')", name=op.f("ck_alert_deliveries_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_alert_deliveries_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_deliveries")),
        sa.UniqueConstraint(
            "workspace_id", "dedupe_key", name=op.f("uq_alert_deliveries_workspace_id_dedupe_key")
        ),
    )
    op.create_index(
        op.f("ix_alert_deliveries_workspace_id"), "alert_deliveries", ["workspace_id"], unique=False
    )
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_alert_rules_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
        sa.UniqueConstraint("workspace_id", "type", name=op.f("uq_alert_rules_workspace_id_type")),
    )
    op.create_index(
        op.f("ix_alert_rules_workspace_id"), "alert_rules", ["workspace_id"], unique=False
    )
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("vnd_per_unit", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("created_by_member_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_rates_currency_code")),
        sa.CheckConstraint("vnd_per_unit > 0", name=op.f("ck_fx_rates_rate_positive")),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_fx_rates_created_by",
            ondelete="SET NULL (created_by_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_fx_rates_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_rates")),
        sa.UniqueConstraint(
            "workspace_id",
            "currency",
            "effective_from",
            name=op.f("uq_fx_rates_workspace_id_currency_effective_from"),
        ),
    )
    op.create_index(op.f("ix_fx_rates_workspace_id"), "fx_rates", ["workspace_id"], unique=False)
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("fb_campaign_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("objective", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("daily_budget_minor", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "ad_account_id"],
            ["ad_accounts.workspace_id", "ad_accounts.id"],
            name="fk_campaigns_ad_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_campaigns_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
        sa.UniqueConstraint(
            "workspace_id", "fb_campaign_id", name=op.f("uq_campaigns_workspace_id_fb_campaign_id")
        ),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_campaigns_workspace_id_id")),
    )
    op.create_index("ix_campaigns_ad_account_id", "campaigns", ["ad_account_id"], unique=False)
    op.create_index(op.f("ix_campaigns_workspace_id"), "campaigns", ["workspace_id"], unique=False)
    op.create_table(
        "page_insights_daily",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("followers", sa.Integer(), nullable=True),
        sa.Column("new_follows", sa.Integer(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("engagements", sa.Integer(), nullable=True),
        sa.Column("video_views", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_page_insights_daily_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_page_insights_daily_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_insights_daily")),
        sa.UniqueConstraint(
            "workspace_id",
            "page_id",
            "date",
            name=op.f("uq_page_insights_daily_workspace_id_page_id_date"),
        ),
    )
    op.create_index(
        "ix_page_insights_daily_page_date", "page_insights_daily", ["page_id", "date"], unique=False
    )
    op.create_table(
        "page_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("fb_post_id", sa.String(length=80), nullable=False),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("excerpt", sa.String(length=200), nullable=True),
        sa.Column("permalink", sa.String(length=500), nullable=True),
        sa.Column("reactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("comments", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shares", sa.Integer(), server_default="0", nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_page_posts_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_page_posts_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_posts")),
        sa.UniqueConstraint(
            "workspace_id", "fb_post_id", name=op.f("uq_page_posts_workspace_id_fb_post_id")
        ),
    )
    op.create_index(
        "ix_page_posts_page_created", "page_posts", ["page_id", "created_time"], unique=False
    )
    op.create_index(
        op.f("ix_page_posts_workspace_id"), "page_posts", ["workspace_id"], unique=False
    )
    op.create_table(
        "ad_insights_daily",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("spend_minor", sa.BigInteger(), nullable=False),
        sa.Column("spend_vnd", sa.BigInteger(), nullable=True),
        sa.Column("impressions", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("reach", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("clicks", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("messaging_starts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("leads", sa.Integer(), server_default="0", nullable=False),
        sa.Column("results", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IN ('campaign', 'adset', 'ad')", name=op.f("ck_ad_insights_daily_level_valid")
        ),
        sa.CheckConstraint(
            "spend_minor >= 0", name=op.f("ck_ad_insights_daily_spend_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "ad_account_id"],
            ["ad_accounts.workspace_id", "ad_accounts.id"],
            name="fk_ad_insights_daily_ad_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_ad_insights_daily_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_ad_insights_daily_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_insights_daily")),
        sa.UniqueConstraint(
            "workspace_id",
            "level",
            "object_id",
            "date",
            name=op.f("uq_ad_insights_daily_workspace_id_level_object_id_date"),
        ),
    )
    op.create_index(
        "ix_ad_insights_daily_campaign_date",
        "ad_insights_daily",
        ["campaign_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_ad_insights_daily_ws_level_date",
        "ad_insights_daily",
        ["workspace_id", "level", "date"],
        unique=False,
    )
    op.create_table(
        "ad_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("fb_ad_set_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("daily_budget_minor", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_ad_sets_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_ad_sets_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_sets")),
        sa.UniqueConstraint(
            "workspace_id", "fb_ad_set_id", name=op.f("uq_ad_sets_workspace_id_fb_ad_set_id")
        ),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_ad_sets_workspace_id_id")),
    )
    op.create_index("ix_ad_sets_campaign_id", "ad_sets", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_ad_sets_workspace_id"), "ad_sets", ["workspace_id"], unique=False)
    op.create_table(
        "ads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("ad_set_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=True),
        sa.Column("fb_ad_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "ad_set_id"],
            ["ad_sets.workspace_id", "ad_sets.id"],
            name="fk_ads_ad_set",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_ads_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_ads_page",
            ondelete="SET NULL (page_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_ads_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ads")),
        sa.UniqueConstraint("workspace_id", "fb_ad_id", name=op.f("uq_ads_workspace_id_fb_ad_id")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_ads_workspace_id_id")),
    )
    op.create_index("ix_ads_ad_set_id", "ads", ["ad_set_id"], unique=False)
    op.create_index("ix_ads_campaign_id", "ads", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_ads_workspace_id"), "ads", ["workspace_id"], unique=False)
    op.add_column("leads", sa.Column("ad_id", sa.Uuid(), nullable=True))
    op.add_column("leads", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_leads_campaign_first_inbound",
        "leads",
        ["campaign_id", "first_inbound_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_leads_ad",
        "leads",
        "ads",
        ["workspace_id", "ad_id"],
        ["workspace_id", "id"],
        ondelete="SET NULL (ad_id)",
    )
    op.create_foreign_key(
        "fk_leads_campaign",
        "leads",
        "campaigns",
        ["workspace_id", "campaign_id"],
        ["workspace_id", "id"],
        ondelete="SET NULL (campaign_id)",
    )
    op.add_column(
        "workspace_settings", sa.Column("telegram_chat_id", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "pages", sa.Column("content_synced_at", sa.DateTime(timezone=True), nullable=True)
    )
    for table, privileges in TABLE_GRANTS:
        enable_tenant_rls(table)
        grant_app(table, privileges)


def downgrade() -> None:
    for table, _ in TABLE_GRANTS:
        revoke_app(table)
    op.drop_column("pages", "content_synced_at")
    op.drop_column("workspace_settings", "telegram_chat_id")
    op.drop_constraint("fk_leads_campaign", "leads", type_="foreignkey")
    op.drop_constraint("fk_leads_ad", "leads", type_="foreignkey")
    op.drop_index("ix_leads_campaign_first_inbound", table_name="leads")
    op.drop_column("leads", "campaign_id")
    op.drop_column("leads", "ad_id")
    op.drop_index(op.f("ix_ads_workspace_id"), table_name="ads")
    op.drop_index("ix_ads_campaign_id", table_name="ads")
    op.drop_index("ix_ads_ad_set_id", table_name="ads")
    op.drop_table("ads")
    op.drop_index(op.f("ix_ad_sets_workspace_id"), table_name="ad_sets")
    op.drop_index("ix_ad_sets_campaign_id", table_name="ad_sets")
    op.drop_table("ad_sets")
    op.drop_index("ix_ad_insights_daily_ws_level_date", table_name="ad_insights_daily")
    op.drop_index("ix_ad_insights_daily_campaign_date", table_name="ad_insights_daily")
    op.drop_table("ad_insights_daily")
    op.drop_index(op.f("ix_page_posts_workspace_id"), table_name="page_posts")
    op.drop_index("ix_page_posts_page_created", table_name="page_posts")
    op.drop_table("page_posts")
    op.drop_index("ix_page_insights_daily_page_date", table_name="page_insights_daily")
    op.drop_table("page_insights_daily")
    op.drop_index(op.f("ix_campaigns_workspace_id"), table_name="campaigns")
    op.drop_index("ix_campaigns_ad_account_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index(op.f("ix_fx_rates_workspace_id"), table_name="fx_rates")
    op.drop_table("fx_rates")
    op.drop_index(op.f("ix_alert_rules_workspace_id"), table_name="alert_rules")
    op.drop_table("alert_rules")
    op.drop_index(op.f("ix_alert_deliveries_workspace_id"), table_name="alert_deliveries")
    op.drop_table("alert_deliveries")
