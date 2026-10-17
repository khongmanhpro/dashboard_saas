"""Chữ ký webhook Meta: header `X-Hub-Signature-256: sha256=<hex HMAC-SHA256(body, app secret)>`."""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-Hub-Signature-256"
_PREFIX = "sha256="


def sign(body: bytes, app_secret: str) -> str:
    """Giá trị header đúng cho `body`. Dùng cho giả lập và test."""
    digest = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return _PREFIX + digest


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    if not app_secret or not header or not header.startswith(_PREFIX):
        return False
    return hmac.compare_digest(sign(body, app_secret), header.strip().lower())
