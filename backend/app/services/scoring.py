"""Tính điểm nhân viên (CLAUDE.md mục 3, quyết định #1–#5, mục F trong decisions.md).

Toàn bộ là hàm thuần: đầu vào là dữ kiện từng khách và tham số công thức, đầu ra là điểm.
Job ban đêm và "xem thử" trong Cài đặt dùng chung các hàm này, nên luôn ra cùng một kết quả.

- Tốc độ trả lời: 100 điểm nếu trung vị ≤ `speed_full_minutes`, 0 điểm nếu ≥ `speed_zero_minutes`,
  nội suy tuyến tính ở giữa.
- Chăm Trang (quyết định #5, mục I): `min(số bài / mục tiêu, 1) × 100`, mục tiêu tuần quy đổi theo
  số ngày đã qua của kỳ.
- Tiêu chí khác: xếp phần trăm giữa những người đủ số khách tối thiểu.
- Tiêu chí chưa có số liệu (Trang chưa đồng bộ được bài đăng, hoặc người chưa có khách nào được trả
  lời): bỏ khỏi tổng, trọng số của nó chia lại cho các tiêu chí còn lại theo tỉ lệ.
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.models import LeadSource, LeadStatus, ScoreFormula, Tier

CRITERIA = ("close_rate", "response_speed", "revenue", "phone_rate", "page_care", "on_time")
_HUNDRED = Decimal(100)
_CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FormulaParams:
    weights: Mapping[str, int]
    speed_full_minutes: int = 5
    speed_zero_minutes: int = 120
    tier_a: int = 85
    tier_b: int = 70
    tier_c: int = 50
    min_leads: int = 10
    posts_per_week_target: int = 5

    @classmethod
    def from_model(cls, f: ScoreFormula) -> FormulaParams:
        return cls(
            weights={c: int(getattr(f, f"w_{c}")) for c in CRITERIA},
            speed_full_minutes=f.speed_full_minutes,
            speed_zero_minutes=f.speed_zero_minutes,
            tier_a=f.tier_a,
            tier_b=f.tier_b,
            tier_c=f.tier_c,
            min_leads=f.min_leads,
            posts_per_week_target=f.posts_per_week_target,
        )

    def with_weights(self, weights: Mapping[str, int]) -> FormulaParams:
        return FormulaParams(
            weights=dict(weights),
            speed_full_minutes=self.speed_full_minutes,
            speed_zero_minutes=self.speed_zero_minutes,
            tier_a=self.tier_a,
            tier_b=self.tier_b,
            tier_c=self.tier_c,
            min_leads=self.min_leads,
            posts_per_week_target=self.posts_per_week_target,
        )


@dataclass(frozen=True)
class LeadFacts:
    """Dữ kiện của một khách, dùng chung cho điểm và mọi chỉ số (app/services/metrics.py).

    `owner_id` None: khách vào Trang lúc chưa có người phụ trách (không tính điểm cho ai).
    """

    owner_id: uuid.UUID | None
    source: LeadSource
    status: LeadStatus
    response_seconds: int | None
    # Khách nhắn tin chưa được trả lời: số giây trong giờ làm việc đã chờ tới lúc tính.
    waiting_seconds: int | None
    has_phone: bool
    won_value_vnd: int | None
    result_at: dt.datetime | None
    result_due_at: dt.datetime
    page_id: uuid.UUID | None = None
    first_inbound_at: dt.datetime | None = None
    replied: bool = False  # docs/metrics.md: trả lời, hoặc đã gọi, hoặc trạng thái khác "Mới"
    called: bool = False
    campaign_id: uuid.UUID | None = None


@dataclass
class MemberMetrics:
    member_id: uuid.UUID
    lead_count: int = 0
    won_count: int = 0
    phone_count: int = 0
    revenue_vnd: int = 0
    close_rate: Decimal | None = None
    phone_rate: Decimal | None = None
    on_time_rate: Decimal | None = None
    median_response_seconds: int | None = None
    # Bài đăng trên Trang mình phụ trách trong kỳ. None: Trang chưa đồng bộ được bài đăng.
    posts_count: int | None = None


@dataclass
class MemberScore:
    metrics: MemberMetrics
    insufficient_data: bool
    components: dict[str, Decimal | None] = field(default_factory=dict)
    total: Decimal | None = None
    tier: Tier | None = None
    rank: int | None = None


def _rate(part: int, whole: int) -> Decimal | None:
    if whole <= 0:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def speed_samples(leads: Iterable[LeadFacts], params: FormulaParams) -> list[int]:
    """Số giây trả lời dùng để lấy trung vị. Khách chờ quá ngưỡng 0 điểm mà chưa được trả lời
    tính bằng ngưỡng; khách đang chờ ít hơn và khách từ form thì chưa tính (quyết định Bước 4)."""
    zero_seconds = params.speed_zero_minutes * 60
    samples = []
    for lead in leads:
        if lead.source != LeadSource.MESSAGE:
            continue
        if lead.response_seconds is not None:
            samples.append(lead.response_seconds)
        elif lead.waiting_seconds is not None and lead.waiting_seconds >= zero_seconds:
            samples.append(zero_seconds)
    return samples


def member_metrics(
    member_id: uuid.UUID, leads: Iterable[LeadFacts], now: dt.datetime, params: FormulaParams
) -> MemberMetrics:
    leads = list(leads)
    m = MemberMetrics(member_id=member_id)
    due_count = 0
    on_time = 0
    for lead in leads:
        m.lead_count += 1
        if lead.has_phone:
            m.phone_count += 1
        if lead.status == LeadStatus.WON:
            m.won_count += 1
            m.revenue_vnd += lead.won_value_vnd or 0
        if lead.result_at is not None or lead.result_due_at <= now:
            due_count += 1
            if lead.result_at is not None and lead.result_at <= lead.result_due_at:
                on_time += 1
    speeds = speed_samples(leads, params)
    m.close_rate = _rate(m.won_count, m.lead_count)
    m.phone_rate = _rate(m.phone_count, m.lead_count)
    m.on_time_rate = _rate(on_time, due_count)
    m.median_response_seconds = int(statistics.median(speeds)) if speeds else None
    return m


def speed_score(median_seconds: int | None, params: FormulaParams) -> Decimal | None:
    if median_seconds is None:
        return None
    full = params.speed_full_minutes * 60
    zero = params.speed_zero_minutes * 60
    if median_seconds <= full:
        return _HUNDRED
    if median_seconds >= zero:
        return Decimal(0)
    return _q(_HUNDRED * Decimal(zero - median_seconds) / Decimal(zero - full))


def page_care_score(
    posts: int | None, period_days: Decimal, params: FormulaParams
) -> Decimal | None:
    target = Decimal(params.posts_per_week_target) * period_days / 7
    if posts is None or target <= 0:
        return None
    return _q(min(Decimal(posts) / target, Decimal(1)) * _HUNDRED)


def percentile_scores(
    values: Mapping[uuid.UUID, Decimal | int | None],
) -> dict[uuid.UUID, Decimal | None]:
    """(số người thấp hơn + ½ số người bằng) ÷ (n − 1) × 100. Người không có giá trị: None."""
    present = {k: Decimal(v) for k, v in values.items() if v is not None}
    n = len(present)
    out: dict[uuid.UUID, Decimal | None] = {k: None for k in values}
    for key, value in present.items():
        if n == 1:
            out[key] = _HUNDRED
            continue
        lower = sum(1 for v in present.values() if v < value)
        equal = sum(1 for v in present.values() if v == value) - 1
        out[key] = _q(_HUNDRED * (Decimal(lower) + Decimal(equal) / 2) / Decimal(n - 1))
    return out


def weighted_total(
    components: Mapping[str, Decimal | None], weights: Mapping[str, int]
) -> Decimal | None:
    """Tổng có trọng số; tiêu chí thiếu số liệu thì chia lại trọng số cho các tiêu chí còn lại."""
    used = {c: weights[c] for c in CRITERIA if components.get(c) is not None and weights[c] > 0}
    weight_sum = sum(used.values())
    if weight_sum == 0:
        return None
    raw = sum(
        (Decimal(w) * components[c] for c, w in used.items()),  # type: ignore[operator]
        Decimal(0),
    )
    return _q(raw / Decimal(weight_sum))


def tier_of(total: Decimal, params: FormulaParams) -> Tier:
    if total >= params.tier_a:
        return Tier.A
    if total >= params.tier_b:
        return Tier.B
    if total >= params.tier_c:
        return Tier.C
    return Tier.D


def compute_scores(
    metrics: Iterable[MemberMetrics], params: FormulaParams, period_days: Decimal = Decimal(7)
) -> list[MemberScore]:
    """Điểm cho mọi người trong một kỳ. Thứ hạng kiểu 1, 2, 2, 4 khi bằng điểm.

    `period_days`: số ngày đã qua của kỳ, để quy đổi mục tiêu bài đăng."""
    all_metrics = list(metrics)
    sufficient = [m for m in all_metrics if m.lead_count >= params.min_leads and m.lead_count > 0]
    ids = {m.member_id for m in sufficient}

    close = percentile_scores({m.member_id: m.close_rate for m in sufficient})
    revenue = percentile_scores({m.member_id: m.revenue_vnd for m in sufficient})
    phone = percentile_scores({m.member_id: m.phone_rate for m in sufficient})
    on_time = percentile_scores({m.member_id: m.on_time_rate for m in sufficient})

    scores: list[MemberScore] = []
    for m in all_metrics:
        if m.member_id not in ids:
            scores.append(MemberScore(metrics=m, insufficient_data=True))
            continue
        components: dict[str, Decimal | None] = {
            "close_rate": close[m.member_id],
            "response_speed": speed_score(m.median_response_seconds, params),
            "revenue": revenue[m.member_id],
            "phone_rate": phone[m.member_id],
            "page_care": page_care_score(m.posts_count, period_days, params),
            "on_time": on_time[m.member_id],
        }
        total = weighted_total(components, params.weights)
        scores.append(
            MemberScore(
                metrics=m,
                insufficient_data=False,
                components=components,
                total=total,
                tier=tier_of(total, params) if total is not None else None,
            )
        )

    ranked = sorted((s for s in scores if s.total is not None), key=lambda s: s.total, reverse=True)  # type: ignore[arg-type, return-value]
    for i, s in enumerate(ranked):
        previous = ranked[i - 1] if i else None
        s.rank = previous.rank if previous and previous.total == s.total else i + 1
    return scores
