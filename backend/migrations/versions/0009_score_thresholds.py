"""Ngưỡng tuyệt đối cho tỉ lệ chốt, doanh thu, % có SĐT, cập nhật đúng hạn (decisions.md mục K).

Phiên bản công thức đang có nhận ngưỡng mặc định; tuần đã chốt giữ nguyên điểm cũ.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("close_rate_zero", sa.SmallInteger(), "5"),
    ("close_rate_full", sa.SmallInteger(), "30"),
    ("revenue_full_vnd", sa.BigInteger(), "20000000"),
    ("phone_rate_zero", sa.SmallInteger(), "30"),
    ("phone_rate_full", sa.SmallInteger(), "80"),
    ("on_time_zero", sa.SmallInteger(), "50"),
    ("on_time_full", sa.SmallInteger(), "95"),
)


def upgrade() -> None:
    for name, type_, default in COLUMNS:
        op.add_column(
            "score_formulas",
            sa.Column(name, type_, server_default=sa.text(default), nullable=False),
        )
    op.create_check_constraint(
        op.f("ck_score_formulas_threshold_range"),
        "score_formulas",
        "close_rate_zero >= 0 AND close_rate_full > close_rate_zero AND close_rate_full <= 100"
        " AND phone_rate_zero >= 0 AND phone_rate_full > phone_rate_zero"
        " AND phone_rate_full <= 100"
        " AND on_time_zero >= 0 AND on_time_full > on_time_zero AND on_time_full <= 100"
        " AND revenue_full_vnd > 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_score_formulas_threshold_range"), "score_formulas", type_="check")
    for name, _, _ in reversed(COLUMNS):
        op.drop_column("score_formulas", name)
