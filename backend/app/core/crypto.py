"""Mã hóa mã truy cập Meta trước khi lưu DB (Fernet).

Hỗ trợ xoay khóa: `TOKEN_ENCRYPTION_KEY=khoa_moi,khoa_cu`. Khóa đầu dùng để mã hóa,
mọi khóa đều thử khi giải mã. Gọi `rotate()` để mã hóa lại bằng khóa mới.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings


class TokenDecryptError(Exception):
    """Không giải mã được (sai khóa hoặc dữ liệu hỏng). Không chứa nội dung mã."""


class TokenCipher:
    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("Cần ít nhất một khóa Fernet")
        self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])

    def encrypt(self, plaintext: str) -> bytes:
        if not plaintext:
            raise ValueError("Không mã hóa chuỗi rỗng")
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            raise TokenDecryptError("Không giải mã được mã truy cập") from exc

    def rotate(self, ciphertext: bytes) -> bytes:
        try:
            return self._fernet.rotate(ciphertext)
        except InvalidToken as exc:
            raise TokenDecryptError("Không giải mã được mã truy cập") from exc


def last4(secret: str) -> str:
    """4 ký tự cuối để hiển thị trên giao diện."""
    return secret[-4:] if len(secret) >= 8 else "••••"


@lru_cache
def get_token_cipher() -> TokenCipher:
    return TokenCipher(get_settings().fernet_keys)
