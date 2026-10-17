"""Các loại cảnh báo Telegram và giá trị mặc định (decisions.md mục I).

Chỉ cảnh báo, không tạm dừng hay đổi ngân sách quảng cáo (quyết định #7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertRule

RULE_TYPES = ("bm_status", "cost_per_result", "cost_per_won", "frequency", "daily_summary")

DEFAULTS: dict[str, tuple[bool, dict[str, int | float]]] = {
    "bm_status": (True, {}),
    # Chi phí/kết quả của chiến dịch trong ngày vượt ngưỡng, khi đã chi đủ nhiều.
    "cost_per_result": (True, {"max_vnd": 25_000, "min_spend_vnd": 300_000}),
    # Chi phí/khách chốt 7 ngày của chiến dịch vượt ngưỡng.
    "cost_per_won": (True, {"max_vnd": 500_000}),
    # Tần suất 7 ngày (ước tính) của chiến dịch vượt ngưỡng: khách đã thấy QC quá nhiều lần.
    "frequency": (False, {"max": 3.5}),
    # Tóm tắt hôm qua, gửi 08:00 giờ workspace.
    "daily_summary": (True, {}),
}

# Giới hạn hợp lệ của từng tham số khi Chủ sở hữu sửa.
PARAM_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "cost_per_result": {"max_vnd": (1_000, 10_000_000), "min_spend_vnd": (0, 100_000_000)},
    "cost_per_won": {"max_vnd": (1_000, 100_000_000)},
    "frequency": {"max": (1.0, 20.0)},
}


@dataclass(frozen=True)
class Rule:
    type: str
    enabled: bool
    params: dict[str, Any]


async def effective_rules(db: AsyncSession) -> dict[str, Rule]:
    """Quy tắc của workspace hiện tại: dòng đã lưu, thiếu thì lấy mặc định."""
    stored = {r.type: r for r in await db.scalars(select(AlertRule))}
    out: dict[str, Rule] = {}
    for rule_type in RULE_TYPES:
        enabled, params = DEFAULTS[rule_type]
        row = stored.get(rule_type)
        if row is not None:
            enabled = row.enabled
            params = {**params, **{k: v for k, v in row.params.items() if k in params}}
        out[rule_type] = Rule(rule_type, enabled, dict(params))
    return out
