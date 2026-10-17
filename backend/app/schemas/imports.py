"""Schema nhập nhân viên từ Excel (Bước 6)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from app.models import MemberRole


class ImportRow(BaseModel):
    row: int  # số dòng trong file (dòng tiêu đề là 1)
    full_name: str
    email: str
    team: str | None
    role: MemberRole | None
    page: str | None
    page_id: uuid.UUID | None
    action: Literal["create", "update"] | None
    errors: list[str]


class ImportPreview(BaseModel):
    id: uuid.UUID
    file_name: str
    rows_total: int
    rows_ok: int
    rows_failed: int
    rows: list[ImportRow]


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    # File mật khẩu tạm (.xlsx, base64) cho tài khoản mới. Chỉ trả một lần, không lưu trên máy chủ.
    credentials_file: str | None
