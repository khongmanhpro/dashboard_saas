"""Chuẩn hóa và che số điện thoại Việt Nam.

`extract_vn_phones` tìm số trong tin nhắn của khách theo regex ở mục 3 CLAUDE.md, sau khi bỏ
dấu cách, dấu chấm, dấu gạch giữa các chữ số (quyết định Bước 3).
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")
# Số di động Việt Nam sau khi bỏ ký tự phân cách: 0 hoặc 84 + đầu 3/5/7/8/9 + 8 chữ số.
_MOBILE = re.compile(r"^(?:84|0)([35789]\d{8})$")

MASK_DOT = "•"

# Regex CLAUDE.md `(?:\+?84|0)(?:3|5|7|8|9)\d{8}`, cho phép một ký tự phân cách giữa các chữ số
# và không dính vào dãy số dài hơn (mã đơn, số tài khoản).
_IN_TEXT = re.compile(r"(?<![\d+])(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)")
# Che SĐT trong nội dung tin nhắn: bắt cả dạng chưa chuẩn, rộng hơn _IN_TEXT một chút.
_ANY_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)")


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


def extract_vn_phones(text: str | None) -> list[str]:
    """Các SĐT di động Việt Nam trong `text`, đã chuẩn hóa, giữ thứ tự, không trùng."""
    if not text:
        return []
    found: list[str] = []
    for match in _IN_TEXT.finditer(text):
        phone = normalize_vn_phone(match.group(0))
        if phone and phone not in found:
            found.append(phone)
    return found


def mask_phones_in_text(text: str) -> str:
    """Che mọi SĐT trong một đoạn văn (dùng cho nội dung tin nhắn khi thiếu quyền xem SĐT)."""
    return _ANY_PHONE.sub(lambda m: mask_phone(m.group(0)), text)
