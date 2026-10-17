"""Xóa dữ liệu một khách theo yêu cầu (decisions.md mục U4, trang /data-deletion).

Chạy bằng tài khoản quản trị DB (lệnh `python -m app.cli delete-customer`), vì yêu cầu xóa đến
qua email, không gắn với workspace nào. Tìm khách theo Trang + PSID, hoặc theo số điện thoại
(mọi Trang). Xóa:

- `contacts` → `leads` → `lead_phones`, `lead_events`, `messages` (khóa ngoại CASCADE);
- `leadgen_submissions`, `notifications`, `audit_logs` (entity "lead") của các đợt khách đó;
- `webhook_events` gốc của Trang có chứa PSID (hoặc số điện thoại) của khách;
- `leadgen_submissions` chưa gắn đợt khách nào nhưng có số điện thoại đó.

Ghi một dòng `audit_logs` cho mỗi workspace, chỉ có số đếm. Không ghi PSID hay số điện thoại.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import Delete, Select, Text, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Contact,
    Lead,
    LeadEvent,
    LeadgenSubmission,
    LeadPhone,
    Message,
    Notification,
    Page,
    WebhookEvent,
)
from app.services.phone import extract_vn_phones, normalize_vn_phone


class ErasureError(Exception):
    pass


@dataclass(frozen=True)
class _Target:
    contact_id: uuid.UUID
    workspace_id: uuid.UUID
    fb_page_id: str
    psid: str


async def _targets(
    db: AsyncSession, fb_page_id: str | None, psid: str | None, phone: str | None
) -> list[_Target]:
    q = select(Contact.id, Contact.workspace_id, Page.fb_page_id, Contact.psid).join(
        Page, Page.id == Contact.page_id
    )
    if psid is not None:
        if not fb_page_id:
            raise ErasureError("Xóa theo PSID phải kèm ID Trang (--page)")
        q = q.where(Page.fb_page_id == fb_page_id, Contact.psid == psid)
    elif phone is not None:
        lead_ids = select(LeadPhone.lead_id).where(LeadPhone.phone == phone)
        contact_ids = select(Lead.contact_id).where(or_(Lead.phone == phone, Lead.id.in_(lead_ids)))
        q = q.where(Contact.id.in_(contact_ids))
        if fb_page_id:
            q = q.where(Page.fb_page_id == fb_page_id)
    rows = (await db.execute(q)).all()
    return [_Target(r[0], r[1], r[2], r[3]) for r in rows]


async def _count(db: AsyncSession, stmt: Select[int]) -> int:
    return int(await db.scalar(stmt) or 0)


async def _delete(db: AsyncSession, stmt: Delete) -> int:
    result = await db.execute(stmt)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def erase_customer(
    db: AsyncSession,
    *,
    fb_page_id: str | None = None,
    psid: str | None = None,
    phone: str | None = None,
) -> Counter[str]:
    """Xóa và trả số dòng đã xóa theo từng loại. Không tìm thấy khách thì trả Counter rỗng.

    Không tự commit: người gọi commit (để test và lệnh CLI tự quyết)."""
    if (psid is None) == (phone is None):
        raise ErasureError("Cần đúng một trong hai: --psid hoặc --phone")
    if phone is not None:
        normalized = normalize_vn_phone(phone)
        if normalized is None:
            raise ErasureError("Số điện thoại không hợp lệ")
        phone = normalized

    targets = await _targets(db, fb_page_id, psid, phone)
    counts: Counter[str] = Counter()
    contact_ids = [t.contact_id for t in targets]
    lead_ids = (
        list((await db.scalars(select(Lead.id).where(Lead.contact_id.in_(contact_ids)))).all())
        if contact_ids
        else []
    )
    lead_keys = [str(i) for i in lead_ids]

    if contact_ids:
        counts["messages"] = await _count(
            db, select(func.count()).where(Message.contact_id.in_(contact_ids))
        )
    if lead_ids:
        counts["lead_phones"] = await _count(
            db, select(func.count()).where(LeadPhone.lead_id.in_(lead_ids))
        )
        counts["lead_events"] = await _count(
            db, select(func.count()).where(LeadEvent.lead_id.in_(lead_ids))
        )
        for model, key in (
            (LeadgenSubmission, "leadgen_submissions"),
            (Notification, "notifications"),
        ):
            counts[key] += await _delete(db, delete(model).where(model.lead_id.in_(lead_ids)))
        counts["audit_logs"] = await _delete(
            db,
            delete(AuditLog).where(
                AuditLog.entity_type == "lead", AuditLog.entity_id.in_(lead_keys)
            ),
        )

    # Bản ghi webhook gốc: lọc theo Trang trước, rồi tìm PSID / số điện thoại trong payload.
    for t in targets:
        counts["webhook_events"] += await _delete(
            db,
            delete(WebhookEvent).where(
                WebhookEvent.fb_page_id == t.fb_page_id,
                func.strpos(cast(WebhookEvent.payload, Text), f'"{t.psid}"') > 0,
            ),
        )
    if phone is not None:
        # Form chưa gắn đợt khách: tìm số trong các ô của form bằng cùng cách nhận SĐT trong tin.
        orphans = (
            await db.execute(
                select(LeadgenSubmission.id, LeadgenSubmission.field_data).where(
                    LeadgenSubmission.lead_id.is_(None)
                )
            )
        ).all()
        matched = [
            sid
            for sid, data in orphans
            if phone in extract_vn_phones(json.dumps(data, ensure_ascii=False))
        ]
        if matched:
            counts["leadgen_submissions"] += await _delete(
                db, delete(LeadgenSubmission).where(LeadgenSubmission.id.in_(matched))
            )

    if contact_ids:
        counts["leads"] = len(lead_ids)
        counts["contacts"] = await _delete(db, delete(Contact).where(Contact.id.in_(contact_ids)))

    for workspace_id in sorted({t.workspace_id for t in targets}, key=str):
        db.add(
            AuditLog(
                workspace_id=workspace_id,
                actor_member_id=None,
                action="customer.erase",
                entity_type="contact",
                entity_id=None,
                after={k: v for k, v in counts.items() if v},
            )
        )
    await db.flush()
    return +counts
