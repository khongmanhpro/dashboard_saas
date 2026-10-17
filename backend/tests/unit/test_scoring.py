"""Hàm tính điểm thuần: tốc độ, xếp phần trăm, chia lại trọng số, hạng, kỳ."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.models import LeadSource, LeadStatus, PeriodType, Tier
from app.services.periods import period_for, previous_week, week_of
from app.services.scoring import (
    FormulaParams,
    LeadFacts,
    MemberMetrics,
    compute_scores,
    linear_score,
    member_metrics,
    page_care_score,
    revenue_target,
    speed_score,
    tier_of,
    weighted_total,
)

DEFAULT = FormulaParams(
    weights={
        "close_rate": 30,
        "response_speed": 25,
        "revenue": 20,
        "phone_rate": 10,
        "page_care": 10,
        "on_time": 5,
    }
)
NOW = dt.datetime(2026, 10, 17, 12, 0, tzinfo=dt.UTC)
VN = ZoneInfo("Asia/Ho_Chi_Minh")


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (0, "100"),
        (5, "100"),
        (62.5, "50.00"),
        (120, "0"),
        (300, "0"),
        (6, "99.13"),
        (119, "0.87"),
    ],
)
def test_speed_score_is_linear_between_5_and_120_minutes(minutes: float, expected: str) -> None:
    assert speed_score(int(minutes * 60), DEFAULT) == Decimal(expected)


def test_speed_score_without_data() -> None:
    assert speed_score(None, DEFAULT) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (0, "0"), (5, "0"), (17.5, "50.00"), (30, "100"), (45, "100")],
)
def test_linear_score_between_thresholds(value: float | None, expected: str | None) -> None:
    got = linear_score(Decimal(str(value)) if value is not None else None, Decimal(5), Decimal(30))
    assert got == (Decimal(expected) if expected is not None else None)


def test_revenue_target_follows_days_elapsed() -> None:
    assert revenue_target(DEFAULT, Decimal(7)) == Decimal(20_000_000)
    assert revenue_target(DEFAULT, Decimal("3.5")) == Decimal(10_000_000)
    assert revenue_target(DEFAULT, Decimal(30)).quantize(Decimal(1)) == Decimal(85_714_286)


def test_score_does_not_depend_on_other_people() -> None:
    """Ngưỡng tuyệt đối (mục K): thêm hay bớt người khác không đổi điểm của một người."""
    params = FormulaParams(weights=DEFAULT.weights, min_leads=1)
    me = MemberMetrics(
        uuid.uuid4(), lead_count=10, close_rate=Decimal("0.2"), phone_rate=Decimal("0.5")
    )
    better = MemberMetrics(uuid.uuid4(), lead_count=10, close_rate=Decimal("0.9"))
    alone = compute_scores([me], params)[0]
    together = next(s for s in compute_scores([me, better], params) if s.metrics is me)
    assert alone.total == together.total
    assert alone.components["close_rate"] == Decimal("60.00")  # (20 − 5) / (30 − 5)
    assert alone.components["phone_rate"] == Decimal("40.00")  # (50 − 30) / (80 − 30)


@pytest.mark.parametrize(
    ("posts", "days", "expected"),
    [
        (5, "7", "100.00"),
        (9, "7", "100.00"),  # vượt mục tiêu vẫn tối đa 100
        (2, "7", "40.00"),
        (0, "7", "0.00"),
        (2, "3.5", "80.00"),  # kỳ mới qua nửa tuần: mục tiêu 2,5 bài
        (10, "30", "46.67"),  # 30 ngày: mục tiêu 21,43 bài
    ],
)
def test_page_care_follows_decision_5(posts: int, days: str, expected: str) -> None:
    assert page_care_score(posts, Decimal(days), DEFAULT) == Decimal(expected)


def test_page_care_without_data_or_target() -> None:
    assert page_care_score(None, Decimal(7), DEFAULT) is None
    no_target = FormulaParams(weights=DEFAULT.weights, posts_per_week_target=0)
    assert page_care_score(3, Decimal(7), no_target) is None


def test_missing_page_care_redistributes_weight() -> None:
    components = {
        "close_rate": Decimal(100),
        "response_speed": Decimal(0),
        "revenue": Decimal(100),
        "phone_rate": Decimal(100),
        "page_care": None,
        "on_time": Decimal(100),
    }
    # (30 + 20 + 10 + 5) × 100 / 90 = 72.22
    assert weighted_total(components, DEFAULT.weights) == Decimal("72.22")
    full = {**components, "page_care": Decimal(100)}
    assert weighted_total(full, DEFAULT.weights) == Decimal("75.00")
    assert weighted_total(dict.fromkeys(components), DEFAULT.weights) is None


@pytest.mark.parametrize(
    ("total", "tier"),
    [
        ("100", Tier.A),
        ("85", Tier.A),
        ("84.99", Tier.B),
        ("70", Tier.B),
        ("69.99", Tier.C),
        ("50", Tier.C),
        ("49.99", Tier.D),
        ("0", Tier.D),
    ],
)
def test_tier_boundaries(total: str, tier: Tier) -> None:
    assert tier_of(Decimal(total), DEFAULT) == tier


def _lead(
    owner: uuid.UUID,
    *,
    response: int | None = 60,
    waiting: int | None = None,
    phone: bool = False,
    won: int | None = None,
    result_at: dt.datetime | None = None,
    due: dt.datetime = NOW - dt.timedelta(hours=1),
    source: LeadSource = LeadSource.MESSAGE,
) -> LeadFacts:
    return LeadFacts(
        owner_id=owner,
        source=source,
        status=LeadStatus.WON if won else LeadStatus.CONTACTED,
        response_seconds=response,
        waiting_seconds=waiting,
        has_phone=phone,
        won_value_vnd=won,
        result_at=result_at if result_at else (NOW - dt.timedelta(hours=2) if won else None),
        result_due_at=due,
    )


def test_member_metrics() -> None:
    owner = uuid.uuid4()
    leads = [
        _lead(owner, response=60, phone=True, won=500_000),
        _lead(owner, response=600, phone=True),
        # Chưa trả lời, đã chờ quá 120 phút: tính bằng 120 phút.
        _lead(owner, response=None, waiting=8000),
        # Chưa trả lời, mới chờ 10 phút: chưa tính.
        _lead(owner, response=None, waiting=600, due=NOW + dt.timedelta(hours=40)),
        # Khách form: không tính tốc độ.
        _lead(owner, response=None, source=LeadSource.LEADGEN, due=NOW + dt.timedelta(hours=40)),
    ]
    m = member_metrics(owner, leads, NOW, DEFAULT)
    assert m.lead_count == 5
    assert m.won_count == 1
    assert m.revenue_vnd == 500_000
    assert m.close_rate == Decimal("0.2000")
    assert m.phone_rate == Decimal("0.4000")
    assert m.median_response_seconds == 600  # trung vị của 60, 600, 7200
    # 3 khách đã qua hạn hoặc có kết quả, 1 khách có kết quả đúng hạn.
    assert m.on_time_rate == Decimal("0.3333")


def test_compute_scores_ranks_and_insufficient_data() -> None:
    params = FormulaParams(weights=DEFAULT.weights, min_leads=2)
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    metrics = [
        MemberMetrics(
            a,
            lead_count=10,
            won_count=3,
            revenue_vnd=20_000_000,
            close_rate=Decimal("0.3"),
            phone_rate=Decimal("0.6"),
            on_time_rate=Decimal(1),
            median_response_seconds=60,
        ),
        MemberMetrics(
            b,
            lead_count=10,
            won_count=1,
            revenue_vnd=100,
            close_rate=Decimal("0.1"),
            phone_rate=Decimal("0.2"),
            on_time_rate=Decimal("0.5"),
            median_response_seconds=7200,
        ),
        MemberMetrics(c, lead_count=1, won_count=1, revenue_vnd=10_000, close_rate=Decimal(1)),
    ]
    scores = {s.metrics.member_id: s for s in compute_scores(metrics, params)}
    # a: chốt 30% → 100, tốc độ → 100, doanh thu đủ mức tuần → 100, SĐT 60% → 60, đúng hạn → 100;
    # Chăm Trang chưa có số liệu nên chia lại trọng số: 8600 / 90.
    assert scores[a].total == Decimal("95.56") and scores[a].tier == Tier.A and scores[a].rank == 1
    # b: chốt 10% → 20 điểm, còn lại 0: 30 × 20 / 90.
    assert scores[b].total == Decimal("6.67") and scores[b].tier == Tier.D and scores[b].rank == 2
    assert scores[a].components["page_care"] is None
    # Dưới số khách tối thiểu: không điểm, không hạng.
    assert scores[c].insufficient_data and scores[c].total is None and scores[c].rank is None


def test_equal_totals_share_rank() -> None:
    params = FormulaParams(weights=DEFAULT.weights, min_leads=1)
    ids = [uuid.uuid4() for _ in range(3)]
    metrics = [MemberMetrics(i, lead_count=5, close_rate=Decimal("0.2")) for i in ids]
    ranks = sorted(s.rank for s in compute_scores(metrics, params))  # type: ignore[type-var]
    assert ranks == [1, 1, 1]


def test_week_is_monday_to_sunday_in_workspace_time() -> None:
    # 23:30 Chủ nhật 18/10 giờ VN = 16:30 UTC cùng ngày: vẫn thuộc tuần 12–18/10.
    sunday_night = dt.datetime(2026, 10, 18, 16, 30, tzinfo=dt.UTC)
    week = period_for(PeriodType.WEEK, sunday_night, VN)
    assert (week.first_day, week.last_day) == (dt.date(2026, 10, 12), dt.date(2026, 10, 18))
    start, end = week.utc_range(VN)
    assert start == dt.datetime(2026, 10, 11, 17, 0, tzinfo=dt.UTC)
    assert end == dt.datetime(2026, 10, 18, 17, 0, tzinfo=dt.UTC)
    # 00:30 thứ Hai 19/10 giờ VN: sang tuần mới; tuần trước là 12–18/10.
    monday = dt.datetime(2026, 10, 18, 17, 30, tzinfo=dt.UTC)
    assert period_for(PeriodType.WEEK, monday, VN).first_day == dt.date(2026, 10, 19)
    assert previous_week(monday, VN) == week_of(dt.date(2026, 10, 12))


def test_reference_periods() -> None:
    assert period_for(PeriodType.ROLLING_7, NOW, VN).first_day == dt.date(2026, 10, 11)
    assert period_for(PeriodType.ROLLING_30, NOW, VN).first_day == dt.date(2026, 9, 18)
    month = period_for(PeriodType.MONTH, NOW, VN)
    assert (month.first_day, month.last_day) == (dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    december = period_for(PeriodType.MONTH, dt.datetime(2026, 12, 15, tzinfo=dt.UTC), VN)
    assert december.last_day == dt.date(2026, 12, 31)
