"""Khoảng thời gian của các màn hình báo cáo (Bước 7) và kỳ liền trước cùng độ dài."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

from app.services.errors import ServiceError

RangeKey = Literal["today", "7d", "30d", "90d", "month", "custom"]
MAX_CUSTOM_DAYS = 90


@dataclass(frozen=True)
class DateRange:
    key: RangeKey
    start: dt.datetime  # UTC, gồm
    end: dt.datetime  # UTC, không gồm (thường là "bây giờ")
    first_day: dt.date  # theo múi giờ workspace
    last_day: dt.date
    tz: ZoneInfo

    @property
    def days(self) -> list[dt.date]:
        n = (self.last_day - self.first_day).days + 1
        return [self.first_day + dt.timedelta(days=i) for i in range(n)]

    def previous(self) -> DateRange:
        """Kỳ liền trước cùng độ dài, để so sánh."""
        length = self.end - self.start
        span = (self.last_day - self.first_day).days + 1
        return DateRange(
            key=self.key,
            start=self.start - length,
            end=self.start,
            first_day=self.first_day - dt.timedelta(days=span),
            last_day=self.first_day - dt.timedelta(days=1),
            tz=self.tz,
        )


def _midnight(day: dt.date, tz: ZoneInfo) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tzinfo=tz).astimezone(dt.UTC)


def resolve_range(
    key: RangeKey,
    tz: ZoneInfo,
    now: dt.datetime,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> DateRange:
    today = now.astimezone(tz).date()
    if key == "custom":
        if date_from is None or date_to is None or date_from > date_to:
            raise ServiceError("invalid_range", 422)
        if (date_to - date_from).days + 1 > MAX_CUSTOM_DAYS:
            raise ServiceError("range_too_long", 422, max_days=MAX_CUSTOM_DAYS)
        last = min(date_to, today)
        end = min(_midnight(last + dt.timedelta(days=1), tz), now)
        return DateRange(key, _midnight(date_from, tz), end, date_from, last, tz)
    if key == "month":
        first = today.replace(day=1)
    else:
        span = {"today": 1, "7d": 7, "30d": 30, "90d": 90}[key]
        first = today - dt.timedelta(days=span - 1)
    return DateRange(key, _midnight(first, tz), now, first, today, tz)
