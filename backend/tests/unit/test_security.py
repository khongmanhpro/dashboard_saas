from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from app.core.security import (
    PasswordPolicyError,
    digest_matches,
    hash_password,
    password_needs_rehash,
    token_digest,
    validate_password,
    verify_password,
)


def test_hash_is_argon2id_and_verifies() -> None:
    hashed = hash_password("đúng-mật-khẩu-123")
    assert hashed.startswith("$argon2id$")
    assert "đúng-mật-khẩu-123" not in hashed
    assert verify_password(hashed, "đúng-mật-khẩu-123")
    assert not verify_password(hashed, "sai-mật-khẩu-123")


def test_verify_handles_missing_or_broken_hash() -> None:
    assert not verify_password(None, "anything-long")
    assert not verify_password("not-a-hash", "anything-long")


def test_detects_hash_needing_upgrade() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash("abcdefghijk")
    assert password_needs_rehash(weak)
    assert not password_needs_rehash(hash_password("abcdefghijk"))


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("short", "password_too_short"),
        ("x" * 129, "password_too_long"),
        ("nhanvien186", "password_same_as_email"),
        ("nhanvien186@example.com", "password_same_as_email"),
        ("1234567890", "password_too_common"),
        ("aaaaaaaaaaaa", "password_too_common"),
        ("abababababab", "password_too_common"),
    ],
)
def test_password_policy_rejects(password: str, code: str) -> None:
    with pytest.raises(PasswordPolicyError) as info:
        validate_password(password, "nhanvien186@example.com")
    assert info.value.code == code


def test_password_policy_accepts_reasonable_password() -> None:
    validate_password("Trang-Didongfix-2026", "nhanvien186@example.com")


def test_token_digest_is_keyed_and_purpose_bound() -> None:
    d = token_digest("tok", "session")
    assert len(d) == 32
    assert d != token_digest("tok", "csrf")
    assert digest_matches("tok", "session", d)
    assert not digest_matches("tok2", "session", d)
