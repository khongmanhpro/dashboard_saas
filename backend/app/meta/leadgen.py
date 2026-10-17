"""Lấy chi tiết form khách hàng tiềm năng.

Webhook `leadgen` chỉ có `leadgen_id`; nội dung form phải gọi Graph API bằng mã của Trang
(có từ Bước 6). Ở MOCK_MODE đọc từ `tests/fixtures/meta/leadgen_forms.json`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "meta"
# Chỉ giữ các trường cần dùng (CLAUDE.md mục 5: không lưu thừa dữ liệu khách).
KEPT_FIELDS = ("phone_number", "full_name")


@lru_cache
def _mock_forms() -> dict[str, Any]:
    path = FIXTURES_DIR / "leadgen_forms.json"
    if not path.exists():  # image production không chứa thư mục tests
        return {}
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def keep_needed_fields(field_data: list[dict[str, Any]]) -> dict[str, str]:
    """`[{"name": "phone_number", "values": ["…"]}]` → `{"phone_number": "…"}`, bỏ trường thừa."""
    kept: dict[str, str] = {}
    for item in field_data:
        name = item.get("name")
        values = item.get("values") or []
        if name in KEPT_FIELDS and values:
            kept[str(name)] = str(values[0])
    return kept


def mock_field_data(form_id: str | None) -> dict[str, str] | None:
    """Dữ liệu form giả theo `form_id`. None nếu fixture không có form này."""
    form = _mock_forms().get(form_id or "")
    if form is None:
        return None
    return keep_needed_fields(form["field_data"])
