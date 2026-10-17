"""Job tính điểm ban đêm: snapshot theo kỳ, chốt tuần, tách workspace."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Lead,
    MemberRole,
    PeriodType,
    ScoreSnapshot,
    Tier,
    Workspace,
    WorkspaceStatus,
)
from app.services.assignment import assign_page
from app.workers.scoring import nightly_scores
from tests.integration import factories as f

pytestmark = pytest.mark.integration

VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Thứ Tư 14/10/2026, 12:00 giờ VN. Tuần hiện tại 12–18/10, tuần trước 5–11/10.
WEDNESDAY = dt.datetime(2026, 10, 14, 12, 0, tzinfo=VN)
NEXT_MONDAY = dt.datetime(2026, 10, 19, 1, 0, tzinfo=VN)


def vn(day: int, hour: int = 10) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, 0, tzinfo=VN)


@dataclass
class Team:
    ws_id: object
    good: object
    slow: object
    few: object


@pytest.fixture
async def team(admin_db: AsyncSession) -> Team:
    ws = await f.create_workspace(admin_db)
    members = []
    for i in range(3):
        m = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.STAFF)
        page = await f.create_page(admin_db, ws, name=f"[Trang {i}]")
        await assign_page(admin_db, page, m, vn(1, 0))
        members.append((m, page))
    (good, good_page), (slow, slow_page), (few, few_page) = members
    # Tuần hiện tại: người tốt 10 khách, trả lời 2 phút, có SĐT, chốt 5.
    for i in range(10):
        await f.create_lead(
            admin_db,
            good_page,
            good,
            vn(12, 9) + dt.timedelta(minutes=i),
            response_seconds=120,
            phone="0900000001",
            won_value_vnd=1_000_000 if i < 5 else None,
        )
    # Người chậm: 10 khách, trả lời 2 giờ, không SĐT, chốt 1.
    for i in range(10):
        await f.create_lead(
            admin_db,
            slow_page,
            slow,
            vn(12, 9) + dt.timedelta(minutes=i),
            response_seconds=7200,
            won_value_vnd=500_000 if i == 0 else None,
        )
    # Người ít khách: 3 khách → chưa đủ dữ liệu.
    for i in range(3):
        await f.create_lead(admin_db, few_page, few, vn(13, 9) + dt.timedelta(minutes=i))
    await admin_db.commit()
    return Team(ws.id, good.id, slow.id, few.id)


async def _rows(
    db: AsyncSession, period_type: PeriodType, start: dt.date
) -> dict[object, ScoreSnapshot]:
    db.expire_all()
    rows = await db.scalars(
        select(ScoreSnapshot).where(
            ScoreSnapshot.period_type == period_type, ScoreSnapshot.period_start == start
        )
    )
    return {r.member_id: r for r in rows}


async def test_nightly_job_writes_week_and_reference_periods(
    team: Team, admin_db: AsyncSession
) -> None:
    result = await nightly_scores({}, now=WEDNESDAY)
    assert result == {"workspaces": 1, "failed": 0}

    week = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 12))
    assert set(week) == {team.good, team.slow, team.few}
    good, slow, few = week[team.good], week[team.slow], week[team.few]
    assert good.lead_count == 10 and good.won_count == 5 and good.revenue_vnd == 5_000_000
    assert good.median_response_seconds == 120
    assert good.s_response_speed == 100 and slow.s_response_speed == 0
    assert good.s_page_care is None  # Chăm Trang chưa có số liệu (Bước 7)
    assert good.total == 100 and good.tier == Tier.A and good.rank == 1
    assert slow.total == 0 and slow.tier == Tier.D and slow.rank == 2
    assert few.insufficient_data and few.total is None and few.rank is None
    assert not good.is_final

    for period_type in (PeriodType.ROLLING_7, PeriodType.ROLLING_30, PeriodType.MONTH):
        rows = await admin_db.scalars(
            select(ScoreSnapshot).where(ScoreSnapshot.period_type == period_type)
        )
        assert len(rows.all()) == 3, period_type


async def test_monday_finalizes_last_week_and_never_rewrites_it(
    team: Team, admin_db: AsyncSession
) -> None:
    await nightly_scores({}, now=NEXT_MONDAY)
    final = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 12))
    assert all(r.is_final for r in final.values())
    assert final[team.good].revenue_vnd == 5_000_000

    # Dữ liệu tuần đã chốt bị sửa sau đó: điểm tuần đó giữ nguyên.
    lead = await admin_db.scalar(
        select(Lead).where(Lead.owner_member_id == team.slow, Lead.won_value_vnd.is_not(None))
    )
    assert lead is not None
    lead.won_value_vnd = 99_000_000
    await admin_db.commit()
    await nightly_scores({}, now=NEXT_MONDAY + dt.timedelta(days=1))
    again = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 12))
    assert again[team.slow].revenue_vnd == 500_000
    assert again[team.slow].computed_at == final[team.slow].computed_at

    # Tuần mới (19–25/10) đã có dòng, chưa chốt.
    current = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 19))
    assert current and not any(r.is_final for r in current.values())


async def test_workspaces_are_scored_separately(team: Team, admin_db: AsyncSession) -> None:
    other = await f.create_workspace(admin_db)
    member = await f.create_member(admin_db, other, await f.create_user(admin_db), MemberRole.STAFF)
    page = await f.create_page(admin_db, other)
    await assign_page(admin_db, page, member, vn(1, 0))
    for i in range(12):
        await f.create_lead(
            admin_db, page, member, vn(12) + dt.timedelta(minutes=i), response_seconds=7200
        )
    suspended = await f.create_workspace(admin_db)
    suspended.status = WorkspaceStatus.SUSPENDED
    member_id, other_id = member.id, other.id
    await admin_db.commit()

    assert await nightly_scores({}, now=WEDNESDAY) == {"workspaces": 2, "failed": 0}
    week = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 12))
    # Một mình trong workspace của mình: phần trăm = 100, không bị so với workspace kia.
    assert week[member_id].s_close_rate == 100
    assert week[member_id].workspace_id == other_id
    assert week[team.slow].rank == 2


async def test_member_assigned_but_without_leads_is_listed(
    team: Team, admin_db: AsyncSession
) -> None:
    ws = await admin_db.get(Workspace, team.ws_id)
    assert ws is not None
    idle = await f.create_member(admin_db, ws, await f.create_user(admin_db), MemberRole.TEAM_LEAD)
    page = await f.create_page(admin_db, ws)
    await assign_page(admin_db, page, idle, vn(13, 0))
    idle_id = idle.id
    await admin_db.commit()
    await nightly_scores({}, now=WEDNESDAY)
    week = await _rows(admin_db, PeriodType.WEEK, dt.date(2026, 10, 12))
    assert week[idle_id].lead_count == 0 and week[idle_id].insufficient_data
