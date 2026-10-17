"""Bước 2: BM, Trang, người phụ trách, webhook, khách, đợt khách, tin nhắn, leadgen.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17

- Mọi bảng có `workspace_id` và bật Row-Level Security.
- `page_assignments` có EXCLUDE gist: một Trang không có hai người phụ trách cùng lúc.
- `app_route_page(fb_page_id)` là cách duy nhất để tài khoản ứng dụng (worker) biết Trang thuộc
  workspace nào trước khi đặt `app.workspace_id`. Hàm chỉ trả về `workspace_id`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import app_role, enable_tenant_rls, grant_app, revoke_app

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (bảng, quyền của tài khoản ứng dụng). lead_events chỉ ghi thêm, không sửa.
TABLE_GRANTS = (
    ("business_managers", "SELECT, INSERT, UPDATE"),
    ("pages", "SELECT, INSERT, UPDATE"),
    ("page_assignments", "SELECT, INSERT, UPDATE"),
    ("webhook_events", "SELECT, INSERT, UPDATE"),
    ("contacts", "SELECT, INSERT, UPDATE"),
    ("leads", "SELECT, INSERT, UPDATE"),
    ("messages", "SELECT, INSERT, UPDATE"),
    ("lead_events", "SELECT, INSERT"),
    ("leadgen_submissions", "SELECT, INSERT, UPDATE"),
)


def upgrade() -> None:
    # EXCLUDE với cột uuid cần toán tử = của btree trong gist.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("object", sa.String(length=32), nullable=False),
        sa.Column("fb_page_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('processed', 'ignored', 'failed')",
            name=op.f("ck_webhook_events_webhook_event_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_webhook_events_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint(
            "workspace_id", "dedupe_key", name=op.f("uq_webhook_events_workspace_id_dedupe_key")
        ),
    )
    op.create_index(
        "ix_webhook_events_received_at", "webhook_events", ["received_at"], unique=False
    )
    op.create_table(
        "business_managers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("fb_business_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=True),
        sa.Column("system_user_id", sa.String(length=32), nullable=True),
        sa.Column("token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("token_last4", sa.String(length=4), nullable=True),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "scopes", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("status_detail", sa.String(length=500), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_by_member_id", sa.Uuid(), nullable=True),
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
            "status IN ('active', 'missing_permissions', 'disconnected')",
            name=op.f("ck_business_managers_bm_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connected_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_business_managers_connected_by",
            ondelete="SET NULL (connected_by_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_business_managers_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_managers")),
        sa.UniqueConstraint(
            "workspace_id",
            "fb_business_id",
            name=op.f("uq_business_managers_workspace_id_fb_business_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_business_managers_workspace_id_id")
        ),
    )
    op.create_index(
        op.f("ix_business_managers_workspace_id"),
        "business_managers",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("business_manager_id", sa.Uuid(), nullable=False),
        sa.Column("fb_page_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("page_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column(
            "webhook_fields",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("webhook_subscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_tracked", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "access_status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
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
            name=op.f("ck_pages_page_access_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "business_manager_id"],
            ["business_managers.workspace_id", "business_managers.id"],
            name="fk_pages_business_manager",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_pages_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pages")),
        sa.UniqueConstraint(
            "workspace_id", "fb_page_id", name=op.f("uq_pages_workspace_id_fb_page_id")
        ),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_pages_workspace_id_id")),
    )
    op.create_index(
        op.f("ix_pages_business_manager_id"), "pages", ["business_manager_id"], unique=False
    )
    op.create_index(op.f("ix_pages_workspace_id"), "pages", ["workspace_id"], unique=False)
    op.create_index(
        "uq_pages_tracked_fb_page_id",
        "pages",
        ["fb_page_id"],
        unique=True,
        postgresql_where=sa.text("is_tracked"),
    )
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("psid", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_contacts_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_contacts_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
        sa.UniqueConstraint("page_id", "psid", name=op.f("uq_contacts_page_id_psid")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_contacts_workspace_id_id")),
    )
    op.create_index(op.f("ix_contacts_workspace_id"), "contacts", ["workspace_id"], unique=False)
    op.create_table(
        "page_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_member_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name=op.f("ck_page_assignments_valid_range"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assigned_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_page_assignments_assigned_by",
            ondelete="SET NULL (assigned_by_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_page_assignments_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_page_assignments_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_page_assignments_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_assignments")),
    )
    op.create_index(
        "ix_page_assignments_member_id", "page_assignments", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_page_assignments_workspace_id"), "page_assignments", ["workspace_id"], unique=False
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("episode_no", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("owner_member_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("fb_ad_id", sa.String(length=32), nullable=True),
        sa.Column("referral", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("first_inbound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_inbound_mid", sa.String(length=200), nullable=True),
        sa.Column("first_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_reply_mid", sa.String(length=200), nullable=True),
        sa.Column("response_business_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="new",
            nullable=False,
        ),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("callback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("won_value_vnd", sa.BigInteger(), nullable=True),
        sa.Column(
            "lost_reason",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column("lost_note", sa.String(length=500), nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone", sa.String(length=15), nullable=True),
        sa.Column("phone_source", sa.String(length=32), nullable=True),
        sa.Column("phone_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
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
            "lost_reason IN ('price', 'out_of_area', 'no_answer', 'bought_elsewhere', 'other')",
            name=op.f("ck_leads_lost_reason"),
        ),
        sa.CheckConstraint("source IN ('message', 'leadgen')", name=op.f("ck_leads_lead_source")),
        sa.CheckConstraint(
            "status <> 'callback' OR callback_at IS NOT NULL",
            name=op.f("ck_leads_callback_has_time"),
        ),
        sa.CheckConstraint(
            "status <> 'lost' OR lost_reason IS NOT NULL", name=op.f("ck_leads_lost_has_reason")
        ),
        sa.CheckConstraint(
            "status <> 'won' OR (won_value_vnd IS NOT NULL AND won_value_vnd > 0)",
            name=op.f("ck_leads_won_has_value"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'callback', 'won', 'lost')",
            name=op.f("ck_leads_lead_status"),
        ),
        sa.CheckConstraint("episode_no >= 1", name=op.f("ck_leads_episode_positive")),
        sa.CheckConstraint(
            "response_business_seconds IS NULL OR response_business_seconds >= 0",
            name=op.f("ck_leads_response_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_leads_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "owner_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_leads_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_leads_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_leads_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
        sa.UniqueConstraint(
            "contact_id", "episode_no", name=op.f("uq_leads_contact_id_episode_no")
        ),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_leads_workspace_id_id")),
    )
    op.create_index(
        "ix_leads_page_first_inbound", "leads", ["page_id", "first_inbound_at"], unique=False
    )
    op.create_index(
        "ix_leads_workspace_owner", "leads", ["workspace_id", "owner_member_id"], unique=False
    )
    op.create_table(
        "lead_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("actor_member_id", sa.Uuid(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('created', 'replied', 'phone_detected', 'called', 'status_changed', 'overdue', 'reminder_sent', 'reassigned')",
            name=op.f("ck_lead_events_lead_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_lead_events_actor",
            ondelete="SET NULL (actor_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_lead_events_lead",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_lead_events_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_events")),
    )
    op.create_index(
        "ix_lead_events_lead_occurred", "lead_events", ["lead_id", "occurred_at"], unique=False
    )
    op.create_index("ix_lead_events_workspace_id", "lead_events", ["workspace_id"], unique=False)
    op.create_table(
        "leadgen_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("leadgen_id", sa.String(length=32), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.String(length=32), nullable=True),
        sa.Column("fb_ad_id", sa.String(length=32), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "field_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "fetch_status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fetch_status IN ('fetched', 'pending')",
            name=op.f("ck_leadgen_submissions_leadgen_fetch_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_leadgen_submissions_lead",
            ondelete="SET NULL (lead_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_leadgen_submissions_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_leadgen_submissions_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leadgen_submissions")),
        sa.UniqueConstraint("leadgen_id", name=op.f("uq_leadgen_submissions_leadgen_id")),
    )
    op.create_index(
        op.f("ix_leadgen_submissions_lead_id"), "leadgen_submissions", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_leadgen_submissions_page_id"), "leadgen_submissions", ["page_id"], unique=False
    )
    op.create_index(
        op.f("ix_leadgen_submissions_workspace_id"),
        "leadgen_submissions",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("mid", sa.String(length=200), nullable=False),
        sa.Column(
            "direction",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("is_echo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("app_id", sa.String(length=32), nullable=True),
        sa.Column("is_automated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('in', 'out')", name=op.f("ck_messages_message_direction")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_messages_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_messages_lead",
            ondelete="SET NULL (lead_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            name="fk_messages_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_messages_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("mid", name=op.f("uq_messages_mid")),
    )
    op.create_index("ix_messages_contact_sent", "messages", ["contact_id", "sent_at"], unique=False)
    op.create_index("ix_messages_lead_id", "messages", ["lead_id"], unique=False)
    op.create_index("ix_messages_workspace_id", "messages", ["workspace_id"], unique=False)
    op.execute(
        "ALTER TABLE page_assignments ADD CONSTRAINT ex_page_assignments_no_overlap"
        " EXCLUDE USING gist (page_id WITH =, tstzrange(valid_from, valid_to) WITH &&)"
    )

    for table, privileges in TABLE_GRANTS:
        enable_tenant_rls(table)
        grant_app(table, privileges)

    # Định tuyến webhook: chạy với quyền chủ hàm (bỏ qua RLS) nhưng chỉ trả về workspace_id
    # của Trang đang theo dõi, thuộc workspace đang hoạt động.
    op.execute(
        """
        CREATE FUNCTION app_route_page(p_fb_page_id text) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT p.workspace_id
            FROM public.pages p
            JOIN public.workspaces w ON w.id = p.workspace_id
            WHERE p.fb_page_id = p_fb_page_id AND p.is_tracked AND w.status = 'active'
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_route_page(text) FROM PUBLIC")
    op.execute(f'GRANT EXECUTE ON FUNCTION app_route_page(text) TO "{app_role()}"')


def downgrade() -> None:
    op.execute("DROP FUNCTION app_route_page(text)")
    for table, _ in TABLE_GRANTS:
        revoke_app(table)
    op.drop_index("ix_messages_workspace_id", table_name="messages")
    op.drop_index("ix_messages_lead_id", table_name="messages")
    op.drop_index("ix_messages_contact_sent", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_leadgen_submissions_workspace_id"), table_name="leadgen_submissions")
    op.drop_index(op.f("ix_leadgen_submissions_page_id"), table_name="leadgen_submissions")
    op.drop_index(op.f("ix_leadgen_submissions_lead_id"), table_name="leadgen_submissions")
    op.drop_table("leadgen_submissions")
    op.drop_index("ix_lead_events_workspace_id", table_name="lead_events")
    op.drop_index("ix_lead_events_lead_occurred", table_name="lead_events")
    op.drop_table("lead_events")
    op.drop_index("ix_leads_workspace_owner", table_name="leads")
    op.drop_index("ix_leads_page_first_inbound", table_name="leads")
    op.drop_table("leads")
    op.drop_index(op.f("ix_page_assignments_workspace_id"), table_name="page_assignments")
    op.drop_index("ix_page_assignments_member_id", table_name="page_assignments")
    op.drop_table("page_assignments")
    op.drop_index(op.f("ix_contacts_workspace_id"), table_name="contacts")
    op.drop_table("contacts")
    op.drop_index(
        "uq_pages_tracked_fb_page_id", table_name="pages", postgresql_where=sa.text("is_tracked")
    )
    op.drop_index(op.f("ix_pages_workspace_id"), table_name="pages")
    op.drop_index(op.f("ix_pages_business_manager_id"), table_name="pages")
    op.drop_table("pages")
    op.drop_index(op.f("ix_business_managers_workspace_id"), table_name="business_managers")
    op.drop_table("business_managers")
    op.drop_index("ix_webhook_events_received_at", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
