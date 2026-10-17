"""Bước 4: công thức điểm (có phiên bản) và điểm theo kỳ.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17

- `score_formulas`: mỗi lần đổi công thức thêm một phiên bản; tài khoản ứng dụng chỉ INSERT/SELECT.
- `score_snapshots`: điểm từng người theo kỳ; không cho xóa, dòng `is_final` do service giữ nguyên.
- Mỗi workspace đang có được tạo sẵn công thức mặc định (phiên bản 1).
- `app_active_workspace_ids()`: job ban đêm (tài khoản ứng dụng) lấy danh sách workspace đang hoạt
  động để tính điểm. Hàm chỉ trả về id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import app_role, enable_tenant_rls, grant_app, revoke_app

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "score_formulas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("w_close_rate", sa.SmallInteger(), server_default=sa.text("30"), nullable=False),
        sa.Column(
            "w_response_speed", sa.SmallInteger(), server_default=sa.text("25"), nullable=False
        ),
        sa.Column("w_revenue", sa.SmallInteger(), server_default=sa.text("20"), nullable=False),
        sa.Column("w_phone_rate", sa.SmallInteger(), server_default=sa.text("10"), nullable=False),
        sa.Column("w_page_care", sa.SmallInteger(), server_default=sa.text("10"), nullable=False),
        sa.Column("w_on_time", sa.SmallInteger(), server_default=sa.text("5"), nullable=False),
        sa.Column(
            "speed_full_minutes", sa.SmallInteger(), server_default=sa.text("5"), nullable=False
        ),
        sa.Column(
            "speed_zero_minutes", sa.SmallInteger(), server_default=sa.text("120"), nullable=False
        ),
        sa.Column("tier_a", sa.SmallInteger(), server_default=sa.text("85"), nullable=False),
        sa.Column("tier_b", sa.SmallInteger(), server_default=sa.text("70"), nullable=False),
        sa.Column("tier_c", sa.SmallInteger(), server_default=sa.text("50"), nullable=False),
        sa.Column("min_leads", sa.SmallInteger(), server_default=sa.text("10"), nullable=False),
        sa.Column(
            "posts_per_week_target", sa.SmallInteger(), server_default=sa.text("5"), nullable=False
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_member_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "LEAST(w_close_rate, w_response_speed, w_revenue, w_phone_rate, w_page_care, w_on_time) >= 0",
            name=op.f("ck_score_formulas_weights_non_negative"),
        ),
        sa.CheckConstraint(
            "min_leads >= 0 AND posts_per_week_target >= 0",
            name=op.f("ck_score_formulas_positive_limits"),
        ),
        sa.CheckConstraint(
            "speed_full_minutes >= 0 AND speed_zero_minutes > speed_full_minutes",
            name=op.f("ck_score_formulas_speed_range"),
        ),
        sa.CheckConstraint(
            "tier_a > tier_b AND tier_b > tier_c AND tier_c > 0 AND tier_a <= 100",
            name=op.f("ck_score_formulas_tier_order"),
        ),
        sa.CheckConstraint(
            "w_close_rate + w_response_speed + w_revenue + w_phone_rate + w_page_care + w_on_time = 100",
            name=op.f("ck_score_formulas_weights_sum_100"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_score_formulas_created_by",
            ondelete="SET NULL (created_by_member_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_score_formulas_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_formulas")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_score_formulas_workspace_id_id")),
        sa.UniqueConstraint(
            "workspace_id", "version", name=op.f("uq_score_formulas_workspace_id_version")
        ),
    )
    op.create_index(
        op.f("ix_score_formulas_workspace_id"), "score_formulas", ["workspace_id"], unique=False
    )
    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("formula_id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_count", sa.Integer(), nullable=False),
        sa.Column("won_count", sa.Integer(), nullable=False),
        sa.Column("phone_count", sa.Integer(), nullable=False),
        sa.Column("close_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("median_response_seconds", sa.Integer(), nullable=True),
        sa.Column("revenue_vnd", sa.BigInteger(), nullable=False),
        sa.Column("phone_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("posts_count", sa.Integer(), nullable=True),
        sa.Column("on_time_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("s_close_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("s_response_speed", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("s_revenue", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("s_phone_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("s_page_care", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("s_on_time", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=True),
        sa.Column("insufficient_data", sa.Boolean(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("is_final", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "period_type IN ('week', 'rolling_7', 'rolling_30', 'month')",
            name=op.f("ck_score_snapshots_period_type"),
        ),
        sa.CheckConstraint("tier IN ('A', 'B', 'C', 'D')", name=op.f("ck_score_snapshots_tier")),
        sa.ForeignKeyConstraint(
            ["workspace_id", "formula_id"],
            ["score_formulas.workspace_id", "score_formulas.id"],
            name="fk_score_snapshots_formula",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            name="fk_score_snapshots_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_score_snapshots_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_snapshots")),
        sa.UniqueConstraint(
            "workspace_id",
            "member_id",
            "period_type",
            "period_start",
            name=op.f("uq_score_snapshots_workspace_id_member_id_period_type_period_start"),
        ),
    )
    op.create_index(
        "ix_score_snapshots_period",
        "score_snapshots",
        ["workspace_id", "period_type", "period_start"],
        unique=False,
    )
    enable_tenant_rls("score_formulas")
    grant_app("score_formulas", "SELECT, INSERT")
    enable_tenant_rls("score_snapshots")
    grant_app("score_snapshots", "SELECT, INSERT, UPDATE")

    op.execute(
        "INSERT INTO score_formulas (id, workspace_id, version, effective_from)"
        " SELECT gen_random_uuid(), id, 1, created_at FROM workspaces"
    )

    op.execute(
        """
        CREATE FUNCTION app_active_workspace_ids() RETURNS SETOF uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$ SELECT w.id FROM public.workspaces w WHERE w.status = 'active' ORDER BY w.id $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_active_workspace_ids() FROM PUBLIC")
    op.execute(f'GRANT EXECUTE ON FUNCTION app_active_workspace_ids() TO "{app_role()}"')


def downgrade() -> None:
    op.execute("DROP FUNCTION app_active_workspace_ids()")
    revoke_app("score_snapshots")
    revoke_app("score_formulas")
    op.drop_index("ix_score_snapshots_period", table_name="score_snapshots")
    op.drop_table("score_snapshots")
    op.drop_index(op.f("ix_score_formulas_workspace_id"), table_name="score_formulas")
    op.drop_table("score_formulas")
