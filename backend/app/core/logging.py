"""Log dạng JSON, tự che số điện thoại và các chuỗi bí mật trước khi ghi ra."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sys
from typing import Any

from app.services.phone import mask_phone

_REDACTED = "[ĐÃ CHE]"

# Số di động VN, chấp nhận dấu cách/chấm/gạch giữa các chữ số.
_PHONE = re.compile(r"(?<![\d])(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?![\d])")

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Mã truy cập Meta (user/system user/page token đều bắt đầu bằng EAA).
    (re.compile(r"EAA[A-Za-z0-9]{10,}"), _REDACTED),
    # Mã bot Telegram (dạng 123456789:AA...), kể cả khi nằm trong URL /bot<mã>/.
    (re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_\-]{30,}"), _REDACTED),
    # Chuỗi mã hóa Fernet.
    (re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}"), _REDACTED),
    # Tham số trên URL hoặc dạng key=value.
    (
        re.compile(
            r"(?i)\b(access_token|appsecret_proof|token|password|secret|client_secret)=([^&\s\"']+)"
        ),
        rf"\1={_REDACTED}",
    ),
    # Trường JSON có tên nhạy cảm.
    (
        re.compile(r"(?i)(\"(?:[a-z_]*password|[a-z_]*token|[a-z_]*secret)\"\s*:\s*\")[^\"]*(\")"),
        rf"\1{_REDACTED}\2",
    ),
    # Header xác thực.
    (
        re.compile(r"(?i)\b(authorization|cookie|set-cookie)(\s*[:=]\s*)[^\n\"]+"),
        rf"\1\2{_REDACTED}",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), f"Bearer {_REDACTED}"),
]


def redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return _PHONE.sub(lambda m: mask_phone(m.group(0)), text)


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            payload["ctx"] = extra
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Che trên chuỗi cuối cùng để không sót trường nào (kể cả traceback).
        return redact(json.dumps(payload, ensure_ascii=False, default=str))


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingJsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "arq"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    # Access log do Caddy ghi; ở đây chỉ làm nhiễu (healthcheck mỗi 5 giây).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
