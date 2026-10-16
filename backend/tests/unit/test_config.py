from __future__ import annotations

import secrets

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings


def _base(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "app_env": "development",
        "app_secret_key": secrets.token_urlsafe(48),
        "token_encryption_key": Fernet.generate_key().decode(),
        "postgres_user": "fanpage",
        "postgres_app_user": "fanpage_app",
    }
    values.update(overrides)
    return values


def _production(**overrides: object) -> dict[str, object]:
    return _base(
        app_env="production",
        app_base_url="https://app.example.vn",
        postgres_password="admin-pw-" + secrets.token_hex(8),
        postgres_app_password="app-pw-" + secrets.token_hex(8),
        **overrides,
    )


def test_valid_development_settings() -> None:
    s = Settings(**_base())  # type: ignore[arg-type]
    assert s.cookie_secure is False
    assert s.database_url.startswith("postgresql+asyncpg://fanpage_app:")


def test_valid_production_settings() -> None:
    s = Settings(**_production())  # type: ignore[arg-type]
    assert s.cookie_secure is True
    assert s.is_production_like


@pytest.mark.parametrize("key", ["", "short", "changeme"])
def test_rejects_weak_app_secret(key: str) -> None:
    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        Settings(**_base(app_secret_key=key))  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["", "not-a-fernet-key"])
def test_rejects_invalid_fernet_key(key: str) -> None:
    with pytest.raises(ValidationError, match="TOKEN_ENCRYPTION_KEY") as info:
        Settings(**_base(token_encryption_key=key))  # type: ignore[arg-type]
    if key:
        assert key not in str(info.value).split("input_value")[0]


def test_accepts_multiple_fernet_keys_for_rotation() -> None:
    keys = f"{Fernet.generate_key().decode()},{Fernet.generate_key().decode()}"
    s = Settings(**_base(token_encryption_key=keys))  # type: ignore[arg-type]
    assert len(s.fernet_keys) == 2


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"app_base_url": "http://app.example.vn"}, "https"),
        ({"postgres_app_password": ""}, "POSTGRES_APP_PASSWORD"),
        ({"postgres_app_user": "fanpage"}, "RLS"),
    ],
)
def test_production_refuses_unsafe_config(override: dict[str, object], message: str) -> None:
    values = _production()
    values.update(override)
    with pytest.raises(ValidationError, match=message):
        Settings(**values)  # type: ignore[arg-type]


def test_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="Múi giờ"):
        Settings(**_base(app_timezone="Mars/Olympus"))  # type: ignore[arg-type]


def test_password_with_special_chars_is_url_encoded() -> None:
    s = Settings(**_base(postgres_app_password="p@ss/w:rd"))  # type: ignore[arg-type]
    assert "p%40ss%2Fw%3Ard@" in s.database_url
