"""Gửi tin Telegram (Bước 7). Một bot cho cả hệ thống (`TELEGRAM_BOT_TOKEN`).

Mã bot nằm trong đường dẫn URL của Telegram, nên mọi lỗi được đổi thành `TelegramError` chỉ có mã
lỗi, không kèm URL. Không bao giờ ghi mã bot vào log. MOCK_MODE không gửi thật.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import get_settings

API = "https://api.telegram.org"
MAX_TEXT = 4000


class TelegramError(Exception):
    """`kind`: not_configured | chat_not_found | blocked | rate_limit | network | other."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"telegram_{kind}")
        self.kind = kind


class TelegramSender(Protocol):
    is_mock: bool

    async def send(self, chat_id: str, text: str) -> None: ...


class HttpTelegram:
    is_mock = False

    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._transport = transport

    async def send(self, chat_id: str, text: str) -> None:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15) as http:
                response = await http.post(
                    f"{API}/bot{self._token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text[:MAX_TEXT],
                        "disable_web_page_preview": True,
                    },
                )
        except httpx.HTTPError:
            raise TelegramError("network") from None
        if response.is_success:
            return
        if response.status_code == 429:
            raise TelegramError("rate_limit")
        if response.status_code == 403:
            raise TelegramError("blocked")  # bot bị chặn hoặc bị xóa khỏi nhóm
        if response.status_code == 400:
            raise TelegramError("chat_not_found")
        raise TelegramError("other")


class MockTelegram:
    """MOCK_MODE: giữ tin trong bộ nhớ để test, không gửi ra ngoài."""

    is_mock = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


_override: TelegramSender | None = None


def get_telegram() -> TelegramSender:
    if _override is not None:
        return _override
    s = get_settings()
    if s.mock_mode:
        return MockTelegram()
    token = s.telegram_bot_token.get_secret_value()
    if not token:
        raise TelegramError("not_configured")
    return HttpTelegram(token)


def set_telegram(sender: TelegramSender | None) -> None:
    global _override
    _override = sender
