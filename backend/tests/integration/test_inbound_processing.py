"""Worker xử lý webhook: khách, đợt, người phụ trách, thời gian trả lời (CLAUDE.md mục 3).

Giờ làm việc 08:00–22:00 Asia/Ho_Chi_Minh. Mọi thời điểm viết theo giờ Việt Nam.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from arq import Retry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.meta.events import WebhookPayload, parse_payload
from app.mock import payloads as p
from app.models import (
    Contact,
    Lead,
    LeadEvent,
    LeadEventType,
    LeadgenFetchStatus,
    LeadgenSubmission,
    LeadSource,
    LeadStatus,
    MemberRole,
    Message,
    Page,
    WebhookEvent,
    WebhookEventStatus,
    Workspace,
    WorkspaceMember,
)
from app.services import inbound
from app.services.assignment import assign_page, end_assignment
from app.services.errors import ServiceError
from app.workers.webhook import process_event, process_webhook
from tests.integration import factories as f

pytestmark = pytest.mark.integration

VN = ZoneInfo("Asia/Ho_Chi_Minh")
_ids = itertools.count(1)


def vn(day: int, hour: int, minute: int = 0, second: int = 0, month: int = 10) -> dt.datetime:
    return dt.datetime(2026, month, day, hour, minute, second, tzinfo=VN)


def uid(prefix: str) -> str:
    return f"{prefix}{next(_ids):06d}"


@dataclass(frozen=True)
class Ref:
    id: uuid.UUID


@dataclass(frozen=True)
class World:
    """Chỉ giữ giá trị thuần: object ORM bị expire sau mỗi lần đọc lại DB."""

    ws: Ref
    page: Ref
    staff_a: Ref
    staff_b: Ref
    fb: str


@pytest.fixture
async def world(admin_db: AsyncSession) -> World:
    ws = await f.create_workspace(admin_db)
    page = await f.create_page(admin_db, ws, name="[Trang FISS]")
    a = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
    b = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
    await assign_page(admin_db, page, a, vn(1, 0, month=9))
    await admin_db.commit()
    return World(Ref(ws.id), Ref(page.id), Ref(a.id), Ref(b.id), page.fb_page_id)


async def run(world: World, *messaging: dict[str, Any]) -> dict[str, int]:
    return await process_webhook(
        {"job_try": 1}, WebhookPayload(p.page_payload(world.fb, messaging=list(messaging)))
    )


async def leads_of(db: AsyncSession, psid: str) -> list[Lead]:
    db.expire_all()
    rows = await db.scalars(
        select(Lead)
        .join(Contact, Contact.id == Lead.contact_id)
        .where(Contact.psid == psid)
        .order_by(Lead.episode_no)
    )
    return list(rows)


async def one_lead(db: AsyncSession, psid: str) -> Lead:
    leads = await leads_of(db, psid)
    assert len(leads) == 1, leads
    return leads[0]


def minutes(lead: Lead) -> float | None:
    s = lead.response_business_seconds
    return None if s is None else s / 60


# ------------------------------------------------------------- thời gian trả lời


@pytest.mark.parametrize(
    ("label", "inbound_at", "reply_at", "expected_minutes"),
    [
        ("trong giờ", vn(5, 9, 0), vn(5, 9, 12), 12),
        ("khách nhắn 23:00, trả lời 08:10 hôm sau", vn(5, 23, 0), vn(6, 8, 10), 10),
        ("qua đêm 21:50 → 08:20", vn(5, 21, 50), vn(6, 8, 20), 30),
        ("sáng sớm, trả lời trước giờ mở cửa", vn(5, 6, 30), vn(5, 7, 45), 0),
    ],
)
async def test_response_time_in_business_hours(
    world: World,
    admin_db: AsyncSession,
    label: str,
    inbound_at: dt.datetime,
    reply_at: dt.datetime,
    expected_minutes: int,
) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m_in"), inbound_at))
    lead = await one_lead(admin_db, psid)
    assert lead.status == LeadStatus.NEW
    assert lead.response_business_seconds is None

    await run(world, p.echo(world.fb, psid, uid("m_out"), reply_at))
    lead = await one_lead(admin_db, psid)
    assert minutes(lead) == expected_minutes, label
    assert lead.first_reply_at == reply_at
    assert lead.status == LeadStatus.CONTACTED
    assert lead.status_changed_at == reply_at
    assert lead.owner_member_id == world.staff_a.id
    assert lead.result_due_at == inbound_at + dt.timedelta(hours=48)
    types = (
        await admin_db.scalars(
            select(LeadEvent.type).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.id)
        )
    ).all()
    assert types == [LeadEventType.CREATED, LeadEventType.REPLIED, LeadEventType.STATUS_CHANGED]


async def test_only_first_reply_counts(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 9)),
        p.echo(world.fb, psid, uid("m_out"), vn(5, 9, 7)),
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 9, 20)),
        p.echo(world.fb, psid, uid("m_out"), vn(5, 11)),
    )
    lead = await one_lead(admin_db, psid)
    assert minutes(lead) == 7
    replied = await admin_db.scalar(
        select(func.count()).where(
            LeadEvent.lead_id == lead.id, LeadEvent.type == LeadEventType.REPLIED
        )
    )
    assert replied == 1


async def test_automated_echo_is_not_a_reply(
    world: World, admin_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "meta_automated_app_ids", "111,222")
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 10)),
        p.echo(world.fb, psid, uid("m_auto"), vn(5, 10, 0, 5), app_id="222"),
    )
    lead = await one_lead(admin_db, psid)
    assert lead.status == LeadStatus.NEW
    assert lead.response_business_seconds is None
    auto = await admin_db.scalar(select(Message).where(Message.lead_id == lead.id, Message.is_echo))
    assert auto is not None and auto.is_automated and auto.app_id == "222"

    # Người trả lời qua Meta Business Suite (app_id khác, không nằm trong danh sách): có tính.
    await run(
        world, p.echo(world.fb, psid, uid("m_human"), vn(5, 10, 25), app_id="263902037430900")
    )
    lead = await one_lead(admin_db, psid)
    assert minutes(lead) == 25
    assert lead.status == LeadStatus.CONTACTED


async def test_echo_without_app_id_counts_as_reply(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 14)),
        p.echo(world.fb, psid, uid("m_out"), vn(5, 14, 3)),
    )
    assert minutes(await one_lead(admin_db, psid)) == 3


async def test_echo_arriving_before_inbound_is_reattached(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    await run(world, p.echo(world.fb, psid, uid("m_out"), vn(5, 9, 15)))
    assert await leads_of(admin_db, psid) == []
    orphan = await admin_db.scalar(select(Message).join(Contact).where(Contact.psid == psid))
    assert orphan is not None and orphan.lead_id is None

    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(5, 9)))
    lead = await one_lead(admin_db, psid)
    assert minutes(lead) == 15
    assert lead.status == LeadStatus.CONTACTED


async def test_earlier_inbound_arriving_late_moves_the_start(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    first_mid = uid("m_in")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 9, 10)),
        p.echo(world.fb, psid, uid("m_out"), vn(5, 9, 20)),
    )
    assert minutes(await one_lead(admin_db, psid)) == 10
    await run(world, p.inbound(world.fb, psid, first_mid, vn(5, 9, 0)))
    lead = await one_lead(admin_db, psid)
    assert lead.first_inbound_mid == first_mid
    assert minutes(lead) == 20


async def test_page_initiated_message_creates_no_lead(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(world, p.echo(world.fb, psid, uid("m_out"), vn(5, 9)))
    assert await leads_of(admin_db, psid) == []


# ------------------------------------------------------------- tin lặp


async def test_duplicate_delivery_is_processed_once(world: World, admin_db: AsyncSession) -> None:
    psid, mid_in, mid_out = uid("psid"), uid("m_in"), uid("m_out")
    batch = [
        p.inbound(world.fb, psid, mid_in, vn(5, 9)),
        p.echo(world.fb, psid, mid_out, vn(5, 9, 4)),
    ]
    first = await run(world, *batch)
    second = await run(world, *batch)
    assert first == {"processed": 2}
    assert second == {"duplicate": 2}
    lead = await one_lead(admin_db, psid)
    assert minutes(lead) == 4
    assert (
        await admin_db.scalar(
            select(func.count()).select_from(Message).where(Message.lead_id == lead.id)
        )
        == 2
    )
    assert await admin_db.scalar(select(func.count()).select_from(WebhookEvent)) == 2
    events = await admin_db.scalar(select(func.count()).where(LeadEvent.lead_id == lead.id))
    assert events == 3


async def test_concurrent_messages_of_new_contact_open_one_lead(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    payload = p.page_payload(
        world.fb,
        messaging=[p.inbound(world.fb, psid, uid("m_in"), vn(5, 9, 0, s)) for s in range(6)],
    )
    events = parse_payload(payload)
    results = await asyncio.gather(*(process_event(ev) for ev in events))
    assert results == ["processed"] * 6
    lead = await one_lead(admin_db, psid)
    assert lead.first_inbound_at == vn(5, 9)
    count = await admin_db.scalar(
        select(func.count()).select_from(Message).where(Message.lead_id == lead.id)
    )
    assert count == 6


# ------------------------------------------------------------- người phụ trách


async def test_reassignment_mid_way(world: World, admin_db: AsyncSession) -> None:
    old_customer, new_customer = uid("psid"), uid("psid")
    await run(world, p.inbound(world.fb, old_customer, uid("m_in"), vn(5, 9)))

    page = await admin_db.get(Page, world.page.id)
    member_b = await admin_db.get(WorkspaceMember, world.staff_b.id)
    assert page is not None and member_b is not None
    await assign_page(admin_db, page, member_b, vn(5, 12))
    await admin_db.commit()

    # Khách cũ nhắn tiếp sau khi đổi người: vẫn cùng đợt, giữ người cũ.
    await run(world, p.inbound(world.fb, old_customer, uid("m_in"), vn(5, 13)))
    await run(world, p.inbound(world.fb, new_customer, uid("m_in"), vn(5, 13)))
    assert (await one_lead(admin_db, old_customer)).owner_member_id == world.staff_a.id
    assert (await one_lead(admin_db, new_customer)).owner_member_id == world.staff_b.id


async def test_owner_is_decided_by_message_time_not_arrival_time(
    world: World, admin_db: AsyncSession
) -> None:
    page = await admin_db.get(Page, world.page.id)
    member_b = await admin_db.get(WorkspaceMember, world.staff_b.id)
    assert page is not None and member_b is not None
    await assign_page(admin_db, page, member_b, vn(5, 12))
    await admin_db.commit()
    psid = uid("psid")
    # Tin gửi lúc 11:59 (người cũ) nhưng tới worker sau khi đã đổi người.
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(5, 11, 59)))
    assert (await one_lead(admin_db, psid)).owner_member_id == world.staff_a.id


async def test_page_without_owner(world: World, admin_db: AsyncSession) -> None:
    page = await admin_db.get(Page, world.page.id)
    assert page is not None
    await end_assignment(admin_db, page, vn(5, 0))
    await admin_db.commit()
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(5, 9)),
        p.echo(world.fb, psid, uid("m_out"), vn(5, 9, 6)),
    )
    lead = await one_lead(admin_db, psid)
    assert lead.owner_member_id is None
    # Vẫn đo thời gian trả lời, chỉ không tính điểm cho ai.
    assert minutes(lead) == 6


async def test_one_page_per_member_setting(world: World, admin_db: AsyncSession) -> None:
    ws = await admin_db.get(Workspace, world.ws.id)
    assert ws is not None
    other = await f.create_page(admin_db, ws)
    member_a = await admin_db.get(WorkspaceMember, world.staff_a.id)
    assert member_a is not None
    with pytest.raises(ServiceError, match="member_already_has_page"):
        await assign_page(admin_db, other, member_a, vn(5, 0))


# ------------------------------------------------------------- đợt khách


async def test_new_episode_after_more_than_30_days_silence(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(1, 9)))
    # 29 ngày sau: vẫn đợt 1.
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(30, 9)))
    assert len(await leads_of(admin_db, psid)) == 1
    # Im lặng 30 ngày + 1 phút kể từ tin cuối: mở đợt 2.
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(29, 9, 1, month=11)))
    leads = await leads_of(admin_db, psid)
    assert [lead.episode_no for lead in leads] == [1, 2]
    assert leads[1].first_inbound_at == vn(29, 9, 1, month=11)
    assert leads[1].status == LeadStatus.NEW


async def test_reply_goes_to_the_episode_it_answers(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m_in"), vn(1, 9)),
        p.echo(world.fb, psid, uid("m_out"), vn(1, 9, 2)),
        p.inbound(world.fb, psid, uid("m_in"), vn(15, 9, month=11)),
        p.echo(world.fb, psid, uid("m_out"), vn(15, 9, 9, month=11)),
    )
    leads = await leads_of(admin_db, psid)
    assert [minutes(lead) for lead in leads] == [2, 9]


# ------------------------------------------------------------- định tuyến


async def test_untracked_page_is_dropped(world: World, admin_db: AsyncSession) -> None:
    result = await process_webhook(
        {"job_try": 1},
        WebhookPayload(
            p.page_payload(
                "199999999999999", messaging=[p.inbound("199999999999999", "x", uid("m"), vn(5, 9))]
            )
        ),
    )
    assert result == {"unrouted": 1}
    assert await admin_db.scalar(select(func.count()).select_from(Contact)) == 0
    assert await admin_db.scalar(select(func.count()).select_from(WebhookEvent)) == 0


async def test_event_lands_in_the_page_workspace(world: World, admin_db: AsyncSession) -> None:
    other_ws = await f.create_workspace(admin_db)
    other_page = await f.create_page(admin_db, other_ws)
    other_ws_id, other_fb = other_ws.id, other_page.fb_page_id
    await admin_db.commit()
    psid = uid("psid")
    await process_webhook(
        {"job_try": 1},
        WebhookPayload(
            p.page_payload(
                other_fb,
                messaging=[p.inbound(other_fb, psid, uid("m"), vn(5, 9))],
            )
        ),
    )
    lead = await one_lead(admin_db, psid)
    assert lead.workspace_id == other_ws_id
    assert lead.owner_member_id is None


async def test_ignored_kinds_are_not_stored(world: World, admin_db: AsyncSession) -> None:
    payload = p.page_payload(
        world.fb,
        messaging=[
            {
                "sender": {"id": "1"},
                "recipient": {"id": world.fb},
                "timestamp": 1,
                "read": {"watermark": 1},
            }
        ],
        changes=[{"field": "feed", "value": {"item": "status"}}],
    )
    assert await process_webhook({"job_try": 1}, WebhookPayload(payload)) == {"ignored": 2}
    assert await admin_db.scalar(select(func.count()).select_from(WebhookEvent)) == 0


# ------------------------------------------------------------- quảng cáo


async def test_ad_referral_on_first_message(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(5, 9), ad_id="238001"))
    lead = await one_lead(admin_db, psid)
    assert lead.fb_ad_id == "238001"
    assert lead.referral is not None and lead.referral["source"] == "ADS"


async def test_referral_before_message_is_claimed_by_new_episode(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    await run(world, p.referral(world.fb, psid, vn(5, 8, 59), "238002"))
    pending = await admin_db.scalar(select(WebhookEvent).where(WebhookEvent.kind == "referral"))
    assert pending is not None and pending.status == WebhookEventStatus.IGNORED
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(5, 9)))
    assert (await one_lead(admin_db, psid)).fb_ad_id == "238002"
    await admin_db.refresh(pending)
    assert pending.status == WebhookEventStatus.PROCESSED


async def test_referral_on_open_episode_sets_ad_once(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m_in"), vn(5, 9)))
    await run(world, p.referral(world.fb, psid, vn(5, 10), "238003"))
    await run(world, p.referral(world.fb, psid, vn(5, 11), "238004"))
    assert (await one_lead(admin_db, psid)).fb_ad_id == "238003"


# ------------------------------------------------------------- leadgen


async def _leadgen(world: World, leadgen_id: str, form_id: str, at: dt.datetime) -> dict[str, int]:
    payload = p.page_payload(
        world.fb, changes=[p.leadgen(world.fb, leadgen_id, form_id, at, ad_id="238009")]
    )
    return await process_webhook({"job_try": 1}, WebhookPayload(payload))


async def test_leadgen_creates_lead_with_phone(world: World, admin_db: AsyncSession) -> None:
    leadgen_id = uid("44")
    assert await _leadgen(world, leadgen_id, "900000000000001", vn(5, 9)) == {"processed": 1}
    assert await _leadgen(world, leadgen_id, "900000000000001", vn(5, 9)) == {"duplicate": 1}
    sub = await admin_db.scalar(
        select(LeadgenSubmission).where(LeadgenSubmission.leadgen_id == leadgen_id)
    )
    assert sub is not None
    assert sub.fetch_status == LeadgenFetchStatus.FETCHED
    assert "city" not in sub.field_data
    lead = await admin_db.get(Lead, sub.lead_id)
    assert lead is not None
    assert lead.source == LeadSource.LEADGEN
    assert lead.contact_id is None
    assert lead.phone == "0900000142"
    assert lead.phone_source == "leadgen"
    assert lead.fb_ad_id == "238009"
    assert lead.owner_member_id == world.staff_a.id
    # Khách từ form không đo thời gian trả lời (quyết định #16).
    assert lead.response_business_seconds is None
    assert lead.result_due_at == vn(7, 9)


async def test_leadgen_outside_mock_mode_waits_for_page_token(
    world: World, admin_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "mock_mode", False)
    leadgen_id = uid("44")
    await _leadgen(world, leadgen_id, "900000000000001", vn(5, 9))
    sub = await admin_db.scalar(
        select(LeadgenSubmission).where(LeadgenSubmission.leadgen_id == leadgen_id)
    )
    assert sub is not None
    assert sub.fetch_status == LeadgenFetchStatus.PENDING
    assert sub.field_data == {}


# ------------------------------------------------------------- lỗi và thử lại


async def test_failure_is_recorded_then_retried(
    world: World, admin_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = inbound.handle_message

    async def boom(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("lỗi giả")

    monkeypatch.setattr(inbound, "handle_message", boom)
    psid, mid = uid("psid"), uid("m_in")
    batch = [p.inbound(world.fb, psid, mid, vn(5, 9))]
    with pytest.raises(Retry):
        await run(world, *batch)
    row = await admin_db.scalar(select(WebhookEvent).where(WebhookEvent.dedupe_key == f"mid:{mid}"))
    assert row is not None
    assert row.status == WebhookEventStatus.FAILED
    assert row.error == "RuntimeError"
    assert await leads_of(admin_db, psid) == []

    monkeypatch.setattr(inbound, "handle_message", original)
    assert await run(world, *batch) == {"processed": 1}
    await admin_db.refresh(row)
    assert row.status == WebhookEventStatus.PROCESSED
    assert row.attempts == 2
    assert row.error is None
    assert len(await leads_of(admin_db, psid)) == 1
