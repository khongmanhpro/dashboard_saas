"""Thời gian trả lời trong giờ làm việc: 08:00–22:00 Asia/Ho_Chi_Minh, 7 ngày/tuần."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.services.response_time import business_seconds

VN = ZoneInfo("Asia/Ho_Chi_Minh")
OPEN = dt.time(8, 0)
CLOSE = dt.time(22, 0)


def vn(day: int, hour: int, minute: int = 0, second: int = 0) -> dt.datetime:
    # Tháng 10/2026: ngày 16 là thứ Sáu, 17 thứ Bảy, 18 Chủ nhật.
    return dt.datetime(2026, 10, day, hour, minute, second, tzinfo=VN)


def minutes(start: dt.datetime, end: dt.datetime) -> float:
    return business_seconds(start, end, tz=VN, work_start=OPEN, work_end=CLOSE) / 60


@pytest.mark.parametrize(
    ("label", "start", "end", "expected"),
    [
        ("trong giờ", vn(16, 9), vn(16, 9, 12), 12),
        ("khách nhắn 23:00, trả lời 08:10 hôm sau", vn(16, 23), vn(17, 8, 10), 10),
        ("qua đêm 21:50 → 08:20 hôm sau", vn(16, 21, 50), vn(17, 8, 20), 30),
        ("sáng sớm, trả lời trước giờ mở cửa", vn(16, 6, 30), vn(16, 7, 45), 0),
        ("sáng sớm, trả lời sau giờ mở cửa", vn(16, 6, 30), vn(16, 8, 5), 5),
        ("khách nhắn 21:59, trả lời 22:30", vn(16, 21, 59), vn(16, 22, 30), 1),
        ("cả hai ngoài giờ cùng đêm", vn(16, 22, 30), vn(16, 23, 30), 0),
        ("đúng mốc mở cửa", vn(16, 8), vn(16, 8, 1), 1),
        ("đúng mốc đóng cửa", vn(16, 22), vn(17, 8), 0),
        ("cuối tuần vẫn tính (7 ngày/tuần)", vn(17, 10), vn(18, 10), 14 * 60),
        ("hai ngày trọn", vn(16, 23), vn(18, 23), 28 * 60),
        ("trả lời trước tin của khách", vn(16, 10), vn(16, 9), 0),
        ("cùng thời điểm", vn(16, 10), vn(16, 10), 0),
    ],
)
def test_business_minutes(
    label: str, start: dt.datetime, end: dt.datetime, expected: float
) -> None:
    assert minutes(start, end) == expected, label


def test_inputs_in_utc_are_converted_to_workspace_time() -> None:
    # 23:00 giờ VN = 16:00 UTC; 08:10 hôm sau giờ VN = 01:10 UTC.
    start = dt.datetime(2026, 10, 16, 16, 0, tzinfo=dt.UTC)
    end = dt.datetime(2026, 10, 17, 1, 10, tzinfo=dt.UTC)
    assert minutes(start, end) == 10


def test_seconds_are_truncated() -> None:
    assert (
        business_seconds(vn(16, 9), vn(16, 9, 0, 59), tz=VN, work_start=OPEN, work_end=CLOSE) == 59
    )


def test_custom_work_hours() -> None:
    seconds = business_seconds(
        vn(16, 17, 30), vn(17, 9, 15), tz=VN, work_start=dt.time(9), work_end=dt.time(18)
    )
    assert seconds == 45 * 60


def test_daylight_saving_day_counts_real_elapsed_time() -> None:
    # Berlin chuyển giờ 02:00 → 03:00 ngày 29/3/2026: ca 00:00–23:59 chỉ dài 22h59.
    berlin = ZoneInfo("Europe/Berlin")
    start = dt.datetime(2026, 3, 29, 1, 0, tzinfo=berlin)
    end = dt.datetime(2026, 3, 29, 4, 0, tzinfo=berlin)
    seconds = business_seconds(start, end, tz=berlin, work_start=dt.time(0), work_end=dt.time(23))
    assert seconds == 2 * 3600


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="múi giờ"):
        business_seconds(
            dt.datetime(2026, 10, 16, 9), vn(16, 10), tz=VN, work_start=OPEN, work_end=CLOSE
        )
