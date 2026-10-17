"""Gọi Graph API của Meta (Bước 6). Có client thật (httpx) và client giả cho MOCK_MODE.

Bảo mật (decisions.md mục H):
- Mã gửi qua header `Authorization: Bearer`, không đặt trong URL; kèm `appsecret_proof`.
- Riêng `debug_token` của Meta bắt buộc mã nằm trong tham số `input_token`: lỗi HTTP luôn được đổi
  thành `GraphError` không chứa URL, nên mã không lọt vào log hay thông báo lỗi.
- Không bao giờ ghi mã vào log.

Giới hạn gọi API: đọc `X-Business-Use-Case-Usage` / `X-App-Usage`, lùi lại khi dùng quá 80%;
lỗi giới hạn (429, mã 4/17/32/613) hoặc lỗi máy chủ thì thử lại có backoff.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

REQUIRED_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "read_insights",
    "pages_read_user_content",
    "pages_messaging",
    "pages_manage_metadata",
    "leads_retrieval",
    "ads_read",
    "business_management",
)
# Thiếu một trong các quyền này thì không đo được gì: không cho lưu BM.
ESSENTIAL_SCOPES = ("pages_show_list", "pages_messaging", "pages_manage_metadata")
WEBHOOK_FIELDS = ("messages", "message_echoes", "messaging_referrals", "leadgen", "feed")
RATE_LIMIT_CODES = {4, 17, 32, 613}
INVALID_TOKEN_CODES = {190, 102}
PERMISSION_CODES = {10, 200, 3, 294}
USAGE_BACKOFF_PERCENT = 80
MAX_ATTEMPTS = 4


class GraphError(Exception):
    """Lỗi từ Meta, đã bỏ mọi chi tiết có thể chứa mã. `kind`: invalid_token | permission |
    rate_limit | not_found | network | other."""

    def __init__(self, kind: str, code: int | None = None, status: int | None = None) -> None:
        super().__init__(f"graph_{kind}" + (f"_{code}" if code is not None else ""))
        self.kind = kind
        self.code = code
        self.status = status


@dataclass(frozen=True)
class TokenInfo:
    is_valid: bool
    system_user_id: str | None
    scopes: tuple[str, ...]
    business_ids: tuple[str, ...]


@dataclass(frozen=True)
class BusinessInfo:
    id: str
    name: str
    verification_status: str | None


@dataclass(frozen=True)
class PageInfo:
    id: str
    name: str
    category: str | None
    access_token: str | None = field(repr=False, default=None)


@dataclass(frozen=True)
class AdAccountInfo:
    id: str
    name: str
    currency: str | None
    timezone_name: str | None
    account_status: int | None


@dataclass(frozen=True)
class LeadDetails:
    field_data: list[dict[str, Any]]
    form_id: str | None
    ad_id: str | None


class GraphClient(Protocol):
    last_usage: dict[str, Any] | None

    async def inspect_token(self, token: str) -> TokenInfo: ...
    async def business(self, token: str, business_id: str) -> BusinessInfo: ...
    async def me_name(self, token: str) -> str | None: ...
    async def pages(self, token: str) -> list[PageInfo]: ...
    async def ad_accounts(self, token: str) -> list[AdAccountInfo]: ...
    async def subscribe_page(self, page_id: str, page_token: str) -> bool: ...
    async def lead(self, leadgen_id: str, page_token: str) -> LeadDetails: ...
    async def user_name(self, psid: str, page_token: str) -> str | None: ...


def appsecret_proof(token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def usage_percent(headers: httpx.Headers) -> tuple[int, dict[str, Any]]:
    """Mức dùng cao nhất (%) trong các header giới hạn của Meta."""
    usage: dict[str, Any] = {}
    peak = 0
    for name in ("x-business-use-case-usage", "x-app-usage", "x-ad-account-usage"):
        raw = headers.get(name)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        usage[name] = parsed
        buckets = (
            [v for values in parsed.values() for v in values]
            if name == "x-business-use-case-usage" and isinstance(parsed, dict)
            else [parsed]
        )
        for bucket in buckets:
            if isinstance(bucket, dict):
                for key in ("call_count", "total_cputime", "total_time", "acc_id_util_pct"):
                    value = bucket.get(key)
                    if isinstance(value, int | float):
                        peak = max(peak, int(value))
    return peak, usage


def _classify(status: int, body: Any) -> GraphError:
    error = body.get("error", {}) if isinstance(body, dict) else {}
    code = error.get("code") if isinstance(error, dict) else None
    code = int(code) if isinstance(code, int) else None
    if status == 429 or code in RATE_LIMIT_CODES:
        return GraphError("rate_limit", code, status)
    if code in INVALID_TOKEN_CODES or status == 401:
        return GraphError("invalid_token", code, status)
    if code in PERMISSION_CODES or status == 403:
        return GraphError("permission", code, status)
    if status == 404 or code == 100:
        return GraphError("not_found", code, status)
    return GraphError("other", code, status)


class HttpGraphClient:
    def __init__(
        self,
        *,
        version: str,
        app_id: str,
        app_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base = f"https://graph.facebook.com/{version}"
        self._app_id = app_id
        self._app_secret = app_secret
        self._transport = transport
        self._sleep = sleep
        self.last_usage: dict[str, Any] | None = None

    async def _get(
        self, path: str, token: str, params: dict[str, Any] | None = None, *, method: str = "GET"
    ) -> Any:
        query = {**(params or {}), "appsecret_proof": appsecret_proof(token, self._app_secret)}
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(transport=self._transport, timeout=20) as http:
                    response = await http.request(
                        method, f"{self._base}/{path.lstrip('/')}", params=query, headers=headers
                    )
            except httpx.HTTPError:
                error = GraphError("network")
            else:
                peak, usage = usage_percent(response.headers)
                if usage:
                    self.last_usage = usage
                if peak >= USAGE_BACKOFF_PERCENT:
                    await self._sleep(min(60, 5 * attempt))
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if response.is_success:
                    return body
                error = _classify(response.status_code, body)
                if error.kind not in ("rate_limit", "other") or (
                    error.kind == "other" and response.status_code < 500
                ):
                    raise error
            if attempt == MAX_ATTEMPTS:
                raise error
            await self._sleep(2**attempt)
        raise GraphError("other")  # pragma: no cover

    async def _paged(self, path: str, token: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        after: str | None = None
        for _ in range(50):  # tối đa 50 trang kết quả
            body = await self._get(
                path, token, {**params, "limit": 100, **({"after": after} if after else {})}
            )
            items.extend(body.get("data", []))
            after = (
                body.get("paging", {}).get("cursors", {}).get("after")
                if body.get("paging", {}).get("next")
                else None
            )
            if not after:
                break
        return items

    async def inspect_token(self, token: str) -> TokenInfo:
        app_token = f"{self._app_id}|{self._app_secret}"
        body = await self._get("debug_token", app_token, {"input_token": token})
        data = body.get("data", {})
        granular = data.get("granular_scopes") or []
        business_ids = tuple(
            str(t)
            for g in granular
            if g.get("scope") == "business_management"
            for t in g.get("target_ids", [])
        )
        return TokenInfo(
            is_valid=bool(data.get("is_valid")),
            system_user_id=str(data["user_id"]) if data.get("user_id") else None,
            scopes=tuple(data.get("scopes") or ()),
            business_ids=business_ids,
        )

    async def business(self, token: str, business_id: str) -> BusinessInfo:
        body = await self._get(business_id, token, {"fields": "id,name,verification_status"})
        return BusinessInfo(
            id=str(body["id"]),
            name=str(body.get("name") or business_id),
            verification_status=body.get("verification_status"),
        )

    async def me_name(self, token: str) -> str | None:
        body = await self._get("me", token, {"fields": "id,name"})
        name = body.get("name")
        return str(name) if name else None

    async def pages(self, token: str) -> list[PageInfo]:
        rows = await self._paged("me/accounts", token, {"fields": "id,name,category,access_token"})
        return [
            PageInfo(
                id=str(r["id"]),
                name=str(r.get("name") or r["id"]),
                category=r.get("category"),
                access_token=r.get("access_token"),
            )
            for r in rows
        ]

    async def ad_accounts(self, token: str) -> list[AdAccountInfo]:
        rows = await self._paged(
            "me/adaccounts", token, {"fields": "id,name,currency,timezone_name,account_status"}
        )
        return [
            AdAccountInfo(
                id=str(r["id"]),
                name=str(r.get("name") or r["id"]),
                currency=r.get("currency"),
                timezone_name=r.get("timezone_name"),
                account_status=r.get("account_status"),
            )
            for r in rows
        ]

    async def subscribe_page(self, page_id: str, page_token: str) -> bool:
        body = await self._get(
            f"{page_id}/subscribed_apps",
            page_token,
            {"subscribed_fields": ",".join(WEBHOOK_FIELDS)},
            method="POST",
        )
        return bool(body.get("success"))

    async def lead(self, leadgen_id: str, page_token: str) -> LeadDetails:
        body = await self._get(
            leadgen_id, page_token, {"fields": "field_data,form_id,ad_id,created_time"}
        )
        return LeadDetails(
            field_data=list(body.get("field_data") or []),
            form_id=body.get("form_id"),
            ad_id=body.get("ad_id"),
        )

    async def user_name(self, psid: str, page_token: str) -> str | None:
        try:
            body = await self._get(psid, page_token, {"fields": "name"})
        except GraphError:
            return None  # Meta không cho đọc tên: giữ "Khách ···1234"
        name = body.get("name")
        return str(name)[:200] if name else None


# ---------------------------------------------------------------- client giả cho MOCK_MODE

MOCK_FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "meta" / "graph_mock.json"
)


@lru_cache
def _mock_data() -> dict[str, Any]:
    if not MOCK_FIXTURE.exists():
        return {"tokens": {}}
    data: dict[str, Any] = json.loads(MOCK_FIXTURE.read_text("utf-8"))
    return data


class MockGraphClient:
    """Đọc `tests/fixtures/meta/graph_mock.json`. Mã giả dạng `MOCK-...`, không phải mã thật."""

    def __init__(self) -> None:
        self.last_usage: dict[str, Any] | None = None
        self.subscribed: list[str] = []

    def _account(self, token: str) -> dict[str, Any]:
        account = _mock_data()["tokens"].get(token)
        if account is None:
            raise GraphError("invalid_token", 190, 400)
        return dict(account)

    def _page_owner(self, page_token: str) -> dict[str, Any]:
        for account in _mock_data()["tokens"].values():
            for page in account.get("pages", []):
                if f"MOCK-PAGE-{page['id']}" == page_token:
                    return dict(page)
        raise GraphError("invalid_token", 190, 400)

    async def inspect_token(self, token: str) -> TokenInfo:
        account = self._account(token)
        return TokenInfo(
            is_valid=True,
            system_user_id=account["system_user"]["id"],
            scopes=tuple(account["scopes"]),
            business_ids=(account["business"]["id"],),
        )

    async def business(self, token: str, business_id: str) -> BusinessInfo:
        b = self._account(token)["business"]
        return BusinessInfo(
            id=b["id"], name=b["name"], verification_status=b.get("verification_status")
        )

    async def me_name(self, token: str) -> str | None:
        return str(self._account(token)["system_user"]["name"])

    async def pages(self, token: str) -> list[PageInfo]:
        return [
            PageInfo(
                id=p["id"],
                name=p["name"],
                category=p.get("category"),
                access_token=f"MOCK-PAGE-{p['id']}",
            )
            for p in self._account(token).get("pages", [])
        ]

    async def ad_accounts(self, token: str) -> list[AdAccountInfo]:
        return [
            AdAccountInfo(
                id=a["id"],
                name=a["name"],
                currency=a.get("currency"),
                timezone_name=a.get("timezone_name"),
                account_status=1,
            )
            for a in self._account(token).get("ad_accounts", [])
        ]

    async def subscribe_page(self, page_id: str, page_token: str) -> bool:
        self._page_owner(page_token)
        self.subscribed.append(page_id)
        return True

    async def lead(self, leadgen_id: str, page_token: str) -> LeadDetails:
        self._page_owner(page_token)
        forms = {
            k: v
            for k, v in json.loads(
                (MOCK_FIXTURE.parent / "leadgen_forms.json").read_text("utf-8")
            ).items()
            if not k.startswith("_")
        }
        form_id, form = next(iter(forms.items()))
        return LeadDetails(field_data=form["field_data"], form_id=form_id, ad_id=None)

    async def user_name(self, psid: str, page_token: str) -> str | None:
        self._page_owner(page_token)
        return f"[Khách {psid[-4:]}]"


_override: GraphClient | None = None


def get_graph() -> GraphClient:
    """Client dùng chung. MOCK_MODE thì client giả; test có thể thay bằng `set_graph`."""
    if _override is not None:
        return _override
    s = get_settings()
    if s.mock_mode:
        return MockGraphClient()
    if not (s.meta_graph_version and s.meta_app_id and s.meta_app_secret.get_secret_value()):
        raise GraphError("not_configured")
    return HttpGraphClient(
        version=s.meta_graph_version,
        app_id=s.meta_app_id,
        app_secret=s.meta_app_secret.get_secret_value(),
    )


def set_graph(client: GraphClient | None) -> None:
    global _override
    _override = client
