"""Endpoint webhook: xác minh, chữ ký, đẩy vào hàng đợi."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from app.api.webhooks import MAX_BODY_BYTES, PROCESS_JOB
from app.core.config import get_settings
from app.core.queue import close_queue, get_queue
from app.meta.signature import SIGNATURE_HEADER, sign

pytestmark = pytest.mark.integration

PAYLOAD = {"object": "page", "entry": [{"id": "100000000000001", "time": 1, "messaging": []}]}


@pytest.fixture(autouse=True)
async def _fresh_queue() -> AsyncIterator[None]:
    yield
    await close_queue()


def _body(payload: object = PAYLOAD) -> bytes:
    return json.dumps(payload).encode()


async def _post(client: httpx.AsyncClient, body: bytes, signature: str | None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers[SIGNATURE_HEADER] = signature
    return await client.post("/webhooks/meta", content=body, headers=headers)


def _secret() -> str:
    return get_settings().meta_app_secret.get_secret_value()


async def test_verify_returns_challenge(client: httpx.AsyncClient) -> None:
    token = get_settings().meta_webhook_verify_token.get_secret_value()
    resp = await client.get(
        "/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "1158201444"},
    )
    assert resp.status_code == 200
    assert resp.text == "1158201444"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "sai", "hub.challenge": "1"},
        {"hub.mode": "unsubscribe", "hub.verify_token": "__TOKEN__", "hub.challenge": "1"},
        {"hub.challenge": "1"},
    ],
)
async def test_verify_rejects_wrong_token_or_mode(
    client: httpx.AsyncClient, params: dict[str, str]
) -> None:
    token = get_settings().meta_webhook_verify_token.get_secret_value()
    params = {k: (token if v == "__TOKEN__" else v) for k, v in params.items()}
    resp = await client.get("/webhooks/meta", params=params)
    assert resp.status_code == 403


async def test_valid_post_is_enqueued(client: httpx.AsyncClient) -> None:
    body = _body()
    resp = await _post(client, body, sign(body, _secret()))
    assert resp.status_code == 200
    assert resp.text == "EVENT_RECEIVED"
    jobs = await (await get_queue()).queued_jobs()
    assert len(jobs) == 1
    assert jobs[0].function == PROCESS_JOB
    assert jobs[0].args == (PAYLOAD,)


async def test_same_body_twice_is_enqueued_once(client: httpx.AsyncClient) -> None:
    body = _body()
    for _ in range(2):
        assert (await _post(client, body, sign(body, _secret()))).status_code == 200
    assert len(await (await get_queue()).queued_jobs()) == 1


@pytest.mark.parametrize("signature", [None, "", "sha256=00", "sha1=abc"])
async def test_bad_signature_is_403_and_not_enqueued(
    client: httpx.AsyncClient, signature: str | None
) -> None:
    resp = await _post(client, _body(), signature)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "invalid_signature"
    assert await (await get_queue()).queued_jobs() == []


async def test_signature_of_other_body_is_403(client: httpx.AsyncClient) -> None:
    resp = await _post(client, _body(), sign(_body({"object": "page"}), _secret()))
    assert resp.status_code == 403


async def test_missing_app_secret_refuses(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "meta_app_secret", SecretStr(""))
    body = _body()
    resp = await _post(client, body, sign(body, ""))
    assert resp.status_code == 503
    assert await (await get_queue()).queued_jobs() == []


async def test_oversized_body_is_rejected(client: httpx.AsyncClient) -> None:
    body = b"{" + b" " * MAX_BODY_BYTES + b"}"
    resp = await _post(client, body, sign(body, _secret()))
    assert resp.status_code == 413


async def test_signed_but_invalid_json_is_400(client: httpx.AsyncClient) -> None:
    body = b"not json"
    resp = await _post(client, body, sign(body, _secret()))
    assert resp.status_code == 400


async def test_payload_is_not_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    payload = {
        "object": "page",
        "entry": [{"id": "1", "messaging": [{"message": {"text": "[bí mật]"}}]}],
    }
    body = _body(payload)
    with caplog.at_level("DEBUG"):
        assert (await _post(client, body, sign(body, _secret()))).status_code == 200
    assert "[bí mật]" not in caplog.text
