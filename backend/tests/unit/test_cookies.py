from __future__ import annotations

import pytest
from fastapi import Response

from app.api import deps
from app.core.config import get_settings


@pytest.fixture
def https_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"app_base_url": "https://app.example.vn"})
    monkeypatch.setattr(deps, "get_settings", lambda: settings)


@pytest.mark.usefixtures("https_settings")
def test_https_uses_host_prefixed_secure_cookies() -> None:
    response = Response()
    deps.set_auth_cookies(response, "session-token", "csrf-token")
    cookies = response.headers.getlist("set-cookie")
    session = next(c for c in cookies if c.startswith("__Host-fp_session="))
    csrf = next(c for c in cookies if c.startswith("fp_csrf="))
    for cookie in (session, csrf):
        assert "Secure" in cookie
        assert "Path=/" in cookie
        assert "Domain" not in cookie
    assert "HttpOnly" in session
    assert "HttpOnly" not in csrf


def test_http_dev_cookie_not_secure() -> None:
    response = Response()
    deps.set_auth_cookies(response, "session-token", "csrf-token")
    session = next(c for c in response.headers.getlist("set-cookie") if c.startswith("fp_session="))
    assert "Secure" not in session
