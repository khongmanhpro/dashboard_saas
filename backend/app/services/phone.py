"""Chuẩn hóa và che số điện thoại Việt Nam.

Việc tìm số trong tin nhắn khách (regex ở mục 3 CLAUDE.md) làm ở Bước 2–3 trong
`phone_extract`; ở đây chỉ có phần dùng chung cho hiển thị và log.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")
# Số di động Việt Nam sau khi bỏ ký tự phân cách: 0 hoặc 84 + đầu 3/5/7/8/9 + 8 chữ số.
_MOBILE = re.compile(r"^(?:84|0)([35789]\d{8})$")

MASK_DOT = "•"


def normalize_vn_phone(raw: str) -> str | None:
    """Đưa số về dạng `0xxxxxxxxx`. Trả về None nếu không phải số di động Việt Nam."""
    digits = _NON_DIGIT.sub("", raw)
    match = _MOBILE.match(digits)
    if not match:
        return None
    return "0" + match.group(1)


def mask_phone(phone: str) -> str:
    """`0912345218` → `09•• ••• 218`. Số không chuẩn hóa được thì che gần hết."""
    normalized = normalize_vn_phone(phone)
    if normalized is None:
        digits = _NON_DIGIT.sub("", phone)
        if len(digits) <= 3:
            return MASK_DOT * len(digits)
        return MASK_DOT * (len(digits) - 3) + digits[-3:]
    return f"{normalized[:2]}{MASK_DOT * 2} {MASK_DOT * 3} {normalized[-3:]}"
