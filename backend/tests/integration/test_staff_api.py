"""API Nhân viên và Công thức điểm: phạm vi xem (#9), xem thử khớp kết quả job, tuần đã chốt."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    MemberRole,
    PeriodType,
    ScoreFormula,
    ScoreSnapshot,
    WorkspaceSettings,
)
from app.services.assignment import assign_page
from app.services.periods import period_for
from tests.integration import factories as f

pytestmark = pytest.mark.integration

# Ngưỡng mặc định (decisions.md mục K).
THRESHOLDS = {
    "speed_full_minutes": 5,
    "speed_zero_minutes": 120,
    "close_rate_zero": 5,
    "close_rate_full": 30,
    "revenue_full_vnd": 20_000_000,
    "phone_rate_zero": 30,
    "phone_rate_full": 80,
    "on_time_zero": 50,
    "on_time_full": 95,
}

VN = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass
class Org:
    ws_id: Any
    accounts: dict[str, f.Account]
    ids: dict[str, Any]
    week_start: dt.date


@pytest.fixture
async def org(admin_db: AsyncSession) -> Org:
    ws = await f.create_workspace(admin_db)
    t1 = await f.create_team(admin_db, ws, "[Nhóm 1]")
    t2 = await f.create_team(admin_db, ws, "[Nhóm 2]")
    acc = {
        "owner": await f.create_account(admin_db, MemberRole.OWNER, workspace=ws),
        "manager": await f.create_account(admin_db, MemberRole.MANAGER, workspace=ws),
        "lead": await f.create_account(admin_db, MemberRole.TEAM_LEAD, workspace=ws, team=t1),
        "s1": await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=t1),
        "s2": await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=t2),
        "viewer": await f.create_account(admin_db, MemberRole.VIEWER, workspace=ws),
    }
    t1.lead_member_id = acc["lead"].member.id
    now = dt.datetime.now(dt.UTC)
    week = period_for(PeriodType.WEEK, now, VN)
    start = week.utc_range(VN)[0]
    profile = {
        "s1": {"response": 120, "phone": "0900000001", "won": 5},
        "s2": {"response": 7200, "phone": None, "won": 1},
        "lead": {"response": 900, "phone": "0900000002", "won": 3},
    }
    for key, p in profile.items():
        page = await f.create_page(admin_db, ws, name=f"[Trang {key}]")
        await assign_page(admin_db, page, acc[key].member, start - dt.timedelta(days=30))
        for i in range(10):
            await f.create_lead(
                admin_db,
                page,
                acc[key].member,
                start + dt.timedelta(minutes=1, seconds=i),
                response_seconds=p["response"],
                phone=p["phone"],
                won_value_vnd=5_000_000 if i < p["won"] else None,
            )
    await admin_db.commit()
    return Org(ws.id, acc, {k: a.member.id for k, a in acc.items()}, week.first_day)


@pytest.fixture
async def as_role(client: httpx.AsyncClient, org: Org) -> AsyncIterator[Any]:
    async def login(role: str) -> httpx.AsyncClient:
        client.cookies.clear()
        await f.login(client, org.accounts[role])
        return client

    yield login


async def _recompute(as_role: Any) -> None:
    owner = await as_role("owner")
    resp = await owner.post("/api/score/recompute")
    assert resp.status_code == 200, resp.text


async def _board(client: httpx.AsyncClient, period: str = "week") -> dict[str, Any]:
    resp = await client.get("/api/staff/leaderboard", params={"period": period})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_owner_sees_full_leaderboard(as_role: Any, org: Org) -> None:
    await _recompute(as_role)
    board = await _board(await as_role("owner"))
    assert board["full_view"] is True
    assert board["period"]["first_day"] == org.week_start.isoformat()
    names = [r["member"]["id"] for r in board["rows"]]
    assert names[0] == str(org.ids["s1"])
    first = board["rows"][0]
    assert first["rank"] == 1 and first["tier"] == "A" and first["lead_count"] == 10
    assert first["pages"] == ["[Trang s1]"]
    assert board["tiers"]["A"] >= 1
    assert board["kpis"]["lead_count"] == 30
    assert board["kpis"]["revenue_vnd"] == 45_000_000
    assert board["kpis"]["median_response_seconds"] == 900  # trung vị của 10×120, 10×900, 10×7200
    assert {t["name"] for t in board["teams"]} == {"[Nhóm 1]", "[Nhóm 2]"}
    for period in ("rolling_7", "rolling_30", "month"):
        assert (await _board(await as_role("owner"), period))["rows"]


async def test_staff_sees_own_score_and_top10_names_only(
    as_role: Any, org: Org, admin_db: AsyncSession
) -> None:
    await _recompute(as_role)
    board = await _board(await as_role("s2"))
    assert board["full_view"] is False
    assert board["kpis"] is None and board["tiers"] is None
    rows = {r["member"]["id"]: r for r in board["rows"]}
    me = rows[str(org.ids["s2"])]
    assert me["is_self"] and me["total"] is not None and me["lead_count"] == 10
    other = rows[str(org.ids["s1"])]
    assert other["tier"] == "A" and other["rank"] == 1
    assert other["total"] is None and other["lead_count"] is None and other["revenue_vnd"] is None

    settings = await admin_db.get(WorkspaceSettings, org.ws_id)
    assert settings is not None
    settings.staff_can_see_leaderboard = False
    await admin_db.commit()
    board = await _board(await as_role("s2"))
    assert [r["member"]["id"] for r in board["rows"]] == [str(org.ids["s2"])]


async def test_team_lead_sees_own_team(as_role: Any, org: Org) -> None:
    await _recompute(as_role)
    board = await _board(await as_role("lead"))
    ids = {r["member"]["id"] for r in board["rows"]}
    assert ids == {str(org.ids["s1"]), str(org.ids["lead"])}
    assert all(r["total"] is not None for r in board["rows"])


@pytest.mark.parametrize(
    ("role", "target", "code"),
    [
        ("s1", "s1", 200),
        ("s1", "s2", 404),
        ("lead", "s1", 200),
        ("lead", "s2", 404),
        ("viewer", "s2", 200),
        ("manager", "lead", 200),
    ],
)
async def test_staff_detail_scope(
    as_role: Any, org: Org, role: str, target: str, code: int
) -> None:
    await _recompute(as_role)
    client = await as_role(role)
    resp = await client.get(f"/api/staff/{org.ids[target]}")
    assert resp.status_code == code, resp.text


async def test_staff_detail_explains_score(as_role: Any, org: Org) -> None:
    await _recompute(as_role)
    detail = (await (await as_role("s1")).get(f"/api/staff/{org.ids['s1']}")).json()
    assert detail["tier"] == "A" and detail["rank"] == 1 and detail["ranked_count"] == 3
    points = sum(Decimal(p["points"]) for p in detail["parts"] if p["points"] is not None)
    assert abs(points - Decimal(detail["total"])) <= Decimal("0.05")
    care = next(p for p in detail["parts"] if p["key"] == "page_care")
    assert care["score"] is None and care["points"] is None
    funnel = {s["key"]: s for s in detail["funnel"]}
    assert funnel["leads"]["value"] == 10 and funnel["won"]["value"] == 5
    assert funnel["won"]["company_rate"] == "0.3000"
    assert sum(h["count"] for h in detail["hours"]) == 10
    assert len(detail["recent"]) == 6
    assert detail["pages"][0]["name"] == "[Trang s1]"
    assert detail["trend"] and detail["trend"][-1]["total"] == detail["total"]


async def test_preview_matches_saved_formula_result(
    as_role: Any, org: Org, admin_db: AsyncSession
) -> None:
    """Tiêu chí "xong" Bước 4: đổi trọng số thì "xem thử" khớp với kết quả job."""
    await _recompute(as_role)
    owner = await as_role("owner")
    weights = {
        "close_rate": 10,
        "response_speed": 60,
        "revenue": 10,
        "phone_rate": 10,
        "page_care": 5,
        "on_time": 5,
    }
    body = {"weights": weights, "thresholds": THRESHOLDS}
    preview = await owner.post("/api/score/preview", json=body)
    assert preview.status_code == 200, preview.text
    rows = {r["member"]["id"]: r for r in preview.json()["rows"]}
    lead_row = rows[str(org.ids["lead"])]
    assert lead_row["new_total"] != lead_row["current_total"]

    saved = await owner.put("/api/score/formula", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2
    assert saved.json()["weights"] == weights

    board = await _board(owner)
    for row in board["rows"]:
        assert row["total"] == rows[row["member"]["id"]]["new_total"], row["member"]
        assert row["tier"] == rows[row["member"]["id"]]["new_tier"]
    versions = (
        await admin_db.scalars(
            select(ScoreFormula.version).where(ScoreFormula.workspace_id == org.ws_id)
        )
    ).all()
    assert sorted(versions) == [1, 2]
    audit = await admin_db.scalar(
        select(AuditLog).where(AuditLog.action == "score_formula.updated")
    )
    assert audit is not None and audit.after["response_speed"] == 60


async def test_finalized_week_is_not_recomputed_by_new_formula(
    as_role: Any, org: Org, admin_db: AsyncSession
) -> None:
    formula = await admin_db.scalar(
        select(ScoreFormula).where(ScoreFormula.workspace_id == org.ws_id)
    )
    assert formula is not None
    last_week = org.week_start - dt.timedelta(days=7)
    admin_db.add(
        ScoreSnapshot(
            workspace_id=org.ws_id,
            member_id=org.ids["s1"],
            formula_id=formula.id,
            period_type=PeriodType.WEEK,
            period_start=last_week,
            period_end=last_week + dt.timedelta(days=6),
            computed_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            lead_count=12,
            won_count=1,
            phone_count=1,
            revenue_vnd=1,
            total=Decimal("42.00"),
            insufficient_data=False,
            is_final=True,
        )
    )
    await admin_db.commit()
    owner = await as_role("owner")
    weights = {
        "close_rate": 50,
        "response_speed": 10,
        "revenue": 10,
        "phone_rate": 10,
        "page_care": 10,
        "on_time": 10,
    }
    body = {"weights": weights, "thresholds": THRESHOLDS}
    assert (await owner.put("/api/score/formula", json=body)).status_code == 200
    assert (await owner.post("/api/score/recompute")).status_code == 200
    admin_db.expire_all()
    kept = await admin_db.scalar(
        select(ScoreSnapshot).where(
            ScoreSnapshot.period_start == last_week, ScoreSnapshot.member_id == org.ids["s1"]
        )
    )
    assert kept is not None and kept.total == Decimal("42.00") and kept.is_final


@pytest.mark.parametrize(
    "weights",
    [
        {
            "close_rate": 30,
            "response_speed": 25,
            "revenue": 20,
            "phone_rate": 10,
            "page_care": 10,
            "on_time": 10,
        },
        {
            "close_rate": -5,
            "response_speed": 35,
            "revenue": 20,
            "phone_rate": 20,
            "page_care": 15,
            "on_time": 15,
        },
        {"close_rate": 100},
    ],
)
async def test_invalid_weights_are_rejected(as_role: Any, weights: dict[str, int]) -> None:
    owner = await as_role("owner")
    body = {"weights": weights, "thresholds": THRESHOLDS}
    assert (await owner.put("/api/score/formula", json=body)).status_code == 422
    assert (await owner.post("/api/score/preview", json=body)).status_code == 422


@pytest.mark.parametrize("role", ["manager", "lead", "s1", "viewer"])
async def test_only_owner_edits_formula(as_role: Any, role: str) -> None:
    client = await as_role(role)
    weights = {
        "close_rate": 30,
        "response_speed": 25,
        "revenue": 20,
        "phone_rate": 10,
        "page_care": 10,
        "on_time": 5,
    }
    body = {"weights": weights, "thresholds": THRESHOLDS}
    assert (await client.put("/api/score/formula", json=body)).status_code == 403
    assert (await client.post("/api/score/preview", json=body)).status_code == 403
    assert (await client.post("/api/score/recompute")).status_code == 403
    formula = (await client.get("/api/score/formula")).json()
    assert formula["can_edit"] is False and formula["page_care_available"] is False


async def test_threshold_change_preview_matches_saved(as_role: Any, org: Org) -> None:
    """Đổi ngưỡng (mục K): "xem thử" khớp điểm sau khi lưu, và điểm đổi theo ngưỡng."""
    owner = await as_role("owner")
    formula = (await owner.get("/api/score/formula")).json()
    assert formula["thresholds"] == THRESHOLDS
    stricter = {**THRESHOLDS, "close_rate_full": 80, "phone_rate_zero": 60}
    body = {"weights": formula["weights"], "thresholds": stricter}
    preview = (await owner.post("/api/score/preview", json=body)).json()
    rows = {r["member"]["id"]: r for r in preview["rows"]}
    s1 = rows[str(org.ids["s1"])]
    assert Decimal(s1["new_total"]) < Decimal(s1["current_total"])

    saved = await owner.put("/api/score/formula", json=body)
    assert saved.status_code == 200 and saved.json()["thresholds"] == stricter
    board = await _board(owner)
    for row in board["rows"]:
        if row["total"] is not None:
            assert row["total"] == rows[row["member"]["id"]]["new_total"]
    detail = (await owner.get(f"/api/staff/{org.ids['s1']}")).json()
    close = next(p for p in detail["parts"] if p["key"] == "close_rate")
    assert close["method"] == "linear"
    assert (Decimal(close["zero"]), Decimal(close["full"])) == (Decimal(5), Decimal(80))


@pytest.mark.parametrize(
    "change",
    [
        {"close_rate_zero": 30, "close_rate_full": 30},
        {"on_time_zero": 96},
        {"speed_full_minutes": 120},
        {"phone_rate_full": 101},
        {"revenue_full_vnd": 0},
    ],
)
async def test_invalid_thresholds_are_rejected(as_role: Any, change: dict[str, int]) -> None:
    owner = await as_role("owner")
    formula = (await owner.get("/api/score/formula")).json()
    body = {"weights": formula["weights"], "thresholds": {**THRESHOLDS, **change}}
    assert (await owner.put("/api/score/formula", json=body)).status_code == 422
    assert (await owner.post("/api/score/preview", json=body)).status_code == 422


async def test_last_week_with_other_formula_is_flagged(
    as_role: Any, org: Org, admin_db: AsyncSession
) -> None:
    """Mục L: tuần đã chốt tính bằng phiên bản công thức khác thì ▲▼ và biểu đồ ghi "khác công
    thức"; tuần đó không bị tính lại."""
    old = await admin_db.scalar(select(ScoreFormula).where(ScoreFormula.workspace_id == org.ws_id))
    assert old is not None and old.score_method == "threshold"
    old.score_method = "percentile"
    last_week = org.week_start - dt.timedelta(days=7)
    admin_db.add(
        ScoreSnapshot(
            workspace_id=org.ws_id,
            member_id=org.ids["s1"],
            formula_id=old.id,
            period_type=PeriodType.WEEK,
            period_start=last_week,
            period_end=last_week + dt.timedelta(days=6),
            computed_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            lead_count=12,
            won_count=1,
            phone_count=1,
            revenue_vnd=1,
            total=Decimal("42.00"),
            insufficient_data=False,
            is_final=True,
        )
    )
    await admin_db.commit()
    owner = await as_role("owner")
    # Cùng phiên bản: không ghi chú.
    row = next(r for r in (await _board(owner))["rows"] if r["member"]["id"] == str(org.ids["s1"]))
    assert row["delta"] is not None and row["delta_other_formula"] is False

    formula = (await owner.get("/api/score/formula")).json()
    body = {"weights": formula["weights"], "thresholds": {**THRESHOLDS, "close_rate_full": 40}}
    saved = (await owner.put("/api/score/formula", json=body)).json()
    assert saved["version"] == 2 and saved["score_method"] == "threshold"

    row = next(r for r in (await _board(owner))["rows"] if r["member"]["id"] == str(org.ids["s1"]))
    assert row["delta_other_formula"] is True
    detail = (await owner.get(f"/api/staff/{org.ids['s1']}")).json()
    assert detail["delta_other_formula"] is True and detail["formula_version"] == 2
    past, current = detail["trend"][-2], detail["trend"][-1]
    assert past["total"] == "42.00" and past["other_formula"] is True
    assert past["formula_version"] == 1
    assert current["other_formula"] is False and current["formula_version"] == 2
