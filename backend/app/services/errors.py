from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Lỗi nghiệp vụ có mã ổn định. API trả `{"detail": {"code": ...}}`, giao diện tự dịch mã."""

    def __init__(self, code: str, status_code: int = 400, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.extra = extra
