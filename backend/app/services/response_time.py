"""Thời gian trả lời tính trong giờ làm việc (CLAUDE.md mục 3, quyết định #15).

Giờ làm việc áp dụng 7 ngày/tuần theo múi giờ của workspace. Khách nhắn ngoài giờ thì đồng hồ
bắt đầu từ đầu ca kế tiếp; Trang trả lời ngoài giờ thì đồng hồ dừng ở cuối ca trước đó.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def business_seconds(
    start: dt.datetime,
    end: dt.datetime,
    *,
    tz: ZoneInfo,
    work_start: dt.time,
    work_end: dt.time,
) -> int:
    """Số giây nằm trong giờ làm việc giữa `start` và `end` (làm tròn xuống)."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start và end phải có múi giờ")
    if work_start >= work_end:
        raise ValueError("work_start phải trước work_end")
    if end <= start:
        return 0

    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    total = dt.timedelta()
    day = local_start.date()
    while day <= local_end.date():
        shift_open = dt.datetime.combine(day, work_start, tzinfo=tz)
        shift_close = dt.datetime.combine(day, work_end, tzinfo=tz)
        lo = max(shift_open, local_start)
        hi = min(shift_close, local_end)
        if hi > lo:
            # Trừ theo UTC: phép trừ hai datetime cùng tzinfo của Python bỏ qua đổi giờ mùa hè.
            total += hi.astimezone(dt.UTC) - lo.astimezone(dt.UTC)
        day += dt.timedelta(days=1)
    return int(total.total_seconds())
