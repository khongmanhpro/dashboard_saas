"""Bước 5: nhắc việc và đăng ký thông báo đẩy.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17

- `notifications`: mỗi mốc nhắc một lần nhờ unique (workspace_id, dedupe_key).
- `push_subscriptions`: trình duyệt/điện thoại đã cho phép nhận thông báo đẩy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant_app, revoke_app

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_push_subscriptions_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_push_subscriptions_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint(
            "workspace_id", "endpoint", name=op.f("uq_push_subscriptions_workspace_id_endpoint")
        ),
    )
    op.create_index(
        "ix_push_subscriptions_member_id", "push_subscriptions", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_push_subscriptions_workspace_id"),
        "push_subscriptions",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("actor_member_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_via", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "type IN ('wait_15', 'wait_30', 'phone_not_called', 'due_soon', 'overdue', 'callback_soon', 'callback_missed', 'manual')",
            name=op.f("ck_notifications_notification_type"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_notifications_actor",
            ondelete="SET NULL (actor_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_notifications_lead",
            ondelete="SET NULL (lead_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_notifications_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_notifications_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "workspace_id", "dedupe_key", name=op.f("uq_notifications_workspace_id_dedupe_key")
        ),
    )
    op.create_index(op.f("ix_notifications_lead_id"), "notifications", ["lead_id"], unique=False)
    op.create_index(
        "ix_notifications_member_created",
        "notifications",
        ["member_id", "created_at"],
        unique=False,
    )
    enable_tenant_rls("notifications")
    grant_app("notifications", "SELECT, INSERT, UPDATE")
    enable_tenant_rls("push_subscriptions")
    grant_app("push_subscriptions")


def downgrade() -> None:
    revoke_app("push_subscriptions")
    revoke_app("notifications")
    op.drop_index("ix_notifications_member_created", table_name="notifications")
    op.drop_index(op.f("ix_notifications_lead_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_push_subscriptions_workspace_id"), table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_member_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
