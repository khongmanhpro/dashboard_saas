"""Webhook Meta: `GET /webhooks/meta` để xác minh, `POST /webhooks/meta` để nhận sự kiện.

POST chỉ làm ba việc: kiểm tra chữ ký, đẩy payload vào hàng đợi, trả 200. Mọi xử lý nằm ở
worker (`app.workers.webhook`). Không ghi nội dung payload vào log.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from redis.exceptions import RedisError

from app.api.deps import api_error
from app.core.config import get_settings
from app.core.queue import get_queue
from app.meta.events import WebhookPayload
from app.meta.signature import SIGNATURE_HEADER, verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)

PROCESS_JOB = "process_webhook"
MAX_BODY_BYTES = 1_000_000
MAX_CHALLENGE_LENGTH = 200


@router.get("/meta", response_class=PlainTextResponse)
async def verify_subscription(
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    verify_token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge", max_length=MAX_CHALLENGE_LENGTH)] = "",
) -> str:
    expected = get_settings().meta_webhook_verify_token.get_secret_value()
    if (
        mode != "subscribe"
        or not expected
        or not hmac.compare_digest(verify_token.encode(), expected.encode())
    ):
        raise api_error(403, "webhook_verify_failed")
    return challenge


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise api_error(413, "payload_too_large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise api_error(413, "payload_too_large")
    return bytes(body)


@router.post("/meta", response_class=PlainTextResponse)
async def receive_event(request: Request) -> str:
    secret = get_settings().meta_app_secret.get_secret_value()
    if not secret:
        log.error("META_APP_SECRET chưa cấu hình, từ chối webhook")
        raise api_error(503, "webhook_not_configured")
    body = await _read_body(request)
    if not verify_signature(body, request.headers.get(SIGNATURE_HEADER), secret):
        log.warning("webhook sai chữ ký")
        raise api_error(403, "invalid_signature")
    try:
        payload: Any = json.loads(body)
    except ValueError:
        raise api_error(400, "invalid_json") from None
    if not isinstance(payload, dict):
        raise api_error(400, "invalid_json")

    # Cùng một body gửi lại (Meta retry) thì arq bỏ qua; worker còn chặn lặp theo mid/leadgen_id.
    job_id = "wh:" + hashlib.sha256(body).hexdigest()
    try:
        queue = await get_queue()
        await queue.enqueue_job(PROCESS_JOB, WebhookPayload(payload), _job_id=job_id)
    except (RedisError, OSError):
        log.exception("không đẩy được webhook vào hàng đợi")
        raise api_error(503, "queue_unavailable") from None
    log.info(
        "nhận webhook",
        extra={
            "ctx": {"object": payload.get("object"), "entries": len(payload.get("entry") or [])}
        },
    )
    return "EVENT_RECEIVED"
