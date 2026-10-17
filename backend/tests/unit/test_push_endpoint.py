"""Mục O: chỉ gửi thông báo đẩy tới dịch vụ đẩy của trình duyệt (chặn SSRF)."""

from __future__ import annotations

import pytest

from app.services.push import is_push_endpoint


@pytest.mark.parametrize(
    "url",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGx3abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
        "https://fcm.googleapis.com:443/fcm/send/abc",
    ],
)
def test_accepts_browser_push_services(url: str) -> None:
    assert is_push_endpoint(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com:8443/fcm/send/abc",
        "https://10.0.0.5/noi-bo",
        "https://localhost/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://evilnotify.windows.com/x",
        "https://notify.windows.com.evil.example/x",
        "https://user:pw@fcm.googleapis.com/x",
        "https://fcm.googleapis.com@10.0.0.5/x",
        "https://",
        "not a url",
    ],
)
def test_rejects_other_hosts(url: str) -> None:
    assert not is_push_endpoint(url)
