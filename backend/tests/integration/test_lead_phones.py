"""Nhận SĐT trong tin nhắn và gộp khách form với khách nhắn tin (quyết định #16, Bước 3)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mock import payloads as p
from app.models import (
    Contact,
    Lead,
    LeadEvent,
    LeadEventType,
    LeadgenSubmission,
    LeadPhone,
    LeadSource,
    Workspace,
)
from tests.integration import factories as f
from tests.integration.inbound_helpers import (
    World,
    make_world,
    one_lead,
    run,
    run_changes,
    uid,
    vn,
)

pytestmark = pytest.mark.integration

FORM_ID = "900000000000001"  # fixture: [Khách 1042], +84900000142
FORM_PHONE = "0900000142"


@pytest.fixture
async def world(admin_db: AsyncSession) -> World:
    return await make_world(admin_db)


async def _form(world: World, at: dt.datetime, *, ad_id: str | None = "238100") -> str:
    leadgen_id = uid("44")
    await run_changes(world, p.leadgen(world.fb, leadgen_id, FORM_ID, at, ad_id=ad_id))
    return leadgen_id


async def _visible_leads(db: AsyncSession, world: World) -> list[Lead]:
    db.expire_all()
    rows = await db.scalars(
        select(Lead).where(Lead.page_id == world.page.id, Lead.merged_into_lead_id.is_(None))
    )
    return list(rows)


async def test_phone_with_separators_is_detected(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m"), vn(5, 9), "số em 0912 345 678 nhé"))
    lead = await one_lead(admin_db, psid)
    assert lead.phone == "0912345678"
    assert lead.phone_source == "message"
    assert lead.phone_captured_at == vn(5, 9)
    row = await admin_db.scalar(select(LeadPhone).where(LeadPhone.lead_id == lead.id))
    assert row is not None and row.message_id is not None and row.source == "message"
    event = await admin_db.scalar(
        select(LeadEvent).where(
            LeadEvent.lead_id == lead.id, LeadEvent.type == LeadEventType.PHONE_DETECTED
        )
    )
    assert event is not None
    assert "0912" not in str(event.data)


async def test_first_phone_stays_primary(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m"), vn(5, 9), "0912345678"),
        p.inbound(world.fb, psid, uid("m"), vn(5, 9, 5), "à số khác 0387654321, lại 0912345678"),
    )
    lead = await one_lead(admin_db, psid)
    assert lead.phone == "0912345678"
    phones = (
        await admin_db.scalars(select(LeadPhone.phone).where(LeadPhone.lead_id == lead.id))
    ).all()
    assert sorted(phones) == ["0387654321", "0912345678"]
    detected = await admin_db.scalar(
        select(func.count()).where(
            LeadEvent.lead_id == lead.id, LeadEvent.type == LeadEventType.PHONE_DETECTED
        )
    )
    assert detected == 1


async def test_phone_in_page_reply_is_ignored(world: World, admin_db: AsyncSession) -> None:
    psid = uid("psid")
    await run(
        world,
        p.inbound(world.fb, psid, uid("m"), vn(5, 9), "giá bao nhiêu?"),
        p.echo(world.fb, psid, uid("m"), vn(5, 9, 3), "gọi hotline 0901234567 ạ"),
    )
    assert (await one_lead(admin_db, psid)).phone is None


async def test_form_then_message_with_same_phone_merges(
    world: World, admin_db: AsyncSession
) -> None:
    leadgen_id = await _form(world, vn(5, 8))
    psid = uid("psid")
    await run(
        world, p.inbound(world.fb, psid, uid("m"), vn(5, 9), "em vừa điền form, 0900 000 142")
    )

    visible = await _visible_leads(admin_db, world)
    assert len(visible) == 1
    message_lead = visible[0]
    assert message_lead.source == LeadSource.MESSAGE
    assert message_lead.fb_ad_id == "238100"
    form_lead = await admin_db.scalar(
        select(Lead).where(Lead.page_id == world.page.id, Lead.source == LeadSource.LEADGEN)
    )
    assert form_lead is not None and form_lead.merged_into_lead_id == message_lead.id
    sub = await admin_db.scalar(
        select(LeadgenSubmission).where(LeadgenSubmission.leadgen_id == leadgen_id)
    )
    assert sub is not None and sub.lead_id == message_lead.id
    contact = await admin_db.get(Contact, message_lead.contact_id)
    assert contact is not None and contact.display_name == "[Khách 1042]"
    merged = await admin_db.scalar(
        select(func.count()).where(LeadEvent.type == LeadEventType.MERGED)
    )
    assert merged == 2


async def test_message_then_form_attaches_to_message_lead(
    world: World, admin_db: AsyncSession
) -> None:
    psid = uid("psid")
    await run(world, p.inbound(world.fb, psid, uid("m"), vn(5, 9), "0900000142"))
    leadgen_id = await _form(world, vn(6, 10))
    visible = await _visible_leads(admin_db, world)
    assert len(visible) == 1
    assert visible[0].source == LeadSource.MESSAGE
    assert visible[0].fb_ad_id == "238100"
    sub = await admin_db.scalar(
        select(LeadgenSubmission).where(LeadgenSubmission.leadgen_id == leadgen_id)
    )
    assert sub is not None and sub.lead_id == visible[0].id
    assert await admin_db.scalar(select(func.count()).select_from(Lead)) == 1


async def test_form_already_worked_on_is_not_merged(world: World, admin_db: AsyncSession) -> None:
    await _form(world, vn(5, 8))
    form_lead = await admin_db.scalar(select(Lead).where(Lead.source == LeadSource.LEADGEN))
    assert form_lead is not None
    form_lead.called_at = vn(5, 8, 30)
    await admin_db.commit()
    await run(world, p.inbound(world.fb, uid("psid"), uid("m"), vn(5, 9), "0900000142"))
    assert len(await _visible_leads(admin_db, world)) == 2


async def test_form_in_another_episode_is_not_merged(world: World, admin_db: AsyncSession) -> None:
    await _form(world, vn(1, 8, month=9))
    await run(world, p.inbound(world.fb, uid("psid"), uid("m"), vn(5, 9), "0900000142"))
    assert len(await _visible_leads(admin_db, world)) == 2


async def test_form_on_another_page_is_not_merged(world: World, admin_db: AsyncSession) -> None:
    ws = await admin_db.get(Workspace, world.ws.id)
    assert ws is not None
    other = await f.create_page(admin_db, ws)
    other_fb = other.fb_page_id
    await admin_db.commit()
    await run_changes(
        World(world.ws, world.page, world.staff_a, world.staff_b, other_fb),
        p.leadgen(other_fb, uid("44"), FORM_ID, vn(5, 8)),
    )
    await run(world, p.inbound(world.fb, uid("psid"), uid("m"), vn(5, 9), "0900000142"))
    assert (
        await admin_db.scalar(
            select(func.count()).select_from(Lead).where(Lead.merged_into_lead_id.is_not(None))
        )
        == 0
    )
