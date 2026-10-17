"""Dựng dữ liệu cho test xử lý webhook: một workspace, một Trang, hai nhân viên."""

from __future__ import annotations

import datetime as dt
import itertools
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.events import WebhookPayload
from app.mock import payloads as p
from app.models import Contact, Lead, MemberRole
from app.services.assignment import assign_page
from app.workers.webhook import process_webhook
from tests.integration import factories as f

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


async def make_world(admin_db: AsyncSession) -> World:
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


async def run_changes(world: World, *changes: dict[str, Any]) -> dict[str, int]:
    return await process_webhook(
        {"job_try": 1}, WebhookPayload(p.page_payload(world.fb, changes=list(changes)))
    )
