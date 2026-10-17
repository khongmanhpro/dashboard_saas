"""Kỳ tính điểm theo múi giờ workspace (quyết định #18).

Kỳ chính thức là tuần T2–CN. 7 ngày / 30 ngày / tháng này chỉ để tham khảo. Mọi kỳ là các ngày
trọn vẹn theo giờ địa phương, đổi sang khoảng UTC nửa mở [start, end) để lọc khách.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.models import PeriodType


@dataclass(frozen=True)
class Period:
    type: PeriodType
    first_day: dt.date
    last_day: dt.date  # tính cả ngày này

    def utc_range(self, tz: ZoneInfo) -> tuple[dt.datetime, dt.datetime]:
        start = dt.datetime.combine(self.first_day, dt.time(0), tzinfo=tz)
        end = dt.datetime.combine(self.last_day + dt.timedelta(days=1), dt.time(0), tzinfo=tz)
        return start.astimezone(dt.UTC), end.astimezone(dt.UTC)


def local_today(now: dt.datetime, tz: ZoneInfo) -> dt.date:
    return now.astimezone(tz).date()


def week_of(day: dt.date) -> Period:
    monday = day - dt.timedelta(days=day.weekday())
    return Period(PeriodType.WEEK, monday, monday + dt.timedelta(days=6))


def period_for(period_type: PeriodType, now: dt.datetime, tz: ZoneInfo) -> Period:
    today = local_today(now, tz)
    if period_type == PeriodType.WEEK:
        return week_of(today)
    if period_type == PeriodType.ROLLING_7:
        return Period(period_type, today - dt.timedelta(days=6), today)
    if period_type == PeriodType.ROLLING_30:
        return Period(period_type, today - dt.timedelta(days=29), today)
    first = today.replace(day=1)
    next_month = (first + dt.timedelta(days=32)).replace(day=1)
    return Period(period_type, first, next_month - dt.timedelta(days=1))


def previous_week(now: dt.datetime, tz: ZoneInfo) -> Period:
    return week_of(local_today(now, tz) - dt.timedelta(days=7))
