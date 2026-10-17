"""Cảnh báo Telegram và tỉ giá (Bước 7): cấu hình, gửi một lần, không lộ SĐT, quyền."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_token_cipher
from app.models import AdInsightDaily, AlertDelivery, AuditLog, BusinessManager
from app.services.telegram import HttpTelegram, MockTelegram, TelegramError, set_telegram
from app.workers.alerts import send_alerts
from app.workers.meta_checks import check_bms
from tests.integration.report_fixtures import Demo

pytestmark = pytest.mark.integration

VN = ZoneInfo("Asia/Ho_Chi_Minh")
CHAT = "-1001234567890"


@pytest.fixture
def telegram() -> Iterator[MockTelegram]:
    sender = MockTelegram()
    set_telegram(sender)
    yield sender
    set_telegram(None)


async def _configure(owner: httpx.AsyncClient, **rules: dict[str, Any]) -> None:
    resp = await owner.put(
        "/api/settings/alerts",
        json={
            "chat_id": CHAT,
            "rules": [{"type": t, **body} for t, body in rules.items()],
        },
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    ("role", "method", "path", "code"),
    [
        ("manager", "get", "/api/settings/alerts", 403),
        ("owner", "get", "/api/settings/alerts", 200),
        ("viewer", "get", "/api/alerts/rules", 200),
        ("lead", "get", "/api/alerts/rules", 403),
        ("viewer", "put", "/api/alerts/rules/frequency", 403),
        ("manager", "post", "/api/settings/fx-rates", 403),
    ],
)
async def test_alert_permissions(
    as_user: Any, role: str, method: str, path: str, code: int
) -> None:
    client = await as_user(role)
    body = {"enabled": True} if method == "put" else None
    if path.endswith("fx-rates"):
        body = {"currency": "USD", "effective_from": "2026-01-01", "vnd_per_unit": "25000"}
    resp = await client.request(method.upper(), path, json=body)
    assert resp.status_code == code, resp.text


async def test_settings_validate_and_audit(as_user: Any, admin_db: AsyncSession) -> None:
    owner = await as_user("owner")
    bad = await owner.put("/api/settings/alerts", json={"chat_id": "abc; drop"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_chat_id"
    assert "drop" not in bad.text
    out_of_range = await owner.put(
        "/api/settings/alerts",
        json={"rules": [{"type": "frequency", "enabled": True, "params": {"max": 0.1}}]},
    )
    assert out_of_range.json()["detail"]["code"] == "invalid_rule_param"
    await _configure(owner, frequency={"enabled": True, "params": {"max": 2.5}})
    body = (await owner.get("/api/settings/alerts")).json()
    assert body["chat_id"] == CHAT and body["is_mock"] is True
    rules = {r["type"]: r for r in body["rules"]}
    assert rules["frequency"]["enabled"] is True and rules["frequency"]["params"]["max"] == 2.5
    assert rules["cost_per_result"]["params"]["max_vnd"] == 25_000  # mặc định
    assert body["currencies"] == ["USD"]
    actions = set(await admin_db.scalars(select(AuditLog.action)))
    assert {"alert.chat_id", "alert_rule.update"} <= actions


async def test_send_test_message(as_user: Any, telegram: MockTelegram) -> None:
    owner = await as_user("owner")
    missing = await owner.post("/api/settings/alerts/test")
    assert missing.json()["detail"]["code"] == "telegram_chat_missing"
    await _configure(owner)
    resp = await owner.post("/api/settings/alerts/test")
    assert resp.status_code == 200 and resp.json() == {"status": "mock"}
    assert telegram.sent and telegram.sent[0][0] == CHAT


async def test_fx_rate_converts_existing_spend(as_user: Any, admin_db: AsyncSession) -> None:
    owner = await as_user("owner")
    resp = await owner.post(
        "/api/settings/fx-rates",
        json={"currency": "USD", "effective_from": "2020-01-01", "vnd_per_unit": "25000"},
    )
    assert resp.status_code == 200, resp.text
    missing = await admin_db.scalar(
        select(func.count()).where(
            AdInsightDaily.currency == "USD", AdInsightDaily.spend_vnd.is_(None)
        )
    )
    assert missing == 0
    overview = (await owner.get("/api/reports/overview")).json()
    assert overview["missing_fx"] == []

    rate_id = resp.json()["fx_rates"][0]["id"]
    assert (await owner.delete(f"/api/settings/fx-rates/{rate_id}")).status_code == 200
    assert (await owner.get("/api/reports/overview")).json()["missing_fx"] == ["USD"]
    vnd = await owner.post(
        "/api/settings/fx-rates",
        json={"currency": "VND", "effective_from": "2020-01-01", "vnd_per_unit": "1"},
    )
    assert vnd.status_code == 422


async def test_campaign_alerts_sent_once_without_phone(
    as_user: Any, telegram: MockTelegram, admin_db: AsyncSession
) -> None:
    owner = await as_user("owner")
    await _configure(
        owner,
        cost_per_result={"enabled": True, "params": {"max_vnd": 1000, "min_spend_vnd": 0}},
        cost_per_won={"enabled": True, "params": {"max_vnd": 1000}},
        frequency={"enabled": True, "params": {"max": 1.0}},
        daily_summary={"enabled": False},
    )
    first = await send_alerts({})
    assert first["sent"] > 0 and first["failed"] == 0
    rules = set(await admin_db.scalars(select(AlertDelivery.rule_type)))
    assert rules == {"cost_per_result", "cost_per_won", "frequency"}
    assert all("0912345678" not in text and "0987654321" not in text for _, text in telegram.sent)
    assert any("[Tin nhắn - Giải pháp tài chính]" in text for _, text in telegram.sent)
    count = len(telegram.sent)

    again = await send_alerts({})
    assert again["sent"] == 0 and len(telegram.sent) == count


async def test_daily_summary_after_8am_once(
    as_user: Any, telegram: MockTelegram, admin_db: AsyncSession
) -> None:
    owner = await as_user("owner")
    await _configure(
        owner,
        cost_per_result={"enabled": False},
        cost_per_won={"enabled": False},
    )
    today = dt.datetime.now(VN).date()
    early = dt.datetime.combine(today, dt.time(7, 0), tzinfo=VN)
    assert (await send_alerts({}, now=early))["sent"] == 0
    morning = dt.datetime.combine(today, dt.time(8, 0, 30), tzinfo=VN)
    assert (await send_alerts({}, now=morning))["sent"] == 1
    assert (await send_alerts({}, now=morning + dt.timedelta(hours=1)))["sent"] == 0
    text = telegram.sent[-1][1]
    assert "Tóm tắt ngày" in text and "/overview" in text


class _Flaky(MockTelegram):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    async def send(self, chat_id: str, text: str) -> None:
        if self.fail:
            raise TelegramError("network")
        await super().send(chat_id, text)


async def test_failed_delivery_is_retried(as_user: Any, admin_db: AsyncSession) -> None:
    owner = await as_user("owner")
    await _configure(
        owner,
        cost_per_result={"enabled": True, "params": {"max_vnd": 1000, "min_spend_vnd": 0}},
        cost_per_won={"enabled": False},
        daily_summary={"enabled": False},
    )
    flaky = _Flaky()
    set_telegram(flaky)
    try:
        assert (await send_alerts({}))["failed"] > 0
        statuses = set(await admin_db.scalars(select(AlertDelivery.status)))
        assert statuses == {"failed"}
        flaky.fail = False
        assert (await send_alerts({}))["sent"] > 0
    finally:
        set_telegram(None)
    admin_db.expire_all()
    assert set(await admin_db.scalars(select(AlertDelivery.status))) == {"mock"}


async def test_bm_disconnect_alert(
    as_user: Any, demo: Demo, telegram: MockTelegram, admin_db: AsyncSession
) -> None:
    await _configure(await as_user("owner"))
    bm = await admin_db.scalar(select(BusinessManager))
    assert bm is not None
    bm.token_ciphertext = get_token_cipher().encrypt("MOCK-INVALID")
    await admin_db.commit()
    await check_bms({})
    texts = [text for _, text in telegram.sent]
    assert any(text.startswith("BM mất kết nối") and "/bm" in text for text in texts)
    assert "MOCK-INVALID" not in " ".join(texts)


async def test_ads_page_rule_toggle(as_user: Any) -> None:
    viewer = await as_user("viewer")
    view = (await viewer.get("/api/alerts/rules")).json()
    assert view["can_edit"] is False and view["chat_configured"] is False
    owner = await as_user("owner")
    resp = await owner.put("/api/alerts/rules/frequency", json={"enabled": True})
    assert resp.status_code == 200
    rules = {r["type"]: r for r in resp.json()["rules"]}
    assert rules["frequency"]["enabled"] is True and resp.json()["can_edit"] is True
    unknown = await owner.put("/api/alerts/rules/pause_ads", json={"enabled": True})
    assert unknown.status_code == 404


async def test_http_telegram_errors_never_contain_token() -> None:
    token = "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/bot{token}/sendMessage"
        return httpx.Response(403, json={"ok": False, "description": f"blocked {request.url}"})

    sender = HttpTelegram(token, transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramError) as exc:
        await sender.send(CHAT, "xin chào")
    assert exc.value.kind == "blocked"
    assert token not in str(exc.value) and token not in repr(exc.value)
