"""Client Graph API: mã không nằm trong URL, appsecret_proof, thử lại, giới hạn gọi, client giả."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.meta.graph import (
    GraphError,
    HttpGraphClient,
    MockGraphClient,
    appsecret_proof,
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
