"""Dựng payload webhook giống định dạng Meta gửi (object `page`). Dùng cho giả lập và test."""

from __future__ import annotations

import datetime as dt
from typing import Any


def _ms(at: dt.datetime) -> int:
    return int(at.timestamp() * 1000)


def page_payload(
    fb_page_id: str,
    *,
    messaging: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    at: dt.datetime | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": fb_page_id, "time": _ms(at or dt.datetime.now(dt.UTC))}
    if messaging is not None:
        entry["messaging"] = messaging
    if changes is not None:
        entry["changes"] = changes
    return {"object": "page", "entry": [entry]}


def inbound(
    fb_page_id: str,
    psid: str,
    mid: str,
    at: dt.datetime,
    text: str | None = "[Tin nhắn mẫu]",
    *,
    ad_id: str | None = None,
) -> dict[str, Any]:
    """Một phần tử `messaging`: khách gửi tin cho Trang."""
    message: dict[str, Any] = {"mid": mid}
    if text is not None:
        message["text"] = text
    if ad_id is not None:
        message["referral"] = {"source": "ADS", "type": "OPEN_THREAD", "ad_id": ad_id}
    return {
        "sender": {"id": psid},
        "recipient": {"id": fb_page_id},
        "timestamp": _ms(at),
        "message": message,
    }


def echo(
    fb_page_id: str,
    psid: str,
    mid: str,
    at: dt.datetime,
    text: str = "[Trả lời mẫu]",
    *,
    app_id: str | None = None,
    metadata: str | None = None,
) -> dict[str, Any]:
    """Một phần tử `messaging`: Trang gửi tin cho khách (`message_echoes`)."""
    message: dict[str, Any] = {"mid": mid, "is_echo": True, "text": text}
    if app_id is not None:
        message["app_id"] = int(app_id)
    if metadata is not None:
        message["metadata"] = metadata
    return {
        "sender": {"id": fb_page_id},
        "recipient": {"id": psid},
        "timestamp": _ms(at),
        "message": message,
    }


def referral(fb_page_id: str, psid: str, at: dt.datetime, ad_id: str) -> dict[str, Any]:
    """Khách đã có hội thoại bấm vào quảng cáo (`messaging_referrals`)."""
    return {
        "sender": {"id": psid},
        "recipient": {"id": fb_page_id},
        "timestamp": _ms(at),
        "referral": {"source": "ADS", "type": "OPEN_THREAD", "ad_id": ad_id},
    }


def leadgen(
    fb_page_id: str, leadgen_id: str, form_id: str, at: dt.datetime, *, ad_id: str | None = None
) -> dict[str, Any]:
    """Một phần tử `changes` field `leadgen`."""
    value: dict[str, Any] = {
        "leadgen_id": leadgen_id,
        "form_id": form_id,
        "page_id": fb_page_id,
        "created_time": int(at.timestamp()),
    }
    if ad_id is not None:
        value["ad_id"] = ad_id
    return {"field": "leadgen", "value": value}
