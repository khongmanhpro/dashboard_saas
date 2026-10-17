"""Bước 6: tài khoản quảng cáo, nhật ký đồng bộ, nhật ký nhập Excel; lý do Trang không theo dõi.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import enable_tenant_rls, grant_app, revoke_app

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_GRANTS = (
    ("ad_accounts", "SELECT, INSERT, UPDATE"),
    ("sync_runs", "SELECT, INSERT, UPDATE"),
    ("import_jobs", "SELECT, INSERT, UPDATE"),
)


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_ok", sa.Integer(), nullable=False),
        sa.Column("rows_failed", sa.Integer(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_member_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_import_jobs_created_by",
            ondelete="SET NULL (created_by_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_import_jobs_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_import_jobs_workspace_id_id")),
    )
    op.create_index(
        op.f("ix_import_jobs_workspace_id"), "import_jobs", ["workspace_id"], unique=False
    )
    op.create_table(
        "ad_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("business_manager_id", sa.Uuid(), nullable=False),
        sa.Column("fb_ad_account_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("timezone_name", sa.String(length=64), nullable=True),
        sa.Column("account_status", sa.SmallInteger(), nullable=True),
        sa.Column("access_status", sa.String(length=32), server_default="active", nullable=False),
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
        sa.CheckConstraint(
            "access_status IN ('active', 'missing_permissions', 'disconnected')",
            name=op.f("ck_ad_accounts_ad_access_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            name="fk_ad_accounts_business_manager",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_ad_accounts_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_accounts")),
        sa.UniqueConstraint(
            "workspace_id",
            "fb_ad_account_id",
            name=op.f("uq_ad_accounts_workspace_id_fb_ad_account_id"),
        ),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_ad_accounts_workspace_id_id")),
    )
    op.create_index(
        "ix_ad_accounts_business_manager_id", "ad_accounts", ["business_manager_id"], unique=False
    )
    op.create_index(
        op.f("ix_ad_accounts_workspace_id"), "ad_accounts", ["workspace_id"], unique=False
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("business_manager_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            name="fk_sync_runs_business_manager",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_sync_runs_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index(
        "ix_sync_runs_bm_started", "sync_runs", ["business_manager_id", "started_at"], unique=False
    )
    op.create_index("ix_sync_runs_workspace_id", "sync_runs", ["workspace_id"], unique=False)
    op.add_column("pages", sa.Column("untracked_reason", sa.String(length=32), nullable=True))
    for table, privileges in TABLE_GRANTS:
        enable_tenant_rls(table)
        grant_app(table, privileges)


def downgrade() -> None:
    for table, _ in TABLE_GRANTS:
        revoke_app(table)
    op.drop_column("pages", "untracked_reason")
    op.drop_index("ix_sync_runs_workspace_id", table_name="sync_runs")
    op.drop_index("ix_sync_runs_bm_started", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index(op.f("ix_ad_accounts_workspace_id"), table_name="ad_accounts")
    op.drop_index("ix_ad_accounts_business_manager_id", table_name="ad_accounts")
    op.drop_table("ad_accounts")
    op.drop_index(op.f("ix_import_jobs_workspace_id"), table_name="import_jobs")
    op.drop_table("import_jobs")
