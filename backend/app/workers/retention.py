"""Job arq chạy mỗi đêm: thực hiện hạn lưu dữ liệu (quyết định #19, data-model.md).

- Xóa dòng `webhook_events` nhận cách đây hơn 30 ngày.
- Xóa nội dung (`messages.text = NULL`) của tin gửi cách đây hơn 180 ngày; dòng và số liệu giữ lại.

Job chạy bằng tài khoản ứng dụng (bị RLS) và xuyên mọi workspace, nên gọi hàm
`app_purge_expired_data` (SECURITY DEFINER, migration 0003). Hàm từ chối ngưỡng dưới 30 / 180 ngày.
Log chỉ ghi số đếm.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.core.db import app_sessionmaker

WEBHOOK_EVENTS_RETENTION_DAYS = 30
MESSAGE_TEXT_RETENTION_DAYS = 180

log = logging.getLogger(__name__)


async def purge_expired_data(ctx: dict[str, Any]) -> dict[str, int]:
    async with app_sessionmaker()() as db:
        row = (
            await db.execute(
                text(
                    "SELECT webhook_events_deleted, message_texts_cleared"
                    " FROM app_purge_expired_data(:webhook_days, :message_text_days)"
                ),
                {
                    "webhook_days": WEBHOOK_EVENTS_RETENTION_DAYS,
                    "message_text_days": MESSAGE_TEXT_RETENTION_DAYS,
                },
            )
        ).one()
        await db.commit()
    counts = {"webhook_events_deleted": int(row[0]), "message_texts_cleared": int(row[1])}
    log.info(
        "hạn lưu: xóa %d webhook_events, xóa nội dung %d tin nhắn",
        counts["webhook_events_deleted"],
        counts["message_texts_cleared"],
    )
    return counts
