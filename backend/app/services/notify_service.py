"""Tạo nhắc việc, gửi thông báo đẩy, nhắc thủ công (Bước 5)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Perm
from app.i18n import vi
from app.models import (
    Contact,
    Lead,
    LeadEvent,
    LeadEventType,
    LeadgenSubmission,
    LeadSource,
    LeadStatus,
    Notification,
    NotificationType,
    User,
    WorkspaceMember,
)
from app.services import inbound, push
from app.services.errors import ServiceError
from app.services.reminders import LeadState, Reminder, display_name, due_reminders

if TYPE_CHECKING:
    from app.api.deps import AuthContext

CANDIDATE_WINDOW = dt.timedelta(days=8)
MANUAL_COOLDOWN_SECONDS = 600


def lead_url(lead_id: uuid.UUID) -> str:
    return f"/m/leads/{lead_id}"


async def deliver(
    db: AsyncSession, reminders: list[Reminder], now: dt.datetime, actor_id: uuid.UUID | None = None
) -> int:
    """Lưu nhắc việc (mỗi `dedupe_key` một lần) và gửi thông báo đẩy. Trả về số nhắc mới."""
    created = 0
    for r in reminders:
        workspace_id = await db.scalar(select(Lead.workspace_id).where(Lead.id == r.lead_id))
        notification_id = await db.scalar(
            pg_insert(Notification)
            .values(
                workspace_id=workspace_id,
                member_id=r.member_id,
                lead_id=r.lead_id,
                actor_member_id=actor_id,
                type=r.type,
                dedupe_key=r.dedupe_key,
                title=r.title,
                body=r.body,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["workspace_id", "dedupe_key"])
            .returning(Notification.id)
        )
        if notification_id is None:
            continue
        created += 1
        db.add(
            LeadEvent(
                workspace_id=workspace_id,
                lead_id=r.lead_id,
                type=LeadEventType.REMINDER_SENT,
                actor_member_id=actor_id,
                occurred_at=now,
                data={"type": r.type.value},
            )
        )
        delivered = await push.send_to_member(
            db,
            r.member_id,
            push.PushMessage(
                title=r.title, body=r.body, url=lead_url(r.lead_id), tag=str(r.lead_id)
            ),
        )
        if delivered:
            await db.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(sent_via="push")
            )
    await db.flush()
    return created


def _name_columns() -> tuple[object, ...]:
    form_name = (
        select(LeadgenSubmission.field_data["full_name"].astext)
        .where(LeadgenSubmission.lead_id == Lead.id)
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    return Contact.display_name, Contact.psid, form_name.label("form_name")


async def due_for_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, now: dt.datetime
) -> list[Reminder]:
    rules = await inbound.load_rules(db, workspace_id)
    local = now.astimezone(rules.tz)
    in_hours = rules.work_start <= local.time() < rules.work_end
    rows = await db.execute(
        select(Lead, *_name_columns())
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .where(
            Lead.owner_member_id.is_not(None),
            Lead.merged_into_lead_id.is_(None),
            Lead.status.not_in((LeadStatus.WON, LeadStatus.LOST)),
            or_(
                Lead.first_inbound_at >= now - CANDIDATE_WINDOW,
                Lead.callback_at.between(now - dt.timedelta(hours=48), now + dt.timedelta(hours=1)),
            ),
        )
    )
    reminders: list[Reminder] = []
    for row in rows.all():
        lead: Lead = row.Lead
        waiting = None
        if lead.source == LeadSource.MESSAGE and lead.first_reply_at is None:
            waiting = rules.business_seconds(lead.first_inbound_at, now)
        state = LeadState(
            id=lead.id,
            owner_id=lead.owner_member_id,
            name=display_name(row.display_name or row.form_name, (row.psid or lead.id.hex)[-4:]),
            source=lead.source,
            status=lead.status,
            first_inbound_at=lead.first_inbound_at,
            first_reply_at=lead.first_reply_at,
            waiting_business_seconds=waiting,
            phone_captured_at=lead.phone_captured_at,
            called_at=lead.called_at,
            result_at=lead.result_at,
            result_due_at=lead.result_due_at,
            callback_at=lead.callback_at,
        )
        callback_text = (
            lead.callback_at.astimezone(rules.tz).strftime("%H:%M") if lead.callback_at else ""
        )
        reminders.extend(
            due_reminders(state, now, in_business_hours=in_hours, callback_time_text=callback_text)
        )
    return reminders


async def remind_owner(
    db: AsyncSession, ctx: AuthContext, lead_id: uuid.UUID, *, now: dt.datetime | None = None
) -> None:
    """Trưởng nhóm / Quản lý nhắc người phụ trách khách (quyền reminder.send)."""
    from app.services.lead_service import member_ids_for

    now = now or dt.datetime.now(dt.UTC)
    allowed = await member_ids_for(db, ctx, ctx.scope(Perm.REMINDER_SEND))
    row = (
        await db.execute(
            select(Lead, *_name_columns())
            .outerjoin(Contact, Contact.id == Lead.contact_id)
            .where(Lead.id == lead_id)
        )
    ).first()
    if row is None or row.Lead.owner_member_id is None:
        raise ServiceError("lead_not_found", 404)
    lead: Lead = row.Lead
    owner_id = lead.owner_member_id
    if owner_id is None or (allowed is not None and owner_id not in allowed):
        raise ServiceError("lead_not_found", 404)
    actor = await db.scalar(
        select(User.full_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.id == ctx.member_id)
    )
    name = display_name(row.display_name or row.form_name, (row.psid or lead.id.hex)[-4:])
    window = int(now.timestamp()) // MANUAL_COOLDOWN_SECONDS
    reminder = Reminder(
        type=NotificationType.MANUAL,
        lead_id=lead.id,
        member_id=owner_id,
        dedupe_key=f"manual:{lead.id}:{window}",
        title=vi.TITLES[NotificationType.MANUAL],
        body=vi.BODIES[NotificationType.MANUAL].format(actor=actor or "", name=name),
    )
    if not await deliver(db, [reminder], now, actor_id=ctx.member_id):
        raise ServiceError("reminder_too_soon", 409)
    await db.commit()


# ---------------------------------------------------------------- hộp nhắc việc của mình


async def unread_count(db: AsyncSession, member_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(
                Notification.member_id == member_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )
