"""Mật khẩu (argon2id), token phiên và CSRF (chỉ lưu HMAC trong DB)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# Danh sách ngắn các mật khẩu phổ biến nhất; chặn thêm ở đây khi cần.
_COMMON_PASSWORDS = {
    "1234567890",
    "12345678910",
    "0123456789",
    "qwertyuiop",
    "password123",
    "matkhau123",
    "abc1234567",
    "1111111111",
    "admin12345",
}


class PasswordPolicyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@lru_cache
def _hasher() -> PasswordHasher:
    if get_settings().app_env == "test":
        # Test chạy nhanh hơn; production dùng tham số mặc định (RFC 9106).
        return PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    return PasswordHasher()


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """So mật khẩu. Khi không có hash vẫn chạy argon2 để thời gian phản hồi như nhau."""
    try:
        return _hasher().verify(password_hash or _dummy_hash(), password) and bool(password_hash)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)


def validate_password(password: str, email: str | None = None) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError("password_too_short")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError("password_too_long")
    lowered = password.lower()
    if email:
        email = email.lower()
        if lowered in (email, email.split("@", 1)[0]):
            raise PasswordPolicyError("password_same_as_email")
    if lowered in _COMMON_PASSWORDS or len(set(password)) <= 2:
        raise PasswordPolicyError("password_too_common")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str, purpose: str) -> bytes:
    """HMAC-SHA256 của token. DB chỉ giữ giá trị này, lộ DB cũng không dùng lại được phiên."""
    key = get_settings().app_secret_key.get_secret_value().encode()
    return hmac.new(key, f"{purpose}:{token}".encode(), hashlib.sha256).digest()


def digest_matches(token: str, purpose: str, expected: bytes) -> bool:
    return hmac.compare_digest(token_digest(token, purpose), expected)
