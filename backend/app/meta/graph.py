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
import datetime as dt
import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

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


@dataclass(frozen=True)
class CampaignInfo:
    id: str
    name: str
    objective: str | None
    status: str | None
    daily_budget_minor: int | None


@dataclass(frozen=True)
class AdSetInfo:
    id: str
    campaign_id: str
    name: str
    status: str | None
    daily_budget_minor: int | None


@dataclass(frozen=True)
class AdInfo:
    id: str
    adset_id: str
    campaign_id: str
    name: str
    status: str | None
    page_id: str | None


@dataclass(frozen=True)
class InsightRow:
    """Một ngày của một đối tượng. `spend` theo đơn vị chính của tiền tệ tài khoản (như Meta)."""

    object_id: str
    campaign_id: str
    date: dt.date
    spend: Decimal
    impressions: int
    reach: int
    clicks: int
    messaging_starts: int
    leads: int


@dataclass(frozen=True)
class PostInfo:
    id: str
    created_time: dt.datetime
    type: str
    message: str | None
    permalink: str | None
    reactions: int
    comments: int
    shares: int
    views: int | None


@dataclass(frozen=True)
class PageDayInsight:
    date: dt.date
    followers: int | None = None
    new_follows: int | None = None
    views: int | None = None
    reach: int | None = None
    engagements: int | None = None
    video_views: int | None = None


INSIGHT_FIELDS = "campaign_id,adset_id,ad_id,spend,impressions,reach,clicks,actions"
MESSAGING_ACTION = "onsite_conversion.messaging_conversation_started_7d"
LEAD_ACTIONS = ("lead", "onsite_conversion.lead_grouped")
# Tên metric Trang trên Graph API → cột `page_insights_daily`. Kiểm lại khi ứng dụng Live
# (decisions.md mục I): metric nào Meta từ chối thì bỏ qua, cột đó để NULL.
PAGE_METRICS = {
    "page_follows": "followers",
    "page_daily_follows_unique": "new_follows",
    "page_media_view": "views",
    "page_impressions_unique": "reach",
    "page_post_engagements": "engagements",
    "page_video_views": "video_views",
}
POST_TYPES = {"photo": "photo", "video": "video", "reel": "reel", "share": "link", "link": "link"}
# Tiền tệ không có đơn vị lẻ trên Meta (offset 1); còn lại offset 100.
ZERO_DECIMAL_CURRENCIES = frozenset(
    {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}
)


def currency_offset(currency: str | None) -> int:
    return 1 if (currency or "").upper() in ZERO_DECIMAL_CURRENCIES else 100


def _int(value: Any) -> int:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return 0


def _actions(actions: Any) -> tuple[int, int]:
    """(tin nhắn bắt đầu, khách tiềm năng) từ danh sách `actions` của insights."""
    found: dict[str, int] = {}
    for a in actions or []:
        if isinstance(a, dict) and a.get("action_type"):
            found[str(a["action_type"])] = _int(a.get("value"))
    leads = next((found[k] for k in LEAD_ACTIONS if k in found), 0)
    return found.get(MESSAGING_ACTION, 0), leads


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
    async def campaigns(self, token: str, account_id: str) -> list[CampaignInfo]: ...
    async def ad_sets(self, token: str, account_id: str) -> list[AdSetInfo]: ...
    async def ads(self, token: str, account_id: str) -> list[AdInfo]: ...
    async def insights(
        self, token: str, account_id: str, level: str, since: dt.date, until: dt.date
    ) -> list[InsightRow]: ...
    async def page_posts(
        self, page_id: str, page_token: str, since: dt.datetime
    ) -> list[PostInfo]: ...
    async def page_insights(
        self, page_id: str, page_token: str, since: dt.date, until: dt.date
    ) -> list[PageDayInsight]: ...


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

    async def campaigns(self, token: str, account_id: str) -> list[CampaignInfo]:
        rows = await self._paged(
            f"{account_id}/campaigns",
            token,
            {"fields": "id,name,objective,effective_status,daily_budget"},
        )
        return [
            CampaignInfo(
                id=str(r["id"]),
                name=str(r.get("name") or r["id"]),
                objective=r.get("objective"),
                status=r.get("effective_status"),
                daily_budget_minor=_int(r["daily_budget"]) if r.get("daily_budget") else None,
            )
            for r in rows
        ]

    async def ad_sets(self, token: str, account_id: str) -> list[AdSetInfo]:
        rows = await self._paged(
            f"{account_id}/adsets",
            token,
            {"fields": "id,name,campaign_id,effective_status,daily_budget"},
        )
        return [
            AdSetInfo(
                id=str(r["id"]),
                campaign_id=str(r["campaign_id"]),
                name=str(r.get("name") or r["id"]),
                status=r.get("effective_status"),
                daily_budget_minor=_int(r["daily_budget"]) if r.get("daily_budget") else None,
            )
            for r in rows
        ]

    async def ads(self, token: str, account_id: str) -> list[AdInfo]:
        rows = await self._paged(
            f"{account_id}/ads",
            token,
            {
                "fields": "id,name,adset_id,campaign_id,effective_status,"
                "creative{effective_object_story_id,object_story_spec}"
            },
        )
        result: list[AdInfo] = []
        for r in rows:
            creative = r.get("creative") or {}
            spec = creative.get("object_story_spec") or {}
            story = str(creative.get("effective_object_story_id") or "")
            page_id = spec.get("page_id") or (story.split("_", 1)[0] if "_" in story else None)
            result.append(
                AdInfo(
                    id=str(r["id"]),
                    adset_id=str(r["adset_id"]),
                    campaign_id=str(r["campaign_id"]),
                    name=str(r.get("name") or r["id"]),
                    status=r.get("effective_status"),
                    page_id=str(page_id) if page_id else None,
                )
            )
        return result

    async def insights(
        self, token: str, account_id: str, level: str, since: dt.date, until: dt.date
    ) -> list[InsightRow]:
        rows = await self._paged(
            f"{account_id}/insights",
            token,
            {
                "level": level,
                "fields": INSIGHT_FIELDS,
                "time_increment": 1,
                "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
            },
        )
        key = {"campaign": "campaign_id", "adset": "adset_id", "ad": "ad_id"}[level]
        result: list[InsightRow] = []
        for r in rows:
            messaging, leads = _actions(r.get("actions"))
            try:
                spend = Decimal(str(r.get("spend") or "0"))
            except InvalidOperation:
                spend = Decimal(0)
            result.append(
                InsightRow(
                    object_id=str(r[key]),
                    campaign_id=str(r["campaign_id"]),
                    date=dt.date.fromisoformat(str(r["date_start"])),
                    spend=spend,
                    impressions=_int(r.get("impressions")),
                    reach=_int(r.get("reach")),
                    clicks=_int(r.get("clicks")),
                    messaging_starts=messaging,
                    leads=leads,
                )
            )
        return result

    async def page_posts(self, page_id: str, page_token: str, since: dt.datetime) -> list[PostInfo]:
        base = (
            "id,created_time,message,permalink_url,attachments{media_type},shares,"
            "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)"
        )
        params = {"since": int(since.timestamp())}
        try:
            rows = await self._paged(
                f"{page_id}/posts",
                page_token,
                {**params, "fields": base + ",insights.metric(post_media_view){values}"},
            )
        except GraphError as exc:
            if exc.kind not in ("not_found", "other", "permission"):
                raise
            # Metric lượt xem của bài chưa dùng được: vẫn lấy bài, để `views` NULL.
            rows = await self._paged(f"{page_id}/posts", page_token, {**params, "fields": base})
        result: list[PostInfo] = []
        for r in rows:
            attachments = (r.get("attachments") or {}).get("data") or [{}]
            media = str(attachments[0].get("media_type") or "status").lower()
            views = None
            for metric in (r.get("insights") or {}).get("data") or []:
                values = metric.get("values") or [{}]
                views = _int(values[0].get("value"))
            result.append(
                PostInfo(
                    id=str(r["id"]),
                    created_time=dt.datetime.fromisoformat(str(r["created_time"])),
                    type=POST_TYPES.get(media, "status"),
                    message=r.get("message"),
                    permalink=r.get("permalink_url"),
                    reactions=_int(
                        ((r.get("reactions") or {}).get("summary") or {}).get("total_count")
                    ),
                    comments=_int(
                        ((r.get("comments") or {}).get("summary") or {}).get("total_count")
                    ),
                    shares=_int((r.get("shares") or {}).get("count")),
                    views=views,
                )
            )
        return result

    async def page_insights(
        self, page_id: str, page_token: str, since: dt.date, until: dt.date
    ) -> list[PageDayInsight]:
        days: dict[dt.date, dict[str, int]] = {}
        for metric, column in PAGE_METRICS.items():
            try:
                body = await self._get(
                    f"{page_id}/insights",
                    page_token,
                    {
                        "metric": metric,
                        "period": "day",
                        "since": since.isoformat(),
                        "until": (until + dt.timedelta(days=1)).isoformat(),
                    },
                )
            except GraphError as exc:
                if exc.kind in ("rate_limit", "invalid_token", "network"):
                    raise
                continue  # metric không còn hoặc chưa được cấp: bỏ qua
            for series in body.get("data") or []:
                for v in series.get("values") or []:
                    end = dt.datetime.fromisoformat(str(v["end_time"]))
                    day = (end - dt.timedelta(days=1)).date()
                    days.setdefault(day, {})[column] = _int(v.get("value"))
        return [
            PageDayInsight(date=d, **values)
            for d, values in sorted(days.items())
            if since <= d <= until
        ]


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

    # ---- Bước 7: số liệu sinh từ tham số trong `content`, cố định theo (đối tượng, ngày).

    def _account_content(self, token: str, account_id: str) -> tuple[dict[str, Any], str]:
        for a in self._account(token).get("ad_accounts", []):
            if a["id"] == account_id:
                content = _mock_data().get("content", {}).get("ad_accounts", {})
                return dict(content.get(account_id, {"campaigns": []})), str(
                    a.get("timezone_name") or MOCK_TZ
                )
        raise GraphError("permission", 200, 403)

    async def campaigns(self, token: str, account_id: str) -> list[CampaignInfo]:
        content, _ = self._account_content(token, account_id)
        return [
            CampaignInfo(
                id=c["id"],
                name=c["name"],
                objective=c.get("objective"),
                status=c.get("status"),
                daily_budget_minor=c.get("daily_budget"),
            )
            for c in content["campaigns"]
        ]

    async def ad_sets(self, token: str, account_id: str) -> list[AdSetInfo]:
        content, _ = self._account_content(token, account_id)
        return [
            AdSetInfo(
                id=s["id"],
                campaign_id=c["id"],
                name=s["name"],
                status=c.get("status"),
                daily_budget_minor=s.get("daily_budget"),
            )
            for c in content["campaigns"]
            for s in c["adsets"]
        ]

    async def ads(self, token: str, account_id: str) -> list[AdInfo]:
        content, _ = self._account_content(token, account_id)
        return [
            AdInfo(
                id=a["id"],
                adset_id=s["id"],
                campaign_id=c["id"],
                name=a["name"],
                status=c.get("status"),
                page_id=a.get("page_id"),
            )
            for c in content["campaigns"]
            for s in c["adsets"]
            for a in s["ads"]
        ]

    async def insights(
        self, token: str, account_id: str, level: str, since: dt.date, until: dt.date
    ) -> list[InsightRow]:
        content, tz = self._account_content(token, account_id)
        currency = next(
            str(a.get("currency") or "VND")
            for a in self._account(token)["ad_accounts"]
            if a["id"] == account_id
        )
        offset = currency_offset(currency)
        today = dt.datetime.now(ZoneInfo(tz)).date()
        rows: list[InsightRow] = []
        day = max(since, today - dt.timedelta(days=MOCK_HISTORY_DAYS))
        while day <= min(until, today):
            for c in content["campaigns"]:
                paused = c.get("paused_days")
                if paused and day > today - dt.timedelta(days=int(paused)):
                    continue
                ads = [(s["id"], a["id"]) for s in c["adsets"] for a in s["ads"]]
                per_ad: list[tuple[str, str, dict[str, int]]] = []
                factor = _mock_jitter(c["id"], day)
                for adset_id, ad_id in ads:
                    share = _mock_jitter(ad_id, day) / len(ads)
                    metrics = {
                        k: round(v * factor * share * (1 if k == "spend" else _mock_jitter(k, day)))
                        for k, v in c["daily"].items()
                    }
                    per_ad.append((adset_id, ad_id, metrics))
                groups: dict[str, list[dict[str, int]]] = {}
                for adset_id, ad_id, metrics in per_ad:
                    key = {"ad": ad_id, "adset": adset_id, "campaign": c["id"]}[level]
                    groups.setdefault(key, []).append(metrics)
                for object_id, items in groups.items():
                    total = {k: sum(m[k] for m in items) for k in items[0]}
                    rows.append(
                        InsightRow(
                            object_id=object_id,
                            campaign_id=c["id"],
                            date=day,
                            spend=Decimal(total["spend"]) / offset,
                            impressions=total["impressions"],
                            reach=total["reach"],
                            clicks=total["clicks"],
                            messaging_starts=total["messaging"],
                            leads=total["leads"],
                        )
                    )
            day += dt.timedelta(days=1)
        return rows

    def _page_content(self, page_id: str, page_token: str) -> dict[str, Any] | None:
        self._page_owner(page_token)
        content: dict[str, Any] | None = (
            _mock_data().get("content", {}).get("pages", {}).get(page_id)
        )
        return content

    async def page_posts(self, page_id: str, page_token: str, since: dt.datetime) -> list[PostInfo]:
        cfg = self._page_content(page_id, page_token)
        if cfg is None:
            return []
        tz = ZoneInfo(MOCK_TZ)
        now = dt.datetime.now(dt.UTC)
        today = now.astimezone(tz).date()
        per_day = float(cfg["posts_per_week"]) / 7
        posts: list[PostInfo] = []
        day = max(since.astimezone(tz).date(), today - dt.timedelta(days=MOCK_HISTORY_DAYS))
        while day <= today:
            count = int(per_day + _mock_unit(page_id, day, "n"))
            for i in range(count):
                hour = 7 + int(_mock_unit(page_id, day, i, "h") * 15)
                created = dt.datetime.combine(day, dt.time(hour, 5 + 7 * i), tz).astimezone(dt.UTC)
                if created > now or created < since:
                    continue
                kind = MOCK_POST_TYPES[int(_mock_unit(page_id, day, i, "t") * len(MOCK_POST_TYPES))]
                trend = (1 + float(cfg.get("trend", 0))) ** -(today - day).days
                boost = 1.4 if 18 <= hour < 21 else 1.0
                views = round(
                    cfg["views"] * 0.25 * trend * boost * _mock_jitter(page_id, day, i, "v")
                )
                posts.append(
                    PostInfo(
                        id=f"{page_id}_{day:%Y%m%d}{i}",
                        created_time=created,
                        type=kind,
                        message=f"[Bài viết mẫu {day:%d/%m} số {i + 1}]",
                        permalink=f"https://www.facebook.com/{page_id}/posts/{day:%Y%m%d}{i}",
                        reactions=round(views * 0.05 * _mock_jitter(page_id, day, i, "r")),
                        comments=round(views * 0.012 * _mock_jitter(page_id, day, i, "c")),
                        shares=round(views * 0.004 * _mock_jitter(page_id, day, i, "s")),
                        views=views,
                    )
                )
            day += dt.timedelta(days=1)
        return posts

    async def page_insights(
        self, page_id: str, page_token: str, since: dt.date, until: dt.date
    ) -> list[PageDayInsight]:
        cfg = self._page_content(page_id, page_token)
        if cfg is None:
            return []
        today = dt.datetime.now(ZoneInfo(MOCK_TZ)).date()
        result: list[PageDayInsight] = []
        day = max(since, today - dt.timedelta(days=MOCK_HISTORY_DAYS))
        while day <= min(until, today):
            age = (today - day).days
            trend = (1 + float(cfg.get("trend", 0))) ** -age
            views = round(cfg["views"] * trend * _mock_jitter(page_id, day, "pv"))
            result.append(
                PageDayInsight(
                    date=day,
                    followers=round(cfg["followers"] * (1 - 0.002 * age)),
                    new_follows=round(cfg["followers"] * 0.002 * _mock_jitter(page_id, day, "f")),
                    views=views,
                    reach=round(views * 0.45),
                    engagements=round(views * 0.04 * _mock_jitter(page_id, day, "e")),
                    video_views=round(views * 0.18 * _mock_jitter(page_id, day, "vv")),
                )
            )
            day += dt.timedelta(days=1)
        return result


MOCK_TZ = "Asia/Ho_Chi_Minh"
MOCK_HISTORY_DAYS = 60
MOCK_POST_TYPES = ("photo", "photo", "video", "reel", "link")


def _mock_unit(*parts: Any) -> float:
    """Số trong [0, 1) cố định theo `parts`: dữ liệu giả giống nhau ở mọi lần chạy."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _mock_jitter(*parts: Any) -> float:
    return 0.75 + 0.5 * _mock_unit(*parts)


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
