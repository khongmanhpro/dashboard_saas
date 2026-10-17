"""Đọc và cập nhật khách (đợt khách) theo phân quyền.

- Phạm vi xem (`lead.view`) áp ngay trong câu truy vấn: toàn workspace / nhóm / của mình.
- SĐT (cả `leads.phone` lẫn số trong nội dung tin) bị che nếu người xem không có
  `lead.phone.view` với người phụ trách khách đó.
- Đợt form đã gộp (`merged_into_lead_id`) không hiện trong danh sách.
"""

from __future__ import annotations

import base64
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Select, and_, exists, false, func, or_, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Perm, Scope
from app.models import (
    Campaign,
    Contact,
    Lead,
    LeadEvent,
    LeadEventType,
    LeadgenSubmission,
    LeadPhone,
    LeadSource,
    LeadStatus,
    Message,
    MessageDirection,
    Page,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)
from app.schemas.leads import (
    FilterOptions,
    LeadCard,
    LeadDetail,
    LeadPage,
    LeadPermissions,
    LeadSummary,
    NamedRef,
    ResultUpdate,
    TimelineItem,
)
from app.services import ads_service, audit
from app.services.errors import ServiceError
from app.services.member_service import visible_team_ids
from app.services.phone import mask_phone, mask_phones_in_text
from app.services.response_time import business_seconds

if TYPE_CHECKING:
    from app.api.deps import AuthContext

Period = Literal["today", "7d", "30d", "all"]
Chip = Literal["unreplied", "overdue", "phone_not_called", "new_today"]
SourceFilter = Literal["ad", "organic", "form"]

TIMELINE_LIMIT = 200
RESULT_EDIT_WINDOW = dt.timedelta(days=7)
_FINAL = (LeadStatus.WON, LeadStatus.LOST)


# ---------------------------------------------------------------- phạm vi


async def member_ids_for(
    db: AsyncSession, ctx: AuthContext, scope: Scope | None
) -> set[uuid.UUID] | None:
    """None = mọi người (ALL). Tập rỗng = không ai."""
    if scope == Scope.ALL:
        return None
    if scope == Scope.TEAM:
        teams = await visible_team_ids(db, ctx)
        ids = set(
            (
                await db.scalars(
                    select(WorkspaceMember.id).where(WorkspaceMember.team_id.in_(teams))
                )
            ).all()
        )
        return ids | {ctx.member_id}
    if scope == Scope.OWN:
        return {ctx.member_id}
    return set()


@dataclass(frozen=True)
class LeadAccess:
    view_owner_ids: set[uuid.UUID] | None
    phone_owner_ids: set[uuid.UUID] | None
    can_search_phone: bool

    def view_condition(self) -> ColumnElement[bool]:
        if self.view_owner_ids is None:
            return true()
        if not self.view_owner_ids:
            return false()
        return Lead.owner_member_id.in_(self.view_owner_ids)

    def can_see_phone(self, owner_id: uuid.UUID | None) -> bool:
        if self.phone_owner_ids is None:
            return True
        return owner_id is not None and owner_id in self.phone_owner_ids


async def lead_access(db: AsyncSession, ctx: AuthContext) -> LeadAccess:
    return LeadAccess(
        view_owner_ids=await member_ids_for(db, ctx, ctx.scope(Perm.LEAD_VIEW)),
        phone_owner_ids=await member_ids_for(db, ctx, ctx.scope(Perm.LEAD_PHONE_VIEW)),
        can_search_phone=ctx.can(Perm.LEAD_PHONE_VIEW),
    )


# ---------------------------------------------------------------- quy tắc workspace


@dataclass(frozen=True)
class Rules:
    tz: ZoneInfo
    work_start: dt.time
    work_end: dt.time
    slow_reply_seconds: int
    slow_reply_minutes: int

    def business_seconds(self, start: dt.datetime, end: dt.datetime) -> int:
        return business_seconds(
            start, end, tz=self.tz, work_start=self.work_start, work_end=self.work_end
        )

    def start_of_today(self, now: dt.datetime) -> dt.datetime:
        local = now.astimezone(self.tz)
        return dt.datetime.combine(local.date(), dt.time(0), tzinfo=self.tz)


async def _rules(db: AsyncSession, workspace_id: uuid.UUID) -> Rules:
    ws = await db.get(Workspace, workspace_id)
    settings = await db.get(WorkspaceSettings, workspace_id)
    if ws is None or settings is None:
        raise ServiceError("workspace_not_found", 404)
    return Rules(
        tz=ZoneInfo(ws.timezone),
        work_start=settings.work_start,
        work_end=settings.work_end,
        slow_reply_seconds=settings.slow_reply_minutes * 60,
        slow_reply_minutes=settings.slow_reply_minutes,
    )


# ---------------------------------------------------------------- truy vấn


def _overdue(now: dt.datetime) -> ColumnElement[bool]:
    return and_(Lead.result_at.is_(None), Lead.result_due_at < now)


def _chip_condition(chip: Chip, now: dt.datetime, rules: Rules) -> ColumnElement[bool]:
    if chip == "unreplied":
        return and_(
            Lead.source == LeadSource.MESSAGE,
            Lead.first_reply_at.is_(None),
            Lead.status == LeadStatus.NEW,
        )
    if chip == "overdue":
        return _overdue(now)
    if chip == "phone_not_called":
        return and_(Lead.phone.is_not(None), Lead.called_at.is_(None), Lead.status.not_in(_FINAL))
    return Lead.first_inbound_at >= rules.start_of_today(now)


def _period_start(period: Period, now: dt.datetime, rules: Rules) -> dt.datetime | None:
    if period == "today":
        return rules.start_of_today(now)
    if period == "7d":
        return now - dt.timedelta(days=7)
    if period == "30d":
        return now - dt.timedelta(days=30)
    return None


_form_name = (
    select(LeadgenSubmission.field_data["full_name"].astext)
    .where(LeadgenSubmission.lead_id == Lead.id)
    .order_by(LeadgenSubmission.created_time)
    .limit(1)
    .correlate(Lead)
    .scalar_subquery()
)
_form_ref = (
    select(LeadgenSubmission.leadgen_id)
    .where(LeadgenSubmission.lead_id == Lead.id)
    .order_by(LeadgenSubmission.created_time)
    .limit(1)
    .correlate(Lead)
    .scalar_subquery()
)


def _base_select() -> Select[Any]:
    return (
        select(
            Lead,
            Contact.display_name,
            Contact.psid,
            _form_name.label("form_name"),
            _form_ref.label("form_ref"),
            Page.name.label("page_name"),
            Page.fb_page_id,
            User.full_name.label("owner_name"),
        )
        .join(Page, Page.id == Lead.page_id)
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .outerjoin(WorkspaceMember, WorkspaceMember.id == Lead.owner_member_id)
        .outerjoin(User, User.id == WorkspaceMember.user_id)
    )


@dataclass
class LeadFilters:
    period: Period = "7d"
    chip: Chip | None = None
    status: LeadStatus | None = None
    page_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    source: SourceFilter | None = None
    q: str | None = None


def _filter_conditions(
    f: LeadFilters, access: LeadAccess, rules: Rules, now: dt.datetime, *, with_chip: bool
) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [
        Lead.merged_into_lead_id.is_(None),
        access.view_condition(),
    ]
    start = _period_start(f.period, now, rules)
    if start is not None:
        conds.append(Lead.first_inbound_at >= start)
    if f.page_id is not None:
        conds.append(Lead.page_id == f.page_id)
    if f.owner_id is not None:
        conds.append(Lead.owner_member_id == f.owner_id)
    if f.source == "ad":
        conds.append(Lead.fb_ad_id.is_not(None))
    elif f.source == "organic":
        conds.append(and_(Lead.fb_ad_id.is_(None), Lead.source == LeadSource.MESSAGE))
    elif f.source == "form":
        conds.append(
            or_(
                Lead.source == LeadSource.LEADGEN,
                exists().where(LeadgenSubmission.lead_id == Lead.id),
            )
        )
    if f.q and f.q.strip():
        conds.append(_search_condition(f.q.strip(), access))
    if with_chip and f.chip is not None:
        conds.append(_chip_condition(f.chip, now, rules))
    if with_chip and f.status is not None:
        conds.append(Lead.status == f.status)
    return conds


def _search_condition(q: str, access: LeadAccess) -> ColumnElement[bool]:
    needle = q.lower()
    by_name = or_(
        func.lower(Contact.display_name).contains(needle, autoescape=True),
        func.lower(_form_name).contains(needle, autoescape=True),
        Contact.psid.endswith(q, autoescape=True),
    )
    digits = "".join(ch for ch in q if ch.isdigit())
    # Người không được xem SĐT không tìm theo SĐT: tránh dò ra số qua kết quả tìm kiếm.
    if access.can_search_phone and len(digits) >= 3 and len(digits) >= len(q.replace(" ", "")) - 1:
        if digits.startswith("84") and len(digits) > 9:
            digits = "0" + digits[2:]
        by_phone = exists().where(
            LeadPhone.lead_id == Lead.id, LeadPhone.phone.contains(digits, autoescape=True)
        )
        return or_(by_name, by_phone)
    return by_name


# ---------------------------------------------------------------- chuyển sang schema


def _short_ref(psid: str | None, form_ref: str | None, lead_id: uuid.UUID) -> str:
    raw = psid or form_ref or lead_id.hex
    return raw[-4:]


def _card(row: Any, access: LeadAccess, rules: Rules, now: dt.datetime) -> LeadCard:
    lead: Lead = row.Lead
    can_phone = access.can_see_phone(lead.owner_member_id)
    waiting: int | None = None
    if (
        lead.source == LeadSource.MESSAGE
        and lead.first_reply_at is None
        and lead.status == LeadStatus.NEW
    ):
        waiting = rules.business_seconds(lead.first_inbound_at, now)
    measured = (
        lead.response_business_seconds if lead.response_business_seconds is not None else waiting
    )
    return LeadCard(
        id=lead.id,
        display_name=row.display_name or row.form_name,
        short_ref=_short_ref(row.psid, row.form_ref, lead.id),
        page=NamedRef(id=lead.page_id, name=row.page_name),
        owner=NamedRef(id=lead.owner_member_id, name=row.owner_name)
        if lead.owner_member_id
        else None,
        source=lead.source,
        from_ad=lead.fb_ad_id is not None,
        fb_ad_id=lead.fb_ad_id,
        status=lead.status,
        first_inbound_at=lead.first_inbound_at,
        first_reply_at=lead.first_reply_at,
        response_business_seconds=lead.response_business_seconds,
        waiting_business_seconds=waiting,
        is_slow=measured is not None and measured > rules.slow_reply_seconds,
        result_due_at=lead.result_due_at,
        result_at=lead.result_at,
        overdue=lead.result_at is None and lead.result_due_at < now,
        callback_at=lead.callback_at,
        won_value_vnd=lead.won_value_vnd,
        lost_reason=lead.lost_reason,
        phone=(lead.phone if can_phone else mask_phone(lead.phone)) if lead.phone else None,
        phone_masked=bool(lead.phone) and not can_phone,
        called_at=lead.called_at,
    )


def _encode_cursor(lead: Lead, *, by_callback: bool = False) -> str:
    at = lead.callback_at if by_callback and lead.callback_at else lead.first_inbound_at
    raw = f"{at.isoformat()}|{lead.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    try:
        at, lead_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return dt.datetime.fromisoformat(at), uuid.UUID(lead_id)
    except (ValueError, UnicodeDecodeError):
        raise ServiceError("invalid_cursor", 400) from None


# ---------------------------------------------------------------- API đọc


async def list_leads(
    db: AsyncSession,
    ctx: AuthContext,
    filters: LeadFilters,
    *,
    limit: int = 30,
    cursor: str | None = None,
    now: dt.datetime | None = None,
) -> LeadPage:
    now = now or dt.datetime.now(dt.UTC)
    access = await lead_access(db, ctx)
    rules = await _rules(db, ctx.workspace_id)
    stmt = _base_select().where(*_filter_conditions(filters, access, rules, now, with_chip=True))
    # Mục M: cột Hẹn lại xếp theo giờ hẹn tăng dần: hẹn đã qua lâu nhất trước, rồi hẹn sắp tới.
    # Ràng buộc `callback_has_time` bảo đảm khách Hẹn lại luôn có giờ hẹn.
    by_callback = filters.status == LeadStatus.CALLBACK
    key = tuple_(Lead.callback_at if by_callback else Lead.first_inbound_at, Lead.id)
    if cursor:
        at, lead_id = _decode_cursor(cursor)
        after = tuple_(at, lead_id)
        stmt = stmt.where(key > after if by_callback else key < after)
    order = (
        (Lead.callback_at.asc(), Lead.id.asc())
        if by_callback
        else (Lead.first_inbound_at.desc(), Lead.id.desc())
    )
    rows = (await db.execute(stmt.order_by(*order).limit(limit + 1))).all()
    items = [_card(r, access, rules, now) for r in rows[:limit]]
    next_cursor = (
        _encode_cursor(rows[limit - 1].Lead, by_callback=by_callback) if len(rows) > limit else None
    )
    return LeadPage(items=items, next_cursor=next_cursor)


async def summary(
    db: AsyncSession, ctx: AuthContext, filters: LeadFilters, *, now: dt.datetime | None = None
) -> LeadSummary:
    now = now or dt.datetime.now(dt.UTC)
    access = await lead_access(db, ctx)
    rules = await _rules(db, ctx.workspace_id)
    conds = _filter_conditions(filters, access, rules, now, with_chip=False)
    statuses = list(LeadStatus)
    columns = [
        func.count(),
        *(
            func.count().filter(_chip_condition(c, now, rules))
            for c in ("unreplied", "overdue", "phone_not_called", "new_today")
        ),
        # Số theo cột tính trong ô lọc nhanh đang chọn; số của các ô lọc nhanh thì không.
        *(
            func.count().filter(
                and_(Lead.status == s, _chip_condition(filters.chip, now, rules))
                if filters.chip
                else Lead.status == s
            )
            for s in statuses
        ),
    ]
    stmt = (
        select(*columns)
        .select_from(Lead)
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .where(*conds)
    )
    row = (await db.execute(stmt)).one()
    return LeadSummary(
        total=row[0],
        unreplied=row[1],
        overdue=row[2],
        phone_not_called=row[3],
        new_today=row[4],
        by_status={s: row[5 + i] for i, s in enumerate(statuses)},
    )


async def filter_options(db: AsyncSession, ctx: AuthContext) -> FilterOptions:
    access = await lead_access(db, ctx)
    visible = (
        select(Lead.page_id, Lead.owner_member_id)
        .where(Lead.merged_into_lead_id.is_(None), access.view_condition())
        .subquery()
    )
    pages = (
        await db.execute(
            select(Page.id, Page.name)
            .where(Page.id.in_(select(visible.c.page_id)))
            .order_by(Page.name)
        )
    ).all()
    owners = (
        await db.execute(
            select(WorkspaceMember.id, User.full_name)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.id.in_(select(visible.c.owner_member_id)))
            .order_by(User.full_name)
        )
    ).all()
    return FilterOptions(
        pages=[NamedRef(id=pid, name=name) for pid, name in pages],
        owners=[NamedRef(id=mid, name=name) for mid, name in owners],
    )


async def _visible_lead_row(db: AsyncSession, access: LeadAccess, lead_id: uuid.UUID) -> Any:
    row = (
        await db.execute(_base_select().where(Lead.id == lead_id, access.view_condition()))
    ).first()
    if row is None:
        raise ServiceError("lead_not_found", 404)
    if row.Lead.merged_into_lead_id is not None:
        raise ServiceError("lead_merged", 404, into_lead_id=str(row.Lead.merged_into_lead_id))
    return row


def permissions_for(ctx: AuthContext, lead: Lead, now: dt.datetime) -> LeadPermissions:
    scope = ctx.scope(Perm.LEAD_UPDATE)
    can_update = scope == Scope.ALL or (
        scope == Scope.OWN and lead.owner_member_id == ctx.member_id
    )
    privileged = scope == Scope.ALL
    edit_until = lead.result_at + RESULT_EDIT_WINDOW if lead.result_at and not privileged else None
    can_edit = can_update and (edit_until is None or now <= edit_until)
    return LeadPermissions(can_update=can_update, can_edit_result=can_edit, edit_until=edit_until)


async def _timeline(
    db: AsyncSession, lead: Lead, can_phone: bool, now: dt.datetime
) -> tuple[list[TimelineItem], bool]:
    messages = list(
        (
            await db.scalars(
                select(Message)
                .where(Message.lead_id == lead.id)
                .order_by(Message.sent_at.desc(), Message.id.desc())
                .limit(TIMELINE_LIMIT + 1)
            )
        ).all()
    )
    truncated = len(messages) > TIMELINE_LIMIT
    messages = messages[:TIMELINE_LIMIT]
    events = (
        await db.execute(
            select(LeadEvent, User.full_name)
            .outerjoin(WorkspaceMember, WorkspaceMember.id == LeadEvent.actor_member_id)
            .outerjoin(User, User.id == WorkspaceMember.user_id)
            .where(LeadEvent.lead_id == lead.id)
            .order_by(LeadEvent.occurred_at, LeadEvent.id)
        )
    ).all()
    items: list[TimelineItem] = []
    for m in messages:
        text = m.text
        if text and not can_phone:
            text = mask_phones_in_text(text)
        items.append(
            TimelineItem(
                kind="message",
                at=m.sent_at,
                direction="in" if m.direction == MessageDirection.IN else "out",
                text=text,
                has_attachments=m.has_attachments,
                is_automated=m.is_automated,
                is_first_reply=m.mid == lead.first_reply_mid,
            )
        )
    # Mục M: nhắc việc gửi cùng lúc, cùng người gửi gộp thành một dòng; `types` giữ thứ tự gửi.
    # Người gửi so theo member, không theo tên hiển thị (hai người có thể trùng tên).
    reminder_types: dict[tuple[dt.datetime, uuid.UUID | None], list[str]] = {}
    for ev, actor in events:
        if ev.type == LeadEventType.REMINDER_SENT:
            key = (ev.occurred_at, ev.actor_member_id)
            types = reminder_types.get(key)
            if types is None:
                types = reminder_types[key] = []
                items.append(
                    TimelineItem(
                        kind="event",
                        at=ev.occurred_at,
                        type=ev.type.value,
                        actor=actor,
                        data={"types": types},
                    )
                )
            kind = (ev.data or {}).get("type")
            if kind and kind not in types:
                types.append(kind)
            continue
        items.append(
            TimelineItem(
                kind="event", at=ev.occurred_at, type=ev.type.value, actor=actor, data=ev.data
            )
        )
    if lead.result_at is None and lead.result_due_at < now:
        items.append(TimelineItem(kind="event", at=lead.result_due_at, type="overdue"))
    # Cùng thời điểm: sự kiện hệ thống ("tạo khách") đứng trước tin nhắn.
    items.sort(key=lambda i: (i.at, 0 if i.kind == "event" and i.type == "created" else 1))
    return items, truncated


async def get_lead(
    db: AsyncSession, ctx: AuthContext, lead_id: uuid.UUID, *, now: dt.datetime | None = None
) -> LeadDetail:
    now = now or dt.datetime.now(dt.UTC)
    access = await lead_access(db, ctx)
    rules = await _rules(db, ctx.workspace_id)
    row = await _visible_lead_row(db, access, lead_id)
    lead: Lead = row.Lead
    can_phone = access.can_see_phone(lead.owner_member_id)
    phones = (
        await db.scalars(
            select(LeadPhone.phone)
            .where(LeadPhone.lead_id == lead.id)
            .order_by(LeadPhone.detected_at)
        )
    ).all()
    timeline, truncated = await _timeline(db, lead, can_phone, now)
    card = _card(row, access, rules, now)
    cost_visible = ctx.can(Perm.ADS_COST_VIEW)
    return LeadDetail(
        **card.model_dump(),
        fb_page_id=row.fb_page_id,
        slow_reply_minutes=rules.slow_reply_minutes,
        lost_note=lead.lost_note,
        phones=[p if can_phone else mask_phone(p) for p in phones],
        timeline=timeline,
        timeline_truncated=truncated,
        permissions=await _with_remind(db, ctx, lead, permissions_for(ctx, lead, now)),
        campaign_name=await db.scalar(select(Campaign.name).where(Campaign.id == lead.campaign_id))
        if lead.campaign_id
        else None,
        cost_visible=cost_visible,
        estimated_cost_vnd=await ads_service.lead_cost(db, lead, rules.tz.key)
        if cost_visible
        else None,
    )


async def _with_remind(
    db: AsyncSession, ctx: AuthContext, lead: Lead, perms: LeadPermissions
) -> LeadPermissions:
    owners = await member_ids_for(db, ctx, ctx.scope(Perm.REMINDER_SEND))
    can = (
        lead.owner_member_id is not None
        and lead.owner_member_id != ctx.member_id
        and ctx.can(Perm.REMINDER_SEND)
        and (owners is None or lead.owner_member_id in owners)
        and lead.status not in _FINAL
    )
    return perms.model_copy(update={"can_remind": can})


# ---------------------------------------------------------------- API ghi


async def _lock_for_update(
    db: AsyncSession, ctx: AuthContext, lead_id: uuid.UUID, now: dt.datetime
) -> tuple[Lead, LeadPermissions]:
    access = await lead_access(db, ctx)
    await _visible_lead_row(db, access, lead_id)
    lead = await db.get(Lead, lead_id, with_for_update=True, populate_existing=True)
    if lead is None:
        raise ServiceError("lead_not_found", 404)
    perms = permissions_for(ctx, lead, now)
    if not perms.can_update:
        raise ServiceError("forbidden", 403, permission=Perm.LEAD_UPDATE.value)
    return lead, perms


def _result_snapshot(lead: Lead) -> dict[str, Any]:
    """Trạng thái kết quả cho audit/lịch sử. Không có SĐT."""
    return {
        "status": lead.status.value,
        "callback_at": lead.callback_at.isoformat() if lead.callback_at else None,
        "won_value_vnd": lead.won_value_vnd,
        "lost_reason": lead.lost_reason.value if lead.lost_reason else None,
        "lost_note": lead.lost_note,
        "called_at": lead.called_at.isoformat() if lead.called_at else None,
    }


async def set_called(
    db: AsyncSession,
    ctx: AuthContext,
    lead_id: uuid.UUID,
    called: bool,
    *,
    now: dt.datetime | None = None,
) -> LeadDetail:
    """Nhân viên tự đánh dấu đã gọi cho khách (bật/tắt)."""
    now = now or dt.datetime.now(dt.UTC)
    lead, _ = await _lock_for_update(db, ctx, lead_id, now)
    if called != (lead.called_at is not None):
        before = _result_snapshot(lead)
        lead.called_at = now if called else None
        db.add(
            LeadEvent(
                workspace_id=lead.workspace_id,
                lead_id=lead.id,
                type=LeadEventType.CALLED,
                actor_member_id=ctx.member_id,
                occurred_at=now,
                data={"called": called},
            )
        )
        await audit.record(
            db,
            workspace_id=ctx.workspace_id,
            actor_member_id=ctx.member_id,
            action="lead.called",
            entity_type="lead",
            entity_id=lead.id,
            before=before,
            after=_result_snapshot(lead),
            ip=ctx.ip,
        )
        await db.commit()
    return await get_lead(db, ctx, lead_id, now=now)


async def set_result(
    db: AsyncSession,
    ctx: AuthContext,
    lead_id: uuid.UUID,
    body: ResultUpdate,
    *,
    now: dt.datetime | None = None,
) -> LeadDetail:
    """Lưu Hẹn lại / Chốt / Hủy. `result_at` chỉ ghi ở lần có kết quả đầu tiên."""
    now = now or dt.datetime.now(dt.UTC)
    lead, perms = await _lock_for_update(db, ctx, lead_id, now)
    if not perms.can_edit_result:
        raise ServiceError(
            "result_edit_window_closed",
            403,
            edit_until=perms.edit_until.isoformat() if perms.edit_until else None,
        )
    if (
        body.status == LeadStatus.CALLBACK
        and body.callback_at is not None
        and body.callback_at <= now
    ):
        raise ServiceError("callback_must_be_future", 422)

    before = _result_snapshot(lead)
    previous = lead.status
    note = body.note.strip() if body.note and body.note.strip() else None
    lead.status = body.status
    lead.status_changed_at = now
    lead.callback_at = body.callback_at if body.status == LeadStatus.CALLBACK else None
    lead.won_value_vnd = body.won_value_vnd if body.status == LeadStatus.WON else None
    lead.lost_reason = body.lost_reason if body.status == LeadStatus.LOST else None
    lead.lost_note = note if body.status == LeadStatus.LOST else None
    first_result = lead.result_at is None
    if first_result:
        lead.result_at = now
    after = _result_snapshot(lead)

    data: dict[str, Any] = {"from": previous.value, "to": body.status.value}
    for key in ("callback_at", "won_value_vnd", "lost_reason"):
        if after[key] is not None:
            data[key] = after[key]
    if note:
        data["note"] = note
    db.add(
        LeadEvent(
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            type=LeadEventType.STATUS_CHANGED,
            actor_member_id=ctx.member_id,
            occurred_at=now,
            data=data,
        )
    )
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="lead.result_set" if first_result else "lead.result_edited",
        entity_type="lead",
        entity_id=lead.id,
        before=before,
        after=after,
        ip=ctx.ip,
    )
    await db.commit()
    return await get_lead(db, ctx, lead_id, now=now)
