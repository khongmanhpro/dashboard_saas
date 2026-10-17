"""Nghiệp vụ khi nhận sự kiện từ Trang: khách, đợt khách, tin nhắn, thời gian trả lời, leadgen.

Mọi hàm chạy trong một transaction đã đặt `app.workspace_id` (worker lo việc này) và luôn
khóa dòng `contacts` trước khi quyết định đợt, nên các sự kiện của cùng một khách xử lý tuần tự.

Thời gian trả lời được **tính lại từ dữ liệu trong DB** mỗi khi có tin mới của đợt: tin đầu
tiên là tin khách sớm nhất, trả lời là tin Trang không tự động sớm nhất sau mốc đó. Nhờ vậy
Meta gửi lặp hoặc sai thứ tự thì kết quả vẫn đúng.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import TokenDecryptError, get_token_cipher
from app.core.ids import uuid7
from app.meta.events import LeadgenEvent, MessageEvent, ReferralEvent
from app.meta.graph import GraphError, get_graph
from app.meta.leadgen import keep_needed_fields, mock_field_data
from app.models import (
    Contact,
    Lead,
    LeadEvent,
    LeadEventType,
    LeadgenFetchStatus,
    LeadgenSubmission,
    LeadPhone,
    LeadSource,
    LeadStatus,
    Message,
    MessageDirection,
    Page,
    WebhookEvent,
    WebhookEventStatus,
    Workspace,
    WorkspaceSettings,
)
from app.services.assignment import owner_at
from app.services.phone import extract_vn_phones, normalize_vn_phone
from app.services.response_time import business_seconds

log = logging.getLogger(__name__)

# Referral đến trước tin nhắn (khách bấm quảng cáo rồi mới gõ): giữ chờ tối đa chừng này.
PENDING_REFERRAL_WINDOW = dt.timedelta(hours=24)


class Outcome:
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    REFERRAL_PENDING = "referral_pending"


@dataclass(frozen=True, slots=True)
class WorkspaceRules:
    tz: ZoneInfo
    work_start: dt.time
    work_end: dt.time
    result_deadline: dt.timedelta
    session_gap: dt.timedelta
    automated_app_ids: frozenset[str]

    def business_seconds(self, start: dt.datetime, end: dt.datetime) -> int:
        return business_seconds(
            start, end, tz=self.tz, work_start=self.work_start, work_end=self.work_end
        )


async def load_rules(db: AsyncSession, workspace_id: uuid.UUID) -> WorkspaceRules:
    ws = await db.get(Workspace, workspace_id)
    settings = await db.get(WorkspaceSettings, workspace_id)
    if ws is None or settings is None:
        raise LookupError("workspace chưa có cài đặt")
    return WorkspaceRules(
        tz=ZoneInfo(ws.timezone),
        work_start=settings.work_start,
        work_end=settings.work_end,
        result_deadline=dt.timedelta(hours=settings.result_deadline_hours),
        session_gap=dt.timedelta(days=settings.lead_session_gap_days),
        automated_app_ids=get_settings().automated_app_ids,
    )


# ---------------------------------------------------------------- Graph API (cần mã Trang)


def _page_token(page: Page) -> str | None:
    if page.page_token_ciphertext is None:
        return None
    try:
        return get_token_cipher().decrypt(page.page_token_ciphertext)
    except TokenDecryptError:
        return None


async def fetch_form_fields(page: Page, leadgen_id: str) -> dict[str, str] | None:
    token = _page_token(page)
    if token is None:
        return None
    try:
        details = await get_graph().lead(leadgen_id, token)
    except GraphError:
        return None
    return keep_needed_fields(details.field_data)


async def fetch_user_name(page: Page, psid: str) -> str | None:
    """Tên thật của khách (quyết định Bước 6). Meta không cho đọc thì None ("Khách ···1234")."""
    token = _page_token(page)
    if token is None:
        return None
    try:
        return await get_graph().user_name(psid, token)
    except GraphError:
        return None


async def refresh_pending_leadgen(db: AsyncSession) -> int:
    """Lấy bù chi tiết các form đang pending (Trang đã có mã). Trả về số form lấy được."""
    done = 0
    rows = (
        await db.execute(
            select(LeadgenSubmission, Page)
            .join(Page, Page.id == LeadgenSubmission.page_id)
            .where(
                LeadgenSubmission.fetch_status == LeadgenFetchStatus.PENDING,
                Page.page_token_ciphertext.is_not(None),
            )
            .limit(200)
        )
    ).all()
    for sub, page in rows:
        fields = await fetch_form_fields(page, sub.leadgen_id)
        if fields is None:
            continue
        sub.field_data = fields
        sub.fetch_status = LeadgenFetchStatus.FETCHED
        done += 1
        lead = await db.get(Lead, sub.lead_id) if sub.lead_id else None
        phone = normalize_vn_phone(fields.get("phone_number", ""))
        if lead is not None and phone and lead.phone is None:
            lead.phone = phone
            lead.phone_source = "leadgen"
            lead.phone_captured_at = sub.created_time
            await _add_phone(db, lead, phone, "leadgen", sub.created_time)
    await db.flush()
    return done


# ---------------------------------------------------------------- khách và đợt


async def lock_contact(db: AsyncSession, page: Page, psid: str, seen_at: dt.datetime) -> Contact:
    """Tạo khách nếu chưa có, rồi khóa dòng cho tới hết transaction."""
    await db.execute(
        pg_insert(Contact)
        .values(
            id=uuid7(),
            workspace_id=page.workspace_id,
            page_id=page.id,
            psid=psid,
            first_seen_at=seen_at,
        )
        .on_conflict_do_nothing(index_elements=["page_id", "psid"])
    )
    contact = (
        await db.execute(
            select(Contact)
            .where(Contact.page_id == page.id, Contact.psid == psid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if seen_at < contact.first_seen_at:
        contact.first_seen_at = seen_at
    return contact


async def _latest_lead(
    db: AsyncSession, contact_id: uuid.UUID, *, started_by: dt.datetime | None = None
) -> Lead | None:
    query = select(Lead).where(Lead.contact_id == contact_id)
    if started_by is not None:
        query = query.where(Lead.first_inbound_at <= started_by)
    return await db.scalar(query.order_by(Lead.episode_no.desc()).limit(1))


def _add_event(
    db: AsyncSession, lead: Lead, type_: LeadEventType, at: dt.datetime, data: dict[str, Any]
) -> None:
    db.add(
        LeadEvent(
            workspace_id=lead.workspace_id, lead_id=lead.id, type=type_, occurred_at=at, data=data
        )
    )


def _apply_referral(lead: Lead, referral: dict[str, Any] | None) -> None:
    if not referral or lead.fb_ad_id is not None:
        return
    lead.referral = referral
    ad_id = referral.get("ad_id")
    lead.fb_ad_id = str(ad_id) if ad_id else None


async def _claim_pending_referral(
    db: AsyncSession, page: Page, psid: str, before: dt.datetime
) -> dict[str, Any] | None:
    """Referral của khách này đến ngay trước tin nhắn mở đợt (chưa gắn được vào đợt nào)."""
    row = await db.scalar(
        select(WebhookEvent)
        .where(
            WebhookEvent.fb_page_id == page.fb_page_id,
            WebhookEvent.kind == "referral",
            WebhookEvent.status == WebhookEventStatus.IGNORED,
            WebhookEvent.dedupe_key.startswith(f"ref:{psid}:", autoescape=True),
        )
        .order_by(WebhookEvent.id.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None:
        return None
    occurred_ms = int(row.dedupe_key.rsplit(":", 1)[1])
    occurred = dt.datetime.fromtimestamp(occurred_ms / 1000, tz=dt.UTC)
    if not (before - PENDING_REFERRAL_WINDOW <= occurred <= before):
        return None
    row.status = WebhookEventStatus.PROCESSED
    referral = row.payload.get("referral")
    return referral if isinstance(referral, dict) else None


async def _lead_for_inbound(
    db: AsyncSession, page: Page, contact: Contact, ev: MessageEvent, rules: WorkspaceRules
) -> Lead:
    latest = await _latest_lead(db, contact.id)
    if latest is not None:
        last = latest.last_inbound_at or latest.first_inbound_at
        if ev.sent_at - last <= rules.session_gap:
            return latest

    owner = await owner_at(db, page.id, ev.sent_at)
    lead = Lead(
        id=uuid7(),
        workspace_id=page.workspace_id,
        page_id=page.id,
        contact_id=contact.id,
        episode_no=(latest.episode_no + 1) if latest else 1,
        owner_member_id=owner,
        source=LeadSource.MESSAGE,
        first_inbound_at=ev.sent_at,
        first_inbound_mid=ev.mid,
        last_inbound_at=ev.sent_at,
        status=LeadStatus.NEW,
        result_due_at=ev.sent_at + rules.result_deadline,
    )
    _apply_referral(
        lead, ev.referral or await _claim_pending_referral(db, page, ev.psid, ev.sent_at)
    )
    db.add(lead)
    await db.flush()

    # Echo đến trước tin mở đợt (Meta gửi sai thứ tự) thì chuyển sang đợt mới.
    unattached: ColumnElement[bool] = Message.lead_id.is_(None)
    if latest is not None:
        unattached = or_(unattached, Message.lead_id == latest.id)
    await db.execute(
        update(Message)
        .where(
            Message.contact_id == contact.id,
            Message.direction == MessageDirection.OUT,
            Message.sent_at >= ev.sent_at,
            unattached,
        )
        .values(lead_id=lead.id)
    )
    _add_event(
        db,
        lead,
        LeadEventType.CREATED,
        ev.sent_at,
        {
            "source": LeadSource.MESSAGE.value,
            "episode_no": lead.episode_no,
            "owner_member_id": str(owner) if owner else None,
        },
    )
    return lead


async def refresh_response(db: AsyncSession, lead: Lead, rules: WorkspaceRules) -> None:
    """Tính lại tin đầu tiên, trả lời đầu tiên và số giây trả lời trong giờ làm việc."""
    if lead.source != LeadSource.MESSAGE:
        return
    first = (
        await db.execute(
            select(Message.sent_at, Message.mid)
            .where(Message.lead_id == lead.id, Message.direction == MessageDirection.IN)
            .order_by(Message.sent_at, Message.id)
            .limit(1)
        )
    ).first()
    if first is not None and first.sent_at < lead.first_inbound_at:
        lead.first_inbound_at = first.sent_at
        lead.first_inbound_mid = first.mid
        lead.result_due_at = first.sent_at + rules.result_deadline

    reply = (
        await db.execute(
            select(Message.sent_at, Message.mid)
            .where(
                Message.lead_id == lead.id,
                Message.direction == MessageDirection.OUT,
                Message.is_automated.is_(False),
                Message.sent_at >= lead.first_inbound_at,
            )
            .order_by(Message.sent_at, Message.id)
            .limit(1)
        )
    ).first()
    if reply is None:
        return
    seconds = rules.business_seconds(lead.first_inbound_at, reply.sent_at)
    if lead.first_reply_mid == reply.mid and lead.response_business_seconds == seconds:
        return
    first_time = lead.first_reply_at is None
    lead.first_reply_at = reply.sent_at
    lead.first_reply_mid = reply.mid
    lead.response_business_seconds = seconds
    if not first_time:
        return
    _add_event(
        db, lead, LeadEventType.REPLIED, reply.sent_at, {"response_business_seconds": seconds}
    )
    if lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.CONTACTED
        lead.status_changed_at = reply.sent_at
        _add_event(
            db,
            lead,
            LeadEventType.STATUS_CHANGED,
            reply.sent_at,
            {"from": LeadStatus.NEW.value, "to": LeadStatus.CONTACTED.value, "auto": True},
        )


# ---------------------------------------------------------------- SĐT và gộp khách form


async def _lock_phone(db: AsyncSession, page: Page, phone: str) -> None:
    """Khóa theo (Trang, SĐT) tới hết transaction: tin nhắn và form cùng số đến cùng lúc thì
    xử lý lần lượt, không tạo ra hai đợt không gộp được."""
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"phone:{page.id}:{phone}", 0)))
    )


async def _add_phone(
    db: AsyncSession,
    lead: Lead,
    phone: str,
    source: str,
    at: dt.datetime,
    message_id: int | None = None,
) -> bool:
    """Lưu SĐT cho đợt. False nếu đợt đã có số này."""
    inserted = await db.scalar(
        pg_insert(LeadPhone)
        .values(
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            phone=phone,
            source=source,
            message_id=message_id,
            detected_at=at,
        )
        .on_conflict_do_nothing(index_elements=["lead_id", "phone"])
        .returning(LeadPhone.id)
    )
    return inserted is not None


def _form_name(submission: LeadgenSubmission) -> str | None:
    name = submission.field_data.get("full_name")
    return str(name)[:200] if name else None


async def _absorb_submissions(
    db: AsyncSession, target: Lead, submissions: list[LeadgenSubmission]
) -> None:
    """Gắn form vào đợt nhắn tin: tên hiển thị và quảng cáo nếu đợt còn thiếu."""
    contact = await db.get(Contact, target.contact_id) if target.contact_id else None
    for sub in submissions:
        sub.lead_id = target.id
        if contact is not None and contact.display_name is None:
            contact.display_name = _form_name(sub)
        if target.fb_ad_id is None and sub.fb_ad_id:
            target.fb_ad_id = sub.fb_ad_id


async def merge_form_leads(
    db: AsyncSession, message_lead: Lead, phone: str, rules: WorkspaceRules
) -> int:
    """Gộp các đợt form cùng Trang, cùng SĐT, trong cùng đợt vào `message_lead` (quyết định #16).

    Chỉ gộp đợt form chưa ai đụng vào (Mới, chưa gọi, chưa có kết quả).
    """
    last = message_lead.last_inbound_at or message_lead.first_inbound_at
    candidates = list(
        await db.scalars(
            select(Lead)
            .where(
                Lead.page_id == message_lead.page_id,
                Lead.source == LeadSource.LEADGEN,
                Lead.merged_into_lead_id.is_(None),
                Lead.phone == phone,
                Lead.status == LeadStatus.NEW,
                Lead.called_at.is_(None),
                Lead.result_at.is_(None),
                Lead.first_inbound_at >= message_lead.first_inbound_at - rules.session_gap,
                Lead.first_inbound_at <= last + rules.session_gap,
            )
            .with_for_update()
        )
    )
    for form_lead in candidates:
        form_lead.merged_into_lead_id = message_lead.id
        submissions = list(
            await db.scalars(
                select(LeadgenSubmission).where(LeadgenSubmission.lead_id == form_lead.id)
            )
        )
        await _absorb_submissions(db, message_lead, submissions)
        await _add_phone(db, message_lead, phone, "leadgen", form_lead.first_inbound_at)
        now = dt.datetime.now(dt.UTC)
        _add_event(db, message_lead, LeadEventType.MERGED, now, {"from_lead_id": str(form_lead.id)})
        _add_event(db, form_lead, LeadEventType.MERGED, now, {"into_lead_id": str(message_lead.id)})
    return len(candidates)


async def _record_message_phones(
    db: AsyncSession, page: Page, lead: Lead, message: Message, rules: WorkspaceRules
) -> None:
    for phone in extract_vn_phones(message.text):
        await _lock_phone(db, page, phone)
        if not await _add_phone(db, lead, phone, "message", message.sent_at, message.id):
            continue
        if lead.phone is None:
            lead.phone = phone
            lead.phone_source = "message"
            lead.phone_captured_at = message.sent_at
            # Không ghi SĐT vào lịch sử: hồ sơ khách đã có, lịch sử chỉ cần mốc thời gian.
            _add_event(
                db, lead, LeadEventType.PHONE_DETECTED, message.sent_at, {"source": "message"}
            )
        await merge_form_leads(db, lead, phone, rules)


async def _message_lead_with_phone(
    db: AsyncSession, page: Page, phone: str, at: dt.datetime, rules: WorkspaceRules
) -> Lead | None:
    """Đợt nhắn tin đang mở của khách có SĐT này, quanh thời điểm `at`."""
    last = func.coalesce(Lead.last_inbound_at, Lead.first_inbound_at)
    return await db.scalar(
        select(Lead)
        .join(LeadPhone, LeadPhone.lead_id == Lead.id)
        .where(
            Lead.page_id == page.id,
            Lead.source == LeadSource.MESSAGE,
            Lead.merged_into_lead_id.is_(None),
            LeadPhone.phone == phone,
            Lead.first_inbound_at <= at + rules.session_gap,
            last >= at - rules.session_gap,
        )
        .order_by(Lead.first_inbound_at.desc())
        .limit(1)
        .with_for_update(of=Lead)
    )


# ---------------------------------------------------------------- từng loại sự kiện


async def handle_message(
    db: AsyncSession, page: Page, rules: WorkspaceRules, ev: MessageEvent
) -> str:
    contact = await lock_contact(db, page, ev.psid, ev.sent_at)
    if await db.scalar(select(Message.id).where(Message.mid == ev.mid)) is not None:
        return Outcome.DUPLICATE
    if ev.kind == "in" and contact.display_name is None:
        contact.display_name = await fetch_user_name(page, ev.psid)

    lead: Lead | None
    if ev.kind == "in":
        lead = await _lead_for_inbound(db, page, contact, ev, rules)
        _apply_referral(lead, ev.referral)
        if contact.last_inbound_at is None or ev.sent_at > contact.last_inbound_at:
            contact.last_inbound_at = ev.sent_at
        if lead.last_inbound_at is None or ev.sent_at > lead.last_inbound_at:
            lead.last_inbound_at = ev.sent_at
        automated = False
    else:
        lead = await _latest_lead(db, contact.id, started_by=ev.sent_at)
        automated = ev.app_id is not None and ev.app_id in rules.automated_app_ids
        # Để sếp biết app_id nào là tin tự động mà điền META_AUTOMATED_APP_IDS.
        log.info("echo", extra={"ctx": {"app_id": ev.app_id or "none", "automated": automated}})

    message = Message(
        workspace_id=page.workspace_id,
        page_id=page.id,
        contact_id=contact.id,
        lead_id=lead.id if lead else None,
        mid=ev.mid,
        direction=MessageDirection.IN if ev.kind == "in" else MessageDirection.OUT,
        is_echo=ev.kind == "echo",
        app_id=ev.app_id,
        is_automated=automated,
        sent_at=ev.sent_at,
        text=ev.text,
        has_attachments=ev.has_attachments,
        meta={"metadata": ev.metadata} if ev.metadata else None,
    )
    db.add(message)
    await db.flush()
    if lead is not None and ev.kind == "in":
        await _record_message_phones(db, page, lead, message, rules)
    if lead is not None:
        await refresh_response(db, lead, rules)
    return Outcome.PROCESSED


async def handle_referral(
    db: AsyncSession, page: Page, rules: WorkspaceRules, ev: ReferralEvent
) -> str:
    contact = await lock_contact(db, page, ev.psid, ev.occurred_at)
    lead = await _latest_lead(db, contact.id, started_by=ev.occurred_at)
    if lead is not None:
        last = lead.last_inbound_at or lead.first_inbound_at
        if ev.occurred_at - last <= rules.session_gap:
            _apply_referral(lead, ev.referral)
            return Outcome.PROCESSED
    # Chưa có đợt phù hợp: tin nhắn tới sau sẽ nhận referral này (_claim_pending_referral).
    return Outcome.REFERRAL_PENDING


async def handle_leadgen(
    db: AsyncSession, page: Page, rules: WorkspaceRules, ev: LeadgenEvent
) -> str:
    exists = await db.scalar(
        select(LeadgenSubmission.id).where(LeadgenSubmission.leadgen_id == ev.leadgen_id)
    )
    if exists is not None:
        return Outcome.DUPLICATE

    # Có mã Trang (Bước 6) thì lấy chi tiết form qua Graph API; MOCK_MODE không có mã thì đọc
    # fixture; còn lại để pending, job kiểm tra BM sẽ lấy bù.
    field_data = await fetch_form_fields(page, ev.leadgen_id)
    if field_data is None and get_settings().mock_mode:
        field_data = mock_field_data(ev.form_id)
    fetch_status = (
        LeadgenFetchStatus.FETCHED if field_data is not None else LeadgenFetchStatus.PENDING
    )
    field_data = field_data or {}
    phone = normalize_vn_phone(field_data.get("phone_number", ""))

    submission = LeadgenSubmission(
        workspace_id=page.workspace_id,
        leadgen_id=ev.leadgen_id,
        page_id=page.id,
        form_id=ev.form_id,
        fb_ad_id=ev.fb_ad_id,
        created_time=ev.created_time,
        field_data=field_data,
        fetch_status=fetch_status,
    )
    if phone:
        await _lock_phone(db, page, phone)
        target = await _message_lead_with_phone(db, page, phone, ev.created_time, rules)
        if target is not None:
            # Khách đã nhắn tin và để lại số này: gắn form vào đợt đó, không mở đợt mới.
            db.add(submission)
            await db.flush()
            await _absorb_submissions(db, target, [submission])
            await _add_phone(db, target, phone, "leadgen", ev.created_time)
            _add_event(
                db, target, LeadEventType.MERGED, ev.created_time, {"leadgen_id": ev.leadgen_id}
            )
            await db.flush()
            return Outcome.PROCESSED

    owner = await owner_at(db, page.id, ev.created_time)
    lead = Lead(
        id=uuid7(),
        workspace_id=page.workspace_id,
        page_id=page.id,
        contact_id=None,
        episode_no=1,
        owner_member_id=owner,
        source=LeadSource.LEADGEN,
        fb_ad_id=ev.fb_ad_id,
        first_inbound_at=ev.created_time,
        status=LeadStatus.NEW,
        result_due_at=ev.created_time + rules.result_deadline,
        phone=phone,
        phone_source="leadgen" if phone else None,
        phone_captured_at=ev.created_time if phone else None,
    )
    db.add(lead)
    await db.flush()
    submission.lead_id = lead.id
    db.add(submission)
    if phone:
        await _add_phone(db, lead, phone, "leadgen", ev.created_time)
    _add_event(
        db,
        lead,
        LeadEventType.CREATED,
        ev.created_time,
        {"source": LeadSource.LEADGEN.value, "owner_member_id": str(owner) if owner else None},
    )
    await db.flush()
    return Outcome.PROCESSED
