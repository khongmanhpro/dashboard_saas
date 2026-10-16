from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import TokenCipher, TokenDecryptError, get_token_cipher, last4

FAKE_TOKEN = "EAAGfakeTokenForTestsOnly0000000000000wxyz"


def test_roundtrip_and_ciphertext_hides_plaintext() -> None:
    cipher = TokenCipher([Fernet.generate_key().decode()])
    encrypted = cipher.encrypt(FAKE_TOKEN)
    assert FAKE_TOKEN.encode() not in encrypted
    assert cipher.decrypt(encrypted) == FAKE_TOKEN


def test_same_plaintext_gives_different_ciphertexts() -> None:
    cipher = TokenCipher([Fernet.generate_key().decode()])
    assert cipher.encrypt(FAKE_TOKEN) != cipher.encrypt(FAKE_TOKEN)


def test_wrong_key_raises_without_leaking_token() -> None:
    encrypted = TokenCipher([Fernet.generate_key().decode()]).encrypt(FAKE_TOKEN)
    other = TokenCipher([Fernet.generate_key().decode()])
    with pytest.raises(TokenDecryptError) as info:
        other.decrypt(encrypted)
    assert FAKE_TOKEN not in str(info.value)


def test_tampered_ciphertext_is_rejected() -> None:
    cipher = TokenCipher([Fernet.generate_key().decode()])
    encrypted = bytearray(cipher.encrypt(FAKE_TOKEN))
    encrypted[-5] ^= 0x01
    with pytest.raises(TokenDecryptError):
        cipher.decrypt(bytes(encrypted))


def test_key_rotation() -> None:
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    old_ciphertext = TokenCipher([old_key]).encrypt(FAKE_TOKEN)
    rotating = TokenCipher([new_key, old_key])
    # Vẫn đọc được dữ liệu mã hóa bằng khóa cũ.
    assert rotating.decrypt(old_ciphertext) == FAKE_TOKEN
    rotated = rotating.rotate(old_ciphertext)
    # Sau khi xoay, chỉ cần khóa mới.
    assert TokenCipher([new_key]).decrypt(rotated) == FAKE_TOKEN


def test_rejects_empty_plaintext_and_empty_keys() -> None:
    with pytest.raises(ValueError):
        TokenCipher([Fernet.generate_key().decode()]).encrypt("")
    with pytest.raises(ValueError):
        TokenCipher([])


def test_last4() -> None:
    assert last4(FAKE_TOKEN) == "wxyz"
    assert last4("short") == "••••"


def test_cipher_from_settings() -> None:
    cipher = get_token_cipher()
    assert cipher.decrypt(cipher.encrypt(FAKE_TOKEN)) == FAKE_TOKEN
