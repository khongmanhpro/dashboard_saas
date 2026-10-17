from __future__ import annotations

import pytest

from app.services.phone import (
    extract_vn_phones,
    mask_phone,
    mask_phones_in_text,
    normalize_vn_phone,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0912345218", "0912345218"),
        ("+84912345218", "0912345218"),
        ("84912345218", "0912345218"),
        ("091 234 5218", "0912345218"),
        ("0912.345.218", "0912345218"),
        ("0312345678", "0312345678"),
        ("0512345678", "0512345678"),
        ("0712345678", "0712345678"),
        ("0812345678", "0812345678"),
    ],
)
def test_normalize_valid(raw: str, expected: str) -> None:
    assert normalize_vn_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "0212345678", "0412345678", "091234521", "09123452189", "abc", "0612345678"],
)
def test_normalize_invalid(raw: str) -> None:
    assert normalize_vn_phone(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["0912345218", "+84912345218", "84 912 345 218"],
)
def test_mask_matches_design(raw: str) -> None:
    assert mask_phone(raw) == "09•• ••• 218"


def test_mask_unknown_format_keeps_only_last_three() -> None:
    assert mask_phone("12345678") == "•••••678"
    assert mask_phone("12") == "••"


# ---------------------------------------------------------------- tìm SĐT trong tin nhắn


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("số mình 0912345678 nhé", ["0912345678"]),
        ("0912 345 678", ["0912345678"]),
        ("0912.345.678", ["0912345678"]),
        ("0912-345-678", ["0912345678"]),
        ("+84912345678", ["0912345678"]),
        ("+84 912 345 678", ["0912345678"]),
        ("84912345678", ["0912345678"]),
        ("gọi 0382345678 hoặc 0582345678", ["0382345678", "0582345678"]),
        ("0912345678 và lại 0912345678", ["0912345678"]),
        ("đầu 02 không phải di động: 0212345678", []),
        ("đầu 1 cũ: 01234567890", []),
        ("thiếu số 091234567", []),
        ("dính vào dãy dài 109123456789", []),
        ("mã đơn 09123456789", []),
        ("", []),
        (None, []),
    ],
)
def test_extract_vn_phones(text: str | None, expected: list[str]) -> None:
    assert extract_vn_phones(text) == expected


def test_mask_phones_in_text() -> None:
    assert mask_phones_in_text("gọi 0912 345 218 chiều nay") == "gọi 09•• ••• 218 chiều nay"
    assert mask_phones_in_text("không có số") == "không có số"
