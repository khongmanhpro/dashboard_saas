"""Xuất Excel cho Tổng quan và Fanpage (Bước 7). Không có SĐT hay nội dung tin nhắn."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from openpyxl import Workbook

from app.i18n import vi
from app.schemas.reports import OverviewOut, PageReportRow
from app.services.xlsx import append_row, to_bytes


def _number(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _percent(value: Decimal | None) -> float | None:
    return round(float(value) * 100, 1) if value is not None else None


def overview_xlsx(data: OverviewOut) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None  # noqa: S101 — Workbook mới luôn có một sheet
    ws.title = vi.EXPORT_OVERVIEW_SHEET
    append_row(ws, [vi.EXPORT_RANGE.format(first=data.range.first_day, last=data.range.last_day)])
    append_row(ws, vi.EXPORT_OVERVIEW_HEADER)
    for key, label in vi.EXPORT_OVERVIEW_ROWS.items():
        metric = getattr(data.kpis, key)
        if metric is None:
            continue
        convert = _percent if key in ("phone_rate", "close_rate") else _number
        append_row(ws, [label, convert(metric.value), convert(metric.previous)])
    if data.campaigns is not None:
        sheet = wb.create_sheet(vi.EXPORT_CAMPAIGN_SHEET)
        append_row(sheet, vi.EXPORT_CAMPAIGN_HEADER)
        for c in data.campaigns:
            append_row(sheet, [c.name, c.spend_vnd, c.leads, c.won, c.cost_per_won_vnd])
    return to_bytes(wb)


def pages_xlsx(rows: list[PageReportRow]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None  # noqa: S101 — Workbook mới luôn có một sheet
    ws.title = vi.EXPORT_PAGES_SHEET
    append_row(ws, vi.EXPORT_PAGES_HEADER)
    for r in rows:
        append_row(
            ws,
            [
                r.name,
                r.fb_page_id,
                r.bm_name,
                r.owner.name if r.owner else None,
                _number(r.owner_total),
                r.owner_tier.value if r.owner_tier else None,
                r.leads_7d,
                round(r.median_response_seconds / 60) if r.median_response_seconds else None,
                r.won_7d,
                r.posts_7d,
                r.views_30d,
                vi.EXPORT_PAGE_STATUS[r.status],
            ],
        )
    return to_bytes(wb)
