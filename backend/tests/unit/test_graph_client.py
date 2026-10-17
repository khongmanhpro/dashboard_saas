"""Client Graph API: mã không nằm trong URL, appsecret_proof, thử lại, giới hạn gọi, client giả."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.meta.graph import (
    MESSAGING_ACTION,
    GraphError,
    HttpGraphClient,
    MockGraphClient,
    appsecret_proof,
    currency_offset,
    usage_percent,
)

TOKEN = "EAAGsecretTokenForTests1234567890"
SECRET = "app-secret-for-tests"


def client(handler: Any, sleeps: list[float] | None = None) -> HttpGraphClient:
    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return HttpGraphClient(
        version="v99.0",
        app_id="123",
        app_secret=SECRET,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
    )


async def test_token_goes_in_header_with_appsecret_proof() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "1", "name": "Dashboard"})

    assert await client(handler).me_name(TOKEN) == "Dashboard"
    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(request.url)
    assert request.url.params["appsecret_proof"] == appsecret_proof(TOKEN, SECRET)
    assert request.url.path == "/v99.0/me"


async def test_rate_limit_is_retried_with_backoff() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(
                400, json={"error": {"code": 17, "message": "User request limit reached"}}
            )
        return httpx.Response(200, json={"data": [], "paging": {}})

    sleeps: list[float] = []
    assert await client(handler, sleeps).pages(TOKEN) == []
    assert calls == 3 and sleeps == [2, 4]


async def test_rate_limit_gives_up_after_max_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with pytest.raises(GraphError) as exc:
        await client(handler, []).pages(TOKEN)
    assert exc.value.kind == "rate_limit"


async def test_invalid_token_is_not_retried_and_never_leaks() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"code": 190, "message": f"Bad token {TOKEN}"}})

    with pytest.raises(GraphError) as exc:
        await client(handler, []).pages(TOKEN)
    assert exc.value.kind == "invalid_token" and calls == 1
    assert TOKEN not in str(exc.value) and TOKEN not in repr(exc.value)


async def test_network_error_never_leaks_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    with pytest.raises(GraphError) as exc:
        await client(handler, []).inspect_token(TOKEN)
    assert exc.value.kind == "network"
    assert TOKEN not in str(exc.value)


async def test_high_usage_header_slows_down() -> None:
    usage = {"123": [{"type": "pages", "call_count": 85, "total_cputime": 10, "total_time": 12}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "1", "name": "x"},
            headers={"X-Business-Use-Case-Usage": json.dumps(usage)},
        )

    sleeps: list[float] = []
    graph = client(handler, sleeps)
    await graph.me_name(TOKEN)
    assert sleeps == [5]
    assert graph.last_usage == {"x-business-use-case-usage": usage}
    assert usage_percent(httpx.Headers({"x-app-usage": json.dumps({"call_count": 12})}))[0] == 12


async def test_pages_follow_cursor_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("after") == "c1":
            return httpx.Response(
                200, json={"data": [{"id": "2", "name": "B", "access_token": "p2"}], "paging": {}}
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": "1", "name": "A", "access_token": "p1"}],
                "paging": {"cursors": {"after": "c1"}, "next": "x"},
            },
        )

    pages = await client(handler).pages(TOKEN)
    assert [p.id for p in pages] == ["1", "2"]
    assert "p1" not in repr(pages[0])  # mã Trang không hiện khi in đối tượng


async def test_debug_token_reads_scopes_and_business() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer 123|{SECRET}"
        return httpx.Response(
            200,
            json={
                "data": {
                    "is_valid": True,
                    "user_id": "61000",
                    "scopes": ["pages_messaging", "business_management"],
                    "granular_scopes": [{"scope": "business_management", "target_ids": ["900"]}],
                }
            },
        )

    info = await client(handler).inspect_token(TOKEN)
    assert info.is_valid and info.system_user_id == "61000"
    assert info.business_ids == ("900",)


async def test_subscribe_page_posts_webhook_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert (
            request.url.params["subscribed_fields"]
            == "messages,message_echoes,messaging_referrals,leadgen,feed"
        )
        return httpx.Response(200, json={"success": True})

    assert await client(handler).subscribe_page("100", "page-token") is True


async def test_mock_client() -> None:
    mock = MockGraphClient()
    with pytest.raises(GraphError) as exc:
        await mock.inspect_token("MOCK-INVALID")
    assert exc.value.kind == "invalid_token"
    info = await mock.inspect_token("MOCK-BM-2")
    assert info.business_ids == ("900000000000002",)
    pages = await mock.pages("MOCK-BM-2")
    assert [p.name for p in pages] == ["[Trang demo 5]", "[Trang demo 6]", "[Trang demo 7]"]
    assert await mock.subscribe_page(pages[0].id, pages[0].access_token or "")
    assert "leads_retrieval" not in (await mock.inspect_token("MOCK-BM-NOLEADS")).scopes


# ---------------------------------------------------------------- Bước 7


async def test_insights_parse_spend_and_actions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v99.0/act_1/insights"
        assert request.url.params["level"] == "campaign"
        assert request.url.params["time_increment"] == "1"
        assert json.loads(request.url.params["time_range"]) == {
            "since": "2026-10-01",
            "until": "2026-10-02",
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "campaign_id": "c1",
                        "date_start": "2026-10-01",
                        "spend": "12.34",
                        "impressions": "1000",
                        "reach": "800",
                        "clicks": "20",
                        "actions": [
                            {
                                "action_type": MESSAGING_ACTION,
                                "value": "7",
                            },
                            {"action_type": "lead", "value": "3"},
                            {"action_type": "onsite_conversion.lead_grouped", "value": "3"},
                        ],
                    }
                ],
                "paging": {},
            },
        )

    rows = await client(handler).insights(
        TOKEN, "act_1", "campaign", dt.date(2026, 10, 1), dt.date(2026, 10, 2)
    )
    row = rows[0]
    assert row.object_id == "c1" and row.date == dt.date(2026, 10, 1)
    assert row.spend == Decimal("12.34") and row.impressions == 1000
    # "lead" và "lead_grouped" là cùng một khách: không cộng hai lần.
    assert (row.messaging_starts, row.leads) == (7, 3)


def test_currency_offset() -> None:
    assert currency_offset("VND") == 1 and currency_offset("usd") == 100
    assert currency_offset(None) == 100


async def test_ads_read_page_from_creative() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "a1",
                        "name": "QC 1",
                        "adset_id": "s1",
                        "campaign_id": "c1",
                        "creative": {"effective_object_story_id": "555_999"},
                    },
                    {
                        "id": "a2",
                        "name": "QC 2",
                        "adset_id": "s1",
                        "campaign_id": "c1",
                        "creative": {"object_story_spec": {"page_id": "777"}},
                    },
                ]
            },
        )

    ads = await client(handler).ads(TOKEN, "act_1")
    assert [a.page_id for a in ads] == ["555", "777"]


async def test_page_posts_fall_back_without_view_metric() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fields = request.url.params["fields"]
        calls.append(fields)
        if "insights" in fields:
            return httpx.Response(400, json={"error": {"code": 100, "message": "bad metric"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "p_1",
                        "created_time": "2026-10-10T05:00:00+0000",
                        "message": "Xin chào",
                        "attachments": {"data": [{"media_type": "video"}]},
                        "shares": {"count": 4},
                        "reactions": {"summary": {"total_count": 9}},
                        "comments": {"summary": {"total_count": 2}},
                    }
                ]
            },
        )

    posts = await client(handler).page_posts(
        "100", "page-token", dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
    )
    assert len(calls) == 2
    post = posts[0]
    assert (post.type, post.reactions, post.comments, post.shares) == ("video", 9, 2, 4)
    assert post.views is None
    assert post.created_time == dt.datetime(2026, 10, 10, 5, tzinfo=dt.UTC)


async def test_page_insights_skip_rejected_metric() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        metric = request.url.params["metric"]
        if metric != "page_media_view":
            return httpx.Response(400, json={"error": {"code": 100, "message": "invalid metric"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": metric,
                        "values": [
                            {"value": 120, "end_time": "2026-10-02T07:00:00+0000"},
                            {"value": 150, "end_time": "2026-10-03T07:00:00+0000"},
                        ],
                    }
                ]
            },
        )

    days = await client(handler).page_insights(
        "100", "page-token", dt.date(2026, 10, 1), dt.date(2026, 10, 2)
    )
    assert [(d.date, d.views, d.reach) for d in days] == [
        (dt.date(2026, 10, 1), 120, None),
        (dt.date(2026, 10, 2), 150, None),
    ]


async def test_mock_insights_add_up_across_levels() -> None:
    mock = MockGraphClient()
    today = dt.date.today()
    since = today - dt.timedelta(days=3)
    totals = {
        level: sum(
            r.spend
            for r in await mock.insights("MOCK-BM-1", "act_200000000000001", level, since, today)
        )
        for level in ("campaign", "adset", "ad")
    }
    assert len(set(totals.values())) == 1 and totals["ad"] > 0
    # Lần chạy sau cho cùng số liệu.
    again = await mock.insights("MOCK-BM-1", "act_200000000000001", "ad", since, today)
    assert sum(r.spend for r in again) == totals["ad"]
    with pytest.raises(GraphError):
        await mock.insights("MOCK-BM-2", "act_200000000000001", "ad", since, today)
