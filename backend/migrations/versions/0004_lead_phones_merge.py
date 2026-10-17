"""Bước 3: SĐT của khách, tên hiển thị, gộp khách form với khách nhắn tin.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17

- `lead_phones`: mọi SĐT nhận được của một đợt (bật RLS).
- `contacts.display_name`: tên hiển thị (từ form leadgen, sau này từ Graph API).
- `leads.merged_into_lead_id`: đợt form đã gộp vào đợt nhắn tin cùng SĐT (quyết định #16).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant_app, revoke_app

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EVENT_TYPES = (
    "created",
    "replied",
    "phone_detected",
    "called",
    "status_changed",
    "overdue",
    "reminder_sent",
    "reassigned",
)


def _replace_event_types(values: tuple[str, ...]) -> None:
    # SQL thuần: op.drop_constraint/op.create_check_constraint áp lại naming convention.
    allowed = ", ".join(f"'{v}'" for v in values)
    op.execute("ALTER TABLE lead_events DROP CONSTRAINT ck_lead_events_lead_event_type")
    op.execute(
        "ALTER TABLE lead_events ADD CONSTRAINT ck_lead_events_lead_event_type"
        f" CHECK (type IN ({allowed}))"
    )


def upgrade() -> None:
    op.create_table(
        "lead_phones",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_lead_phones_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_lead_phones_lead",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_lead_phones_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_phones")),
        sa.UniqueConstraint("lead_id", "phone", name=op.f("uq_lead_phones_lead_id_phone")),
    )
    op.create_index(
        "ix_lead_phones_workspace_phone", "lead_phones", ["workspace_id", "phone"], unique=False
    )
    op.add_column("contacts", sa.Column("display_name", sa.String(length=200), nullable=True))
    op.add_column("leads", sa.Column("merged_into_lead_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_leads_workspace_first_inbound",
        "leads",
        ["workspace_id", "first_inbound_at"],
        unique=False,
    )
    op.create_index("ix_leads_workspace_phone", "leads", ["workspace_id", "phone"], unique=False)
    op.create_foreign_key(
        "fk_leads_merged_into",
        "leads",
        "leads",
        ["workspace_id", "merged_into_lead_id"],
        ["workspace_id", "id"],
        ondelete="SET NULL (merged_into_lead_id)",
    )

    _replace_event_types((*EVENT_TYPES, "merged"))
    enable_tenant_rls("lead_phones")
    grant_app("lead_phones", "SELECT, INSERT, UPDATE")


def downgrade() -> None:
    revoke_app("lead_phones")
    op.execute("DELETE FROM lead_events WHERE type = 'merged'")
    _replace_event_types(EVENT_TYPES)
    op.drop_constraint("fk_leads_merged_into", "leads", type_="foreignkey")
    op.drop_index("ix_leads_workspace_phone", table_name="leads")
    op.drop_index("ix_leads_workspace_first_inbound", table_name="leads")
    op.drop_column("leads", "merged_into_lead_id")
    op.drop_column("contacts", "display_name")
    op.drop_index("ix_lead_phones_workspace_phone", table_name="lead_phones")
    op.drop_table("lead_phones")
