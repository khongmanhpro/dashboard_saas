"""Bảng lõi: workspace, người dùng, thành viên, nhóm, cài đặt, phiên đăng nhập, audit.

Revision ID: 0001
Revises:
Create Date: 2026-10-17

Có Row-Level Security cho mọi bảng thuộc workspace. Tài khoản ứng dụng chỉ nhận
đúng các quyền cần; `audit_logs` chỉ INSERT/SELECT.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import app_role, enable_tenant_rls, grant_app, revoke_app

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def _ts(name: str, nullable: bool = False, default: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=_NOW if default else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # Ngữ cảnh tenant đặt bằng set_config(..., true) ở đầu mỗi transaction (app/core/db.py).
    op.execute(
        """
        CREATE FUNCTION app_current_workspace() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT NULLIF(current_setting('app.workspace_id', true), '')::uuid $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_current_user() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$
        """
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("last_login_at", nullable=True),
        _ts("password_changed_at", nullable=True),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "timezone", sa.String(length=64), server_default="Asia/Ho_Chi_Minh", nullable=False
        ),
        sa.Column("plan_code", sa.String(length=32), server_default="internal", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')", name="ck_workspaces_workspace_status"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'team_lead', 'staff', 'viewer')",
            name="ck_workspace_members_member_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_workspace_members_member_status"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_workspace_members_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_members_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_members"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_workspace_members_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_id_user_id"
        ),
    )
    op.create_index("ix_workspace_members_team_id", "workspace_members", ["team_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("lead_member_id", sa.Uuid(), nullable=True),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_teams_lead_member",
            ondelete="SET NULL (lead_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_teams_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_teams_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_teams_workspace_id_name"),
    )
    op.create_index("ix_teams_lead_member_id", "teams", ["lead_member_id"])
    op.create_index("ix_teams_workspace_id", "teams", ["workspace_id"])

    # Khóa ngoại vòng members → teams: tạo sau khi đủ cả hai bảng.
    op.create_foreign_key(
        "fk_workspace_members_team",
        "workspace_members",
        "teams",
        ["workspace_id", "team_id"],
        ["workspace_id", "id"],
        ondelete="SET NULL (team_id)",
    )

    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("work_start", sa.Time(), server_default=sa.text("'08:00'"), nullable=False),
        sa.Column("work_end", sa.Time(), server_default=sa.text("'22:00'"), nullable=False),
        sa.Column("slow_reply_minutes", sa.SmallInteger(), server_default="30", nullable=False),
        sa.Column("result_deadline_hours", sa.SmallInteger(), server_default="48", nullable=False),
        sa.Column("lead_session_gap_days", sa.SmallInteger(), server_default="30", nullable=False),
        sa.Column("posts_per_week_target", sa.SmallInteger(), server_default="5", nullable=False),
        sa.Column("min_leads_for_ranking", sa.SmallInteger(), server_default="10", nullable=False),
        sa.Column(
            "one_page_per_member", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "staff_can_see_leaderboard",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        _ts("updated_at", default=True),
        sa.CheckConstraint(
            "slow_reply_minutes > 0 AND result_deadline_hours > 0 AND lead_session_gap_days > 0"
            " AND posts_per_week_target >= 0 AND min_leads_for_ranking >= 0",
            name="ck_workspace_settings_positive_values",
        ),
        sa.CheckConstraint("work_start < work_end", name="ck_workspace_settings_work_hours_order"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_settings_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspace_settings"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("token_hmac", sa.LargeBinary(length=32), nullable=False),
        sa.Column("csrf_hmac", sa.LargeBinary(length=32), nullable=False),
        _ts("created_at", default=True),
        _ts("last_seen_at"),
        _ts("expires_at"),
        _ts("idle_expires_at"),
        _ts("revoked_at", nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_auth_sessions_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_auth_sessions_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hmac", name="uq_auth_sessions_token_hmac"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_workspace_id", "auth_sessions", ["workspace_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_member_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        _ts("created_at", default=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_audit_logs_actor",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_audit_logs_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_workspace_created", "audit_logs", ["workspace_id", "created_at"])

    # ---------------- Row-Level Security ----------------
    for table in ("workspace_members", "teams", "workspace_settings", "audit_logs"):
        enable_tenant_rls(table)

    # Người dùng thấy các membership của chính mình ở mọi workspace (để đăng nhập, chọn workspace).
    op.execute(
        "CREATE POLICY member_self_read ON workspace_members FOR SELECT"
        " USING (user_id = app_current_user())"
    )

    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspace_read ON workspaces FOR SELECT USING (
            id = app_current_workspace()
            OR EXISTS (
                SELECT 1 FROM workspace_members m
                WHERE m.workspace_id = workspaces.id AND m.user_id = app_current_user()
            )
        )
        """
    )
    op.execute(
        "CREATE POLICY workspace_update ON workspaces FOR UPDATE"
        " USING (id = app_current_workspace()) WITH CHECK (id = app_current_workspace())"
    )

    # ---------------- Quyền của tài khoản ứng dụng ----------------
    # Tạo workspace là việc quản trị (CLI), ứng dụng chỉ đọc và sửa workspace của mình.
    grant_app("workspaces", "SELECT, UPDATE")
    grant_app("users", "SELECT, INSERT, UPDATE")
    grant_app("workspace_members")
    grant_app("teams")
    grant_app("workspace_settings", "SELECT, INSERT, UPDATE")
    grant_app("auth_sessions")
    # Nhật ký không được sửa hay xóa từ ứng dụng.
    grant_app("audit_logs", "SELECT, INSERT")
    op.execute(f'REVOKE ALL ON alembic_version FROM "{app_role()}"')


def downgrade() -> None:
    # Policy của workspaces tham chiếu workspace_members: phải xóa trước khi xóa bảng.
    op.execute("DROP POLICY workspace_read ON workspaces")
    for table in (
        "audit_logs",
        "auth_sessions",
        "workspace_settings",
        "teams",
        "workspace_members",
        "workspaces",
        "users",
    ):
        revoke_app(table)
    op.drop_constraint("fk_workspace_members_team", "workspace_members", type_="foreignkey")
    op.drop_table("audit_logs")
    op.drop_table("auth_sessions")
    op.drop_table("workspace_settings")
    op.drop_table("teams")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.execute("DROP FUNCTION app_current_user()")
    op.execute("DROP FUNCTION app_current_workspace()")
