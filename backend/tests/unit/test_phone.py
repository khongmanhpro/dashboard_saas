from __future__ import annotations

import pytest

from app.services.phone import mask_phone, normalize_vn_phone


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
