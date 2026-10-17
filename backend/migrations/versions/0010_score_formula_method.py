"""Phiên bản công thức ghi cách chấm (decisions.md mục L).

Các phiên bản đang có được đánh dấu `percentile` (xếp phần trăm, trước mục K). Mỗi workspace thêm
một phiên bản mới `threshold` (ngưỡng tuyệt đối) chép trọng số, ngưỡng của phiên bản mới nhất, áp
dụng từ lúc chạy migration. Tuần đã chốt giữ nguyên điểm; giao diện ghi "khác công thức".

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "score_formulas",
        sa.Column(
            "score_method",
            sa.String(length=16),
            server_default=sa.text("'threshold'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_score_formulas_score_method_valid"),
        "score_formulas",
        "score_method IN ('percentile', 'threshold')",
    )
    op.execute("UPDATE score_formulas SET score_method = 'percentile'")
    op.execute(
        """
        INSERT INTO score_formulas (
            id, workspace_id, version,
            w_close_rate, w_response_speed, w_revenue, w_phone_rate, w_page_care, w_on_time,
            speed_full_minutes, speed_zero_minutes, tier_a, tier_b, tier_c, min_leads,
            posts_per_week_target, close_rate_zero, close_rate_full, revenue_full_vnd,
            phone_rate_zero, phone_rate_full, on_time_zero, on_time_full,
            score_method, effective_from, created_by_member_id
        )
        SELECT
            gen_random_uuid(), f.workspace_id, f.version + 1,
            f.w_close_rate, f.w_response_speed, f.w_revenue, f.w_phone_rate, f.w_page_care,
            f.w_on_time, f.speed_full_minutes, f.speed_zero_minutes, f.tier_a, f.tier_b,
            f.tier_c, f.min_leads, f.posts_per_week_target, f.close_rate_zero,
            f.close_rate_full, f.revenue_full_vnd, f.phone_rate_zero, f.phone_rate_full,
            f.on_time_zero, f.on_time_full,
            'threshold', now(), NULL
        FROM score_formulas f
        WHERE f.version = (
            SELECT max(x.version) FROM score_formulas x WHERE x.workspace_id = f.workspace_id
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM score_formulas f
        WHERE f.score_method = 'threshold'
          AND f.created_by_member_id IS NULL
          AND f.version = (
              SELECT max(x.version) FROM score_formulas x WHERE x.workspace_id = f.workspace_id
          )
          AND NOT EXISTS (SELECT 1 FROM score_snapshots s WHERE s.formula_id = f.id)
        """
    )
    op.drop_constraint(
        op.f("ck_score_formulas_score_method_valid"), "score_formulas", type_="check"
    )
    op.drop_column("score_formulas", "score_method")
