"""Khách mẫu 30 ngày cho máy dev (Bước 7), để Tổng quan, Fanpage, Quảng cáo có số liệu.

Chỉ chạy trong MOCK_MODE, qua `make seed`. Tên khách dạng `[Khách 1042]`, SĐT dạng `0900xxxxxx`
(rõ là số giả). Sinh cố định theo seed của bộ số ngẫu nhiên; chạy lại không tạo trùng.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.models import (
    Contact,
    Lead,
    LeadSource,
    LeadStatus,
    LostReason,
    Message,
    MessageDirection,
    Page,
    WorkspaceMember,
)

DAYS = 30
PSID_PREFIX = "seedhist"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
# Tên Trang → (khách mỗi ngày, phút trả lời nhỏ nhất–lớn nhất, quảng cáo, tỉ lệ khách từ QC).
PROFILES: dict[str, tuple[tuple[int, int], tuple[int, int], tuple[str, ...], float]] = {
    "Phần Mềm Giá Rẻ": ((3, 6), (2, 15), ("23800000000000111", "23800000000000112"), 0.5),
    "FISS": ((2, 5), (4, 45), ("23800000000000101", "23800000000000102"), 0.6),
    "Shop Thỏ": ((2, 4), (15, 95), ("23800000000000151",), 0.4),
    "Mua Sắm Thông Minh": ((1, 2), (5, 30), ("23800000000000141",), 0.3),
}
LOST = list(LostReason)


async def seed_history(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    pages: dict[str, Page],
    owners: dict[str, WorkspaceMember | None],
    now: dt.datetime,
) -> int:
    """Tạo khách mẫu nếu chưa có. Trả số khách đã tạo."""
    exists = await db.scalar(
        select(Contact.id).where(
            Contact.workspace_id == workspace_id, Contact.psid.startswith(PSID_PREFIX)
        )
    )
    if exists is not None:
        return 0
    rng = random.Random(20261017)  # noqa: S311 — dữ liệu giả, không dùng cho bảo mật
    created = 0
    today = now.astimezone(TZ).date()
    for name, (per_day, reply, ads, ad_share) in PROFILES.items():
        page = pages.get(name)
        if page is None:
            continue
        owner = owners.get(name)
        for back in range(DAYS, 0, -1):
            day = today - dt.timedelta(days=back)
            for _ in range(rng.randint(*per_day)):
                created += 1
                ref = 1000 + created
                at = dt.datetime.combine(
                    day, dt.time(rng.randint(8, 19), rng.randint(0, 59)), TZ
                ).astimezone(dt.UTC)
                contact = Contact(
                    id=uuid7(),
                    workspace_id=workspace_id,
                    page_id=page.id,
                    psid=f"{PSID_PREFIX}{ref}",
                    display_name=f"[Khách {ref}]",
                    first_seen_at=at,
                    last_inbound_at=at,
                )
                db.add(contact)
                replied = rng.random() > 0.04
                seconds = rng.randint(reply[0] * 60, reply[1] * 60) if replied else None
                has_phone = rng.random() < 0.62
                roll = rng.random()
                status = LeadStatus.CONTACTED if replied else LeadStatus.NEW
                result_at = None
                if replied and roll < 0.28:
                    status = LeadStatus.WON
                elif replied and roll < 0.70:
                    status = LeadStatus.LOST
                elif replied and roll < 0.85:
                    status = LeadStatus.CALLBACK
                if status in (LeadStatus.WON, LeadStatus.LOST, LeadStatus.CALLBACK):
                    late = rng.random() < 0.1
                    result_at = at + dt.timedelta(
                        hours=rng.randint(50, 70) if late else rng.randint(1, 40)
                    )
                lead = Lead(
                    id=uuid7(),
                    workspace_id=workspace_id,
                    page_id=page.id,
                    contact_id=contact.id,
                    episode_no=1,
                    owner_member_id=owner.id if owner else None,
                    source=LeadSource.MESSAGE,
                    fb_ad_id=rng.choice(ads) if rng.random() < ad_share else None,
                    first_inbound_at=at,
                    first_inbound_mid=f"m-{PSID_PREFIX}-{ref}",
                    first_reply_at=at + dt.timedelta(seconds=seconds) if seconds else None,
                    first_reply_mid=f"m-{PSID_PREFIX}-{ref}-r" if seconds else None,
                    response_business_seconds=seconds,
                    status=status,
                    status_changed_at=result_at,
                    callback_at=result_at + dt.timedelta(days=1)
                    if status == LeadStatus.CALLBACK and result_at
                    else None,
                    won_value_vnd=rng.randint(5, 50) * 100_000
                    if status == LeadStatus.WON
                    else None,
                    lost_reason=rng.choice(LOST) if status == LeadStatus.LOST else None,
                    lost_note="[Ghi chú mẫu]"
                    if status == LeadStatus.LOST and rng.random() < 0.3
                    else None,
                    called_at=at + dt.timedelta(hours=1)
                    if has_phone and status != LeadStatus.NEW and rng.random() < 0.9
                    else None,
                    phone=f"0900{rng.randint(0, 999_999):06d}" if has_phone else None,
                    phone_source="message" if has_phone else None,
                    phone_captured_at=at if has_phone else None,
                    result_due_at=at + dt.timedelta(hours=48),
                    result_at=result_at,
                    last_inbound_at=at,
                )
                if lead.status == LeadStatus.LOST and lead.lost_reason == LostReason.OTHER:
                    lead.lost_note = "[Ghi chú mẫu]"
                db.add(lead)
                db.add(
                    Message(
                        workspace_id=workspace_id,
                        page_id=page.id,
                        contact_id=contact.id,
                        lead_id=lead.id,
                        mid=lead.first_inbound_mid,
                        direction=MessageDirection.IN,
                        is_echo=False,
                        is_automated=False,
                        sent_at=at,
                        text="[Tin nhắn mẫu của khách]",
                        has_attachments=False,
                    )
                )
                if seconds and lead.first_reply_mid and lead.first_reply_at:
                    db.add(
                        Message(
                            workspace_id=workspace_id,
                            page_id=page.id,
                            contact_id=contact.id,
                            lead_id=lead.id,
                            mid=lead.first_reply_mid,
                            direction=MessageDirection.OUT,
                            is_echo=True,
                            is_automated=False,
                            sent_at=lead.first_reply_at,
                            text="[Tin trả lời mẫu]",
                            has_attachments=False,
                        )
                    )
    await db.flush()
    return created
