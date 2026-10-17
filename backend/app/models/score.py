"""Công thức điểm (có phiên bản) và điểm đã tính của từng người theo kỳ."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, str_enum, uuid_pk, workspace_fk
from app.models.enums import PeriodType, Tier

DEFAULT_WEIGHTS = {
    "w_close_rate": 30,
    "w_response_speed": 25,
    "w_revenue": 20,
    "w_phone_rate": 10,
    "w_page_care": 10,
    "w_on_time": 5,
}


class ScoreFormula(Base):
    """Một phiên bản công thức. Không sửa: đổi công thức là thêm phiên bản mới."""

    __tablename__ = "score_formulas"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "version"),
        CheckConstraint(
            "w_close_rate + w_response_speed + w_revenue + w_phone_rate + w_page_care"
            " + w_on_time = 100",
            name="weights_sum_100",
        ),
        CheckConstraint(
            "LEAST(w_close_rate, w_response_speed, w_revenue, w_phone_rate, w_page_care,"
            " w_on_time) >= 0",
            name="weights_non_negative",
        ),
        CheckConstraint(
            "speed_full_minutes >= 0 AND speed_zero_minutes > speed_full_minutes",
            name="speed_range",
        ),
        CheckConstraint(
            "tier_a > tier_b AND tier_b > tier_c AND tier_c > 0 AND tier_a <= 100",
            name="tier_order",
        ),
        CheckConstraint("min_leads >= 0 AND posts_per_week_target >= 0", name="positive_limits"),
        ForeignKeyConstraint(
            ["workspace_id", "created_by_member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="SET NULL (created_by_member_id)",
            name="fk_score_formulas_created_by",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    version: Mapped[int] = mapped_column(Integer)
    w_close_rate: Mapped[int] = mapped_column(SmallInteger, server_default=text("30"))
    w_response_speed: Mapped[int] = mapped_column(SmallInteger, server_default=text("25"))
    w_revenue: Mapped[int] = mapped_column(SmallInteger, server_default=text("20"))
    w_phone_rate: Mapped[int] = mapped_column(SmallInteger, server_default=text("10"))
    w_page_care: Mapped[int] = mapped_column(SmallInteger, server_default=text("10"))
    w_on_time: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    speed_full_minutes: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    speed_zero_minutes: Mapped[int] = mapped_column(SmallInteger, server_default=text("120"))
    tier_a: Mapped[int] = mapped_column(SmallInteger, server_default=text("85"))
    tier_b: Mapped[int] = mapped_column(SmallInteger, server_default=text("70"))
    tier_c: Mapped[int] = mapped_column(SmallInteger, server_default=text("50"))
    min_leads: Mapped[int] = mapped_column(SmallInteger, server_default=text("10"))
    posts_per_week_target: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    effective_from: Mapped[dt.datetime]
    created_by_member_id: Mapped[uuid.UUID | None]
    created_at: Mapped[dt.datetime] = created_at_col()


class ScoreSnapshot(Base):
    """Điểm của một người trong một kỳ. Dòng `is_final` không bao giờ bị ghi đè."""

    __tablename__ = "score_snapshots"
    __table_args__ = (
        UniqueConstraint("workspace_id", "member_id", "period_type", "period_start"),
        ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="CASCADE",
            name="fk_score_snapshots_member",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "formula_id"],
            ["score_formulas.workspace_id", "score_formulas.id"],
            ondelete="RESTRICT",
            name="fk_score_snapshots_formula",
        ),
        Index("ix_score_snapshots_period", "workspace_id", "period_type", "period_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Không index riêng: uq và ix_score_snapshots_period đều bắt đầu bằng workspace_id.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    member_id: Mapped[uuid.UUID]
    formula_id: Mapped[uuid.UUID]
    period_type: Mapped[PeriodType] = mapped_column(str_enum(PeriodType, "period_type"))
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)  # ngày cuối kỳ, tính cả ngày này
    computed_at: Mapped[dt.datetime]
    # Chỉ số thô
    lead_count: Mapped[int] = mapped_column(Integer)
    won_count: Mapped[int] = mapped_column(Integer)
    phone_count: Mapped[int] = mapped_column(Integer)
    close_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    median_response_seconds: Mapped[int | None] = mapped_column(Integer)
    revenue_vnd: Mapped[int] = mapped_column(BigInteger)
    phone_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    posts_count: Mapped[int | None] = mapped_column(Integer)
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # Điểm thành phần 0–100 (NULL: chưa đủ dữ liệu hoặc chưa có số liệu, ví dụ Chăm Trang)
    s_close_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    s_response_speed: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    s_revenue: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    s_phone_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    s_page_care: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    s_on_time: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tier: Mapped[Tier | None] = mapped_column(str_enum(Tier, "tier"))
    insufficient_data: Mapped[bool] = mapped_column(Boolean)
    rank: Mapped[int | None] = mapped_column(Integer)
    is_final: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
