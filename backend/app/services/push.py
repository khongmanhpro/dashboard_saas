"""Gửi thông báo đẩy (Web Push, VAPID) tới các máy đã đăng ký của một người.

pywebpush gọi HTTP đồng bộ nên chạy trong thread. Nội dung chỉ có tiêu đề, câu nhắc và đường dẫn
mở app, không có SĐT hay nội dung tin nhắn. Máy trả 404/410 (đã hủy đăng ký) thì xóa đăng ký.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PushSubscription

log = logging.getLogger(__name__)

GONE_STATUSES = {404, 410}
MAX_FAILURES = 5
TTL_SECONDS = 6 * 3600


def push_configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key.get_secret_value())


def _vapid_subject() -> str:
    base = get_settings().app_base_url
    # Dịch vụ đẩy cần một liên hệ: https URL của app hoặc mailto.
    return base if base.startswith("https://") else "mailto:noreply@example.com"


def _send_one(sub: PushSubscription, data: str) -> int | None:
    """Trả về None nếu gửi được, hoặc mã HTTP lỗi (0 nếu lỗi mạng)."""
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=data,
            vapid_private_key=get_settings().vapid_private_key.get_secret_value(),
            vapid_claims={"sub": _vapid_subject()},
            ttl=TTL_SECONDS,
            timeout=10,
        )
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        return int(getattr(response, "status_code", 0) or 0)
    except Exception:
        return 0
    return None


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    url: str
    tag: str

    def json(self) -> str:
        payload: dict[str, Any] = {
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "tag": self.tag,
        }
        return json.dumps(payload, ensure_ascii=False)


async def send_to_member(db: AsyncSession, member_id: uuid.UUID, message: PushMessage) -> int:
    """Gửi tới mọi máy của một người. Trả về số máy nhận được."""
    if not push_configured():
        return 0
    subs = list(
        await db.scalars(select(PushSubscription).where(PushSubscription.member_id == member_id))
    )
    delivered = 0
    data = message.json()
    for sub in subs:
        status = await asyncio.to_thread(_send_one, sub, data)
        if status is None:
            delivered += 1
            sub.last_success_at = dt.datetime.now(dt.UTC)
            sub.failure_count = 0
        elif status in GONE_STATUSES:
            await db.delete(sub)
        else:
            sub.failure_count += 1
            if sub.failure_count >= MAX_FAILURES:
                await db.delete(sub)
            log.warning("gửi thông báo đẩy lỗi", extra={"ctx": {"status": status}})
    await db.flush()
    return delivered
