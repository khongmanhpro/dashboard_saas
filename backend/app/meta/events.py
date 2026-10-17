"""Đọc payload webhook của Meta (object `page`) thành các sự kiện có kiểu.

Hàm thuần, không chạm DB: dễ test bằng fixture. Mỗi phần tử `messaging` hoặc `changes` thành
một sự kiện; loại không dùng (đã xem, đã nhận, bài viết…) thành `IgnoredEvent`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WebhookPayload:
    """Payload đưa vào hàng đợi. `repr` không lộ nội dung vì arq ghi tham số job vào log."""

    data: dict[str, Any] = field(repr=False)

    def __repr__(self) -> str:
        entries = self.data.get("entry")
        return f"<WebhookPayload entries={len(entries) if isinstance(entries, list) else 0}>"


@dataclass(frozen=True, slots=True)
class MessageEvent:
    """Tin khách gửi Trang (`kind="in"`) hoặc Trang gửi khách (`kind="echo"`)."""

    kind: str
    fb_page_id: str
    psid: str
    mid: str
    sent_at: dt.datetime
    text: str | None
    has_attachments: bool
    app_id: str | None
    metadata: str | None
    referral: dict[str, Any] | None
    raw: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return f"mid:{self.mid}"


@dataclass(frozen=True, slots=True)
class ReferralEvent:
    """Khách đã có hội thoại bấm lại vào quảng cáo (`messaging_referrals`)."""

    fb_page_id: str
    psid: str
    occurred_at: dt.datetime
    referral: dict[str, Any]
    raw: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return f"ref:{self.psid}:{int(self.occurred_at.timestamp() * 1000)}"


@dataclass(frozen=True, slots=True)
class LeadgenEvent:
    fb_page_id: str
    leadgen_id: str
    form_id: str | None
    fb_ad_id: str | None
    created_time: dt.datetime
    raw: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return f"leadgen:{self.leadgen_id}"


@dataclass(frozen=True, slots=True)
class IgnoredEvent:
    fb_page_id: str
    kind: str


Event = MessageEvent | ReferralEvent | LeadgenEvent | IgnoredEvent


def _from_ms(value: Any) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value) / 1000, tz=dt.UTC)


def _from_seconds(value: Any) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value), tz=dt.UTC)


def _str_or_none(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _messaging(fb_page_id: str, item: dict[str, Any]) -> Event:
    sender = str((item.get("sender") or {}).get("id") or "")
    recipient = str((item.get("recipient") or {}).get("id") or "")
    timestamp = item.get("timestamp")
    message = item.get("message")

    if isinstance(message, dict) and message.get("mid") and timestamp is not None:
        is_echo = bool(message.get("is_echo"))
        # Echo: người gửi là Trang, người nhận là khách. Tin thường thì ngược lại.
        psid = recipient if is_echo else sender
        if not psid or psid == fb_page_id:
            return IgnoredEvent(fb_page_id, "message_without_psid")
        # Khách nhắn lần đầu từ quảng cáo: referral nằm trong message hoặc cạnh message.
        referral = message.get("referral") or item.get("referral")
        return MessageEvent(
            kind="echo" if is_echo else "in",
            fb_page_id=fb_page_id,
            psid=psid,
            mid=str(message["mid"]),
            sent_at=_from_ms(timestamp),
            text=_str_or_none(message.get("text")),
            has_attachments=bool(message.get("attachments")),
            app_id=_str_or_none(message.get("app_id")),
            metadata=_str_or_none(message.get("metadata")),
            referral=referral if isinstance(referral, dict) else None,
            raw=item,
        )
    referral = item.get("referral")
    if isinstance(referral, dict) and sender and timestamp is not None:
        return ReferralEvent(fb_page_id, sender, _from_ms(timestamp), referral, item)
    for kind in ("delivery", "read", "postback", "reaction", "optin"):
        if kind in item:
            return IgnoredEvent(fb_page_id, kind)
    return IgnoredEvent(fb_page_id, "unknown_messaging")


def _change(fb_page_id: str, change: dict[str, Any]) -> Event:
    field_name = str(change.get("field") or "unknown")
    value = change.get("value")
    if field_name == "leadgen" and isinstance(value, dict) and value.get("leadgen_id"):
        created = value.get("created_time")
        return LeadgenEvent(
            fb_page_id=str(value.get("page_id") or fb_page_id),
            leadgen_id=str(value["leadgen_id"]),
            form_id=_str_or_none(value.get("form_id")),
            fb_ad_id=_str_or_none(value.get("ad_id")),
            created_time=_from_seconds(created) if created is not None else dt.datetime.now(dt.UTC),
            raw=value,
        )
    # `feed` (bài đăng) dùng ở Bước 7.
    return IgnoredEvent(fb_page_id, field_name)


def parse_payload(payload: dict[str, Any]) -> list[Event]:
    if payload.get("object") != "page":
        return []
    events: list[Event] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        fb_page_id = str(entry["id"])
        for item in entry.get("messaging") or []:
            if isinstance(item, dict):
                events.append(_messaging(fb_page_id, item))
        for change in entry.get("changes") or []:
            if isinstance(change, dict):
                events.append(_change(fb_page_id, change))
        # `standby` (khi Trang bật chuyển giao hội thoại) chưa hỗ trợ: bỏ qua.
    return events
