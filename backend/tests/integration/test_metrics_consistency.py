"""Ràng buộc chéo giữa các màn hình (decisions.md mục J, docs/metrics.md).

Cùng kỳ và cùng phạm vi: Tổng quan = tổng các dòng /staff (gồm dòng "Chưa có người phụ trách") =
tổng các Trang /pages; phễu cộng khớp; điểm một người giống nhau ở mọi màn.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeadSource, LeadStatus
from app.services.assignment import assign_page
from tests.integration import factories as f
from tests.integration.report_fixtures import FISS, NOW, RABBIT, SMART, SOFTWARE, Demo

pytestmark = pytest.mark.integration

H = dt.timedelta(hours=1)
TEAMS = ("[Nhóm 1]", "[Nhóm 2]")


@pytest.fixture
async def mixed(demo: Demo, admin_db: AsyncSession) -> Demo:
    """Thêm các trường hợp làm lệch số liệu trước đây."""
    pages, acc = demo.pages, demo.accounts
    # Khách vào Mua Sắm lúc chưa có ai phụ trách: không tính cho ai, kể cả sau khi gán Trang.
    for i in range(3):
        await f.create_lead(
            admin_db,
            pages[SMART],
            None,
            NOW - (5 + i) * H,
            won_value_vnd=3_000_000 if i == 0 else None,
        )
    await assign_page(admin_db, pages[SMART], acc["owner"].member, NOW - 2 * H)
    # Shop Thỏ: Quản lý từng phụ trách, khách của giai đoạn đó vẫn tính cho Quản lý.
    for i in range(2):
        await f.create_lead(admin_db, pages[RABBIT], acc["manager"].member, NOW - (8 + i) * H)
    for i in range(4):
        await f.create_lead(
            admin_db,
            pages[RABBIT],
            acc["lead"].member,
            NOW - (3 + i) * H,
            phone="0911111111",
            response_seconds=900 if i else None,
        )
    # Có SĐT nhưng chưa được trả lời; khách form có SĐT; chốt mà chưa bấm "Đã gọi"; hẹn, hủy.
    await f.create_lead(
        admin_db,
        pages[SOFTWARE],
        acc["s1"].member,
        NOW - 4 * H,
        response_seconds=None,
        phone="0922222222",
    )
    await f.create_lead(
        admin_db,
        pages[FISS],
        acc["s2"].member,
        NOW - 6 * H,
        response_seconds=None,
        phone="0933333333",
        source=LeadSource.LEADGEN,
    )
    called = await f.create_lead(
        admin_db, pages[SOFTWARE], acc["s1"].member, NOW - 7 * H, phone="0944444444"
    )
    called.callback_at = NOW + H
    called.status = LeadStatus.CALLBACK
    called.called_at = NOW - 6 * H
    lost = await f.create_lead(
        admin_db,
        pages[FISS],
        acc["s2"].member,
        NOW - 9 * H,
        phone="0955555555",
        status=LeadStatus.LOST,
    )
    lost.called_at = NOW - 8 * H
    await admin_db.commit()
    return demo


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    resp = await client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _staff_totals(board: Any, teams: set[str] | None = None) -> dict[str, int]:
    rows = [r for r in board["rows"] if teams is None or (r["team"] and r["team"]["name"] in teams)]
    extra = board["unassigned"] if teams is None and board["unassigned"] else None
    return {
        "leads": sum(r["lead_count"] for r in rows) + (extra["lead_count"] if extra else 0),
        "won": sum(r["won_count"] for r in rows) + (extra["won_count"] if extra else 0),
        "revenue": sum(r["revenue_vnd"] for r in rows) + (extra["revenue_vnd"] if extra else 0),
    }


def _page_totals(pages: Any) -> dict[str, int]:
    return {
        "leads": sum(r["leads_7d"] for r in pages["rows"]),
        "won": sum(r["won_7d"] for r in pages["rows"]),
        "revenue": sum(r["revenue_7d"] for r in pages["rows"]),
    }


def _overview_totals(ov: Any) -> dict[str, int]:
    return {
        "leads": int(Decimal(ov["kpis"]["new_leads"]["value"])),
        "won": ov["funnel"]["won"],
        "revenue": int(Decimal(ov["kpis"]["revenue_vnd"]["value"])),
    }


@pytest.mark.parametrize("role", ["owner", "manager", "viewer", "lead"])
async def test_overview_equals_staff_equals_pages(mixed: Demo, as_user: Any, role: str) -> None:
    client = await as_user(role)
    ov = await _get(client, "/api/reports/overview?range=7d")
    board = await _get(client, "/api/staff/leaderboard?period=rolling_7")
    pages = await _get(client, "/api/reports/pages")
    assert board["period"]["first_day"] == ov["range"]["first_day"] == pages["range"]["first_day"]
    assert _overview_totals(ov) == _staff_totals(board) == _page_totals(pages)
    assert board["kpis"]["lead_count"] == _overview_totals(ov)["leads"]
    assert (
        ov["kpis"]["overdue_in_range"]
        == board["kpis"]["overdue_count"]
        == sum(r["overdue_7d"] for r in pages["rows"])
    )
    assert board["kpis"]["median_response_seconds"] == (
        int(Decimal(ov["kpis"]["median_response_seconds"]["value"]))
        if ov["kpis"]["median_response_seconds"]["value"] is not None
        else None
    )


async def test_same_totals_when_filtering_one_team(mixed: Demo, as_user: Any) -> None:
    owner = await as_user("owner")
    teams = {t["name"]: t["id"] for t in (await _get(owner, "/api/reports/overview"))["teams"]}
    board = await _get(owner, "/api/staff/leaderboard?period=rolling_7")
    for name in TEAMS:
        ov = await _get(owner, f"/api/reports/overview?range=7d&team_id={teams[name]}")
        pages = await _get(owner, f"/api/reports/pages?team_id={teams[name]}")
        assert _overview_totals(ov) == _staff_totals(board, {name}) == _page_totals(pages)


async def test_unassigned_leads_and_owner_in_staff(mixed: Demo, as_user: Any) -> None:
    owner = await as_user("owner")
    board = await _get(owner, "/api/staff/leaderboard?period=rolling_7")
    unassigned = board["unassigned"]
    assert unassigned["lead_count"] == 3 and unassigned["revenue_vnd"] == 3_000_000
    roles = {r["member"]["name"]: r["role"] for r in board["rows"]}
    # Chủ sở hữu phụ trách Mua Sắm từ giữa kỳ: có trong danh sách, có nhãn vai trò.
    assert roles[mixed.accounts["owner"].user.full_name] == "owner"
    assert roles[mixed.accounts["manager"].user.full_name] == "manager"
    ov = await _get(owner, "/api/reports/overview?range=7d")
    assert ov["alerts"]["unassigned_pages"] == 0
    assert ov["alerts"]["unassigned_leads"] == 3
    assert ov["members"] == len(board["rows"])
    lead = await as_user("lead")
    assert (await _get(lead, "/api/staff/leaderboard?period=rolling_7"))["unassigned"] is None
    assert (await _get(lead, "/api/reports/overview"))["alerts"]["unassigned_leads"] is None


async def test_funnel_adds_up(mixed: Demo, as_user: Any) -> None:
    ov = await _get(await as_user("owner"), "/api/reports/overview?range=7d")
    f_ = ov["funnel"]
    assert f_["unreplied"] == f_["new"] - f_["replied"]
    assert f_["no_phone"] == f_["replied"] - f_["phone"]
    assert f_["not_called"] == f_["phone"] - f_["called"]
    assert f_["won"] + f_["lost"] + f_["callback"] + f_["pending"] == f_["new"]
    assert f_["new"] >= f_["replied"] >= f_["phone"] >= f_["called"]
    # Khách có SĐT mà chưa được trả lời không vào bước "Có SĐT" của phễu, nhưng vẫn tính vào ô
    # "Có số điện thoại %" (tiêu chí điểm).
    phones_all = Decimal(ov["kpis"]["phone_rate"]["value"]) * f_["new"]
    assert round(phones_all) > f_["phone"]
    assert sum(d["new"] for d in ov["daily"]) == f_["new"]
    assert sum(d["won"] for d in ov["daily"]) == f_["won"]


async def test_scores_same_everywhere(mixed: Demo, as_user: Any) -> None:
    owner = await as_user("owner")
    board = await _get(owner, "/api/staff/leaderboard?period=rolling_7")
    ov = await _get(owner, "/api/reports/overview?range=7d")
    pages = await _get(owner, "/api/reports/pages")
    assert ov["boards"]["same_as_range"] is True
    board_totals = {
        b["member"]["id"]: b["total"] for b in ov["boards"]["top"] + ov["boards"]["bottom"]
    }
    page_totals = {r["owner"]["id"]: r["owner_total"] for r in pages["rows"] if r["owner"]}
    ranked = [r for r in board["rows"] if r["total"] is not None]
    assert ranked
    for row in ranked:
        mid = row["member"]["id"]
        detail = await _get(owner, f"/api/staff/{mid}?period=rolling_7")
        assert detail["total"] == row["total"]
        assert detail["lead_count"] == row["lead_count"]
        assert board_totals.get(mid, row["total"]) == row["total"]
        assert page_totals.get(mid, row["total"]) == row["total"]
        assert len(board_totals) == len(ranked)


async def test_score_parts_explain_conversion(mixed: Demo, as_user: Any) -> None:
    """Mục K: mọi tiêu chí trừ Chăm Trang có ngưỡng 0 điểm / 100 điểm, điểm nằm đúng giữa."""
    owner = await as_user("owner")
    board = await _get(owner, "/api/staff/leaderboard?period=rolling_7")
    ranked = [r for r in board["rows"] if r["total"] is not None]
    assert ranked
    for row in ranked:
        detail = await _get(owner, f"/api/staff/{row['member']['id']}?period=rolling_7")
        parts = {p["key"]: p for p in detail["parts"]}
        assert parts["page_care"]["method"] == "target"
        assert (
            Decimal(parts["response_speed"]["zero"]),
            Decimal(parts["response_speed"]["full"]),
        ) == (
            Decimal(120),
            Decimal(5),
        )
        for key in ("close_rate", "phone_rate", "on_time"):
            part = parts[key]
            assert part["method"] == "linear"
            if part["score"] is None:
                continue
            rate = Decimal(part["raw"]["rate"]) * 100
            zero, full = Decimal(part["zero"]), Decimal(part["full"])
            expected = min(max((rate - zero) / (full - zero), Decimal(0)), Decimal(1)) * 100
            assert abs(Decimal(part["score"]) - expected) <= Decimal("0.01")
        assert detail["trend"][-1]["is_final"] is False


async def test_pages_show_leads_per_owner_when_more_than_one(mixed: Demo, as_user: Any) -> None:
    pages = await _get(await as_user("owner"), "/api/reports/pages")
    rows = {r["fb_page_id"]: r for r in pages["rows"]}
    acc = mixed.accounts
    rabbit = {
        (s["member"]["name"] if s["member"] else None): s["leads"]
        for s in rows[RABBIT]["owners_in_range"]
    }
    assert rabbit == {acc["lead"].user.full_name: 4, acc["manager"].user.full_name: 2}
    assert sum(rabbit.values()) == rows[RABBIT]["leads_7d"]
    # Mua Sắm: khách vào lúc chưa có ai, Chủ sở hữu nhận Trang sau đó (0 khách).
    smart = {
        (s["member"]["name"] if s["member"] else None): s["leads"]
        for s in rows[SMART]["owners_in_range"]
    }
    assert smart == {None: 3, acc["owner"].user.full_name: 0}
    # Chỉ một người: không ghi chú.
    assert rows[SOFTWARE]["owners_in_range"] == []


async def test_staff_shows_page_ownership_that_ended_in_period(
    mixed: Demo, as_user: Any, admin_db: AsyncSession
) -> None:
    acc = mixed.accounts
    # Đổi qua lại nhiều lần: chỉ hiện một dòng, lần thôi phụ trách gần nhất.
    await assign_page(admin_db, mixed.pages[SOFTWARE], acc["manager"].member, NOW - 3 * H)
    await assign_page(admin_db, mixed.pages[SOFTWARE], acc["s1"].member, NOW - 2 * H)
    ended = NOW - H
    await assign_page(admin_db, mixed.pages[SOFTWARE], acc["manager"].member, ended)
    # Shop Thỏ: Trưởng nhóm thôi rồi được gán lại, vẫn đang phụ trách nên không hiện.
    await assign_page(admin_db, mixed.pages[RABBIT], acc["viewer"].member, NOW - 3 * H)
    await assign_page(admin_db, mixed.pages[RABBIT], acc["lead"].member, NOW - 2 * H)
    await admin_db.commit()
    board = await _get(await as_user("owner"), "/api/staff/leaderboard?period=rolling_7")
    rows = {r["member"]["name"]: r for r in board["rows"]}
    s1 = rows[acc["s1"].user.full_name]
    assert s1["pages"] == []
    assert [p["name"] for p in s1["past_pages"]] == [mixed.pages[SOFTWARE].name]
    assert dt.datetime.fromisoformat(s1["past_pages"][0]["until"]) == ended
    assert rows[acc["manager"].user.full_name]["pages"] == [mixed.pages[SOFTWARE].name]
    assert rows[acc["lead"].user.full_name]["past_pages"] == []
    assert [p["name"] for p in rows[acc["viewer"].user.full_name]["past_pages"]] == [
        mixed.pages[RABBIT].name
    ]
    assert rows[acc["s2"].user.full_name]["past_pages"] == []
