"""Cảnh báo Telegram (Bước 7, decisions.md mục I).

- Mỗi quy tắc × đối tượng × ngày gửi một lần (`alert_deliveries.dedupe_key`); lần gửi lỗi thì
  lần chạy sau thử lại.
- Nội dung không có SĐT, không có nội dung tin nhắn của khách.
- Chỉ cảnh báo, không tạm dừng hay đổi ngân sách quảng cáo (quyết định #7).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.config import get_settings
from app.core.rbac import Perm
from app.i18n import vi
from app.models import (
    AdInsightDaily,
    AlertDelivery,
    AlertRule,
    BusinessManager,
    ConnectionStatus,
    FxRate,
    Lead,
    Page,
    Workspace,
    WorkspaceSettings,
)
from app.schemas.alerts import (
    CHAT_ID,
    AlertSettingsOut,
    AlertSettingsUpdate,
    DeliveryOut,
    FxRateIn,
    FxRateOut,
    RuleOut,
    RulesView,
    TestResult,
)
from app.services import ads_service, audit, meta_sync
from app.services.alert_rules import PARAM_LIMITS, RULE_TYPES, effective_rules
from app.services.errors import ServiceError
from app.services.report_range import resolve_range
from app.services.telegram import TelegramError, TelegramSender, get_telegram

log = logging.getLogger(__name__)

SUMMARY_HOUR = 8  # tóm tắt hôm qua gửi từ 08:00 giờ workspace
RECENT_DELIVERIES = 20


def vnd(value: int | Decimal | None) -> str:
    if value is None:
        return vi.NO_VALUE
    return f"{int(value):,}".replace(",", ".") + " ₫"


def _link(path: str) -> str:
    return get_settings().app_base_url.rstrip("/") + path


# ---------------------------------------------------------------- gửi


async def deliver(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    chat_id: str,
    rule_type: str,
    dedupe_key: str,
    text: str,
    payload: dict[str, Any],
    now: dt.datetime,
    sender: TelegramSender,
) -> str | None:
    """Gửi một lần cho mỗi `dedupe_key`. Trả trạng thái, hoặc None nếu đã gửi trước đó."""
    stmt = (
        pg_insert(AlertDelivery)
        .values(
            workspace_id=workspace_id,
            rule_type=rule_type,
            dedupe_key=dedupe_key[:200],
            target=chat_id,
            payload=payload,
            status="failed",
            sent_at=now,
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "dedupe_key"])
        .returning(AlertDelivery.id)
    )
    row_id = (await db.execute(stmt)).scalar_one_or_none()
    if row_id is None:
        existing = await db.scalar(
            select(AlertDelivery).where(AlertDelivery.dedupe_key == dedupe_key[:200])
        )
        if existing is None or existing.status != "failed":
            return None
        row_id = existing.id
    row = await db.get(AlertDelivery, row_id)
    assert row is not None  # noqa: S101 — vừa thêm hoặc vừa đọc ở trên
    try:
        await sender.send(chat_id, text)
    except TelegramError as exc:
        row.status, row.error = "failed", exc.kind
        log.warning("gửi Telegram lỗi", extra={"ctx": {"rule": rule_type, "kind": exc.kind}})
    else:
        row.status, row.error = ("mock" if sender.is_mock else "sent"), None
    row.sent_at = now
    await db.flush()
    return row.status


async def _context(db: AsyncSession) -> tuple[str | None, str, str]:
    """(chat ID, tên workspace, múi giờ) của workspace hiện tại."""
    row = (
        await db.execute(
            select(WorkspaceSettings.telegram_chat_id, Workspace.name, Workspace.timezone).join(
                Workspace, Workspace.id == WorkspaceSettings.workspace_id
            )
        )
    ).first()
    if row is None:
        return None, "", "Asia/Ho_Chi_Minh"
    return row[0], row[1], row[2]


def _sender(sender: TelegramSender | None) -> TelegramSender | None:
    if sender is not None:
        return sender
    try:
        return get_telegram()
    except TelegramError:
        return None  # chưa cấu hình bot: bỏ qua, không làm hỏng job


async def notify_bm_status(
    db: AsyncSession,
    bm: BusinessManager,
    status: ConnectionStatus,
    now: dt.datetime,
    sender: TelegramSender | None = None,
) -> str | None:
    """Gọi từ job kiểm tra BM khi trạng thái xấu đi."""
    rules = await effective_rules(db)
    chat_id, _, _ = await _context(db)
    send = _sender(sender)
    if not rules["bm_status"].enabled or not chat_id or send is None:
        return None
    pages = int(
        await db.scalar(
            select(func.count()).where(Page.business_manager_id == bm.id, Page.is_tracked.is_(True))
        )
        or 0
    )
    key = "bm_disconnected" if status == ConnectionStatus.DISCONNECTED else "bm_missing_permissions"
    text = vi.ALERT_TEXTS[key].format(name=bm.name, pages=pages, link=_link("/bm"))
    return await deliver(
        db,
        bm.workspace_id,
        chat_id,
        "bm_status",
        f"bm_status:{bm.id}:{status.value}:{now.date().isoformat()}",
        text,
        {"bm_id": str(bm.id), "status": status.value},
        now,
        send,
    )


async def run_workspace(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    now: dt.datetime,
    sender: TelegramSender | None = None,
) -> dict[str, int]:
    """Kiểm tra các quy tắc QC và tóm tắt buổi sáng cho workspace hiện tại."""
    from zoneinfo import ZoneInfo

    counts = {"sent": 0, "failed": 0}
    chat_id, workspace_name, tz_name = await _context(db)
    send = _sender(sender)
    if not chat_id or send is None:
        return counts
    rules = await effective_rules(db)
    tz = ZoneInfo(tz_name)

    async def push(rule: str, key: str, text: str, payload: dict[str, Any]) -> None:
        status = await deliver(db, workspace_id, chat_id, rule, key, text, payload, now, send)
        if status is not None:
            counts["failed" if status == "failed" else "sent"] += 1

    today = resolve_range("today", tz, now)
    week = resolve_range("7d", tz, now)
    day_key = today.first_day.isoformat()
    link = _link("/ads")

    rule = rules["cost_per_result"]
    if rule.enabled:
        limit, min_spend = int(rule.params["max_vnd"]), int(rule.params["min_spend_vnd"])
        stats = await ads_service.level_stats(db, "campaign", today)
        flagged = [
            s
            for s in stats.values()
            if (s.spend_vnd or 0) >= min_spend
            and s.cost_per_result is not None
            and s.cost_per_result > limit
        ]
        found = await ads_service.names(db, "campaign", {s.object_id for s in flagged})
        for s in flagged:
            await push(
                "cost_per_result",
                f"cost_per_result:{s.object_id}:{day_key}",
                vi.ALERT_TEXTS["cost_per_result"].format(
                    name=found[s.object_id].name,
                    value=vnd(s.cost_per_result),
                    limit=vnd(limit),
                    spend=vnd(s.spend_vnd),
                    link=link,
                ),
                {"campaign_id": str(s.object_id), "value": s.cost_per_result},
            )

    week_stats = None
    rule = rules["cost_per_won"]
    if rule.enabled:
        limit = int(rule.params["max_vnd"])
        week_stats = await ads_service.level_stats(db, "campaign", week)
        flagged = [
            s
            for s in week_stats.values()
            if (s.spend_vnd or 0) > limit
            and (s.won == 0 or (s.cost_per_won is not None and s.cost_per_won > limit))
        ]
        found = await ads_service.names(db, "campaign", {s.object_id for s in flagged})
        for s in flagged:
            template = "cost_per_won_none" if s.won == 0 else "cost_per_won"
            await push(
                "cost_per_won",
                f"cost_per_won:{s.object_id}:{day_key}",
                vi.ALERT_TEXTS[template].format(
                    name=found[s.object_id].name,
                    value=vnd(s.cost_per_won),
                    limit=vnd(limit),
                    spend=vnd(s.spend_vnd),
                    won=s.won,
                    link=link,
                ),
                {"campaign_id": str(s.object_id), "value": s.cost_per_won, "won": s.won},
            )

    rule = rules["frequency"]
    if rule.enabled:
        limit_f = Decimal(str(rule.params["max"]))
        week_stats = week_stats or await ads_service.level_stats(db, "campaign", week)
        flagged = [
            s for s in week_stats.values() if s.frequency is not None and s.frequency > limit_f
        ]
        found = await ads_service.names(db, "campaign", {s.object_id for s in flagged})
        for s in flagged:
            await push(
                "frequency",
                f"frequency:{s.object_id}:{day_key}",
                vi.ALERT_TEXTS["frequency"].format(
                    name=found[s.object_id].name,
                    value=str(s.frequency).replace(".", ","),
                    limit=str(limit_f).replace(".", ","),
                    link=link,
                ),
                {"campaign_id": str(s.object_id), "value": str(s.frequency)},
            )

    local_now = now.astimezone(tz)
    if rules["daily_summary"].enabled and local_now.hour >= SUMMARY_HOUR:
        yesterday = today.previous()
        await push(
            "daily_summary",
            f"daily_summary:{yesterday.first_day.isoformat()}",
            await _summary_text(db, workspace_name, yesterday, now),
            {"date": yesterday.first_day.isoformat()},
        )
    return counts


async def _summary_text(db: AsyncSession, workspace_name: str, r: Any, now: dt.datetime) -> str:
    from app.models import LeadStatus

    won = Lead.status == LeadStatus.WON
    row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(won),
                func.coalesce(func.sum(Lead.won_value_vnd).filter(won), 0),
                func.count().filter(won, Lead.campaign_id.is_not(None)),
            ).where(*ads_service.cohort(r, None))
        )
    ).one()
    new, won_count, revenue, won_from_ads = (int(v) for v in row)
    spend = ads_service.total(await ads_service.level_stats(db, "campaign", r)).spend_vnd
    overdue = int(
        await db.scalar(
            select(func.count()).where(
                Lead.result_at.is_(None),
                Lead.result_due_at < now,
                Lead.merged_into_lead_id.is_(None),
            )
        )
        or 0
    )
    return vi.ALERT_TEXTS["daily_summary"].format(
        date=r.first_day.strftime("%d/%m/%Y"),
        workspace=workspace_name,
        new=new,
        won=won_count,
        revenue=vnd(revenue),
        spend=vnd(spend),
        cpw=vnd(ads_service.money_ratio(spend, won_from_ads)),
        overdue=overdue,
        link=_link("/overview"),
    )


# ---------------------------------------------------------------- cấu hình (Cài đặt, màn Quảng cáo)


def _rules_out(rules: dict[str, Any]) -> list[RuleOut]:
    return [RuleOut(type=t, enabled=rules[t].enabled, params=rules[t].params) for t in RULE_TYPES]


async def rules_view(db: AsyncSession, ctx: AuthContext) -> RulesView:
    chat_id, _, _ = await _context(db)
    return RulesView(
        rules=_rules_out(await effective_rules(db)),
        can_edit=ctx.can(Perm.SETTINGS_MANAGE),
        chat_configured=bool(chat_id),
    )


async def settings_view(db: AsyncSession, ctx: AuthContext) -> AlertSettingsOut:
    chat_id, _, _ = await _context(db)
    s = get_settings()
    currencies = sorted(
        c
        for c in (await db.scalars(select(AdInsightDaily.currency).distinct())).all()
        if c != "VND"
    )
    deliveries = await db.scalars(
        select(AlertDelivery).order_by(AlertDelivery.sent_at.desc()).limit(RECENT_DELIVERIES)
    )
    rates = await db.scalars(select(FxRate).order_by(FxRate.currency, FxRate.effective_from.desc()))
    return AlertSettingsOut(
        chat_id=chat_id,
        bot_configured=s.mock_mode or bool(s.telegram_bot_token.get_secret_value()),
        is_mock=s.mock_mode,
        rules=_rules_out(await effective_rules(db)),
        fx_rates=[
            FxRateOut(
                id=r.id,
                currency=r.currency,
                effective_from=r.effective_from,
                vnd_per_unit=r.vnd_per_unit,
            )
            for r in rates
        ],
        currencies=currencies,
        deliveries=[
            DeliveryOut(rule_type=d.rule_type, status=d.status, error=d.error, sent_at=d.sent_at)
            for d in deliveries
        ],
    )


async def _save_rule(
    db: AsyncSession, ctx: AuthContext, rule_type: str, enabled: bool, params: dict[str, float]
) -> None:
    limits = PARAM_LIMITS.get(rule_type, {})
    for key, value in params.items():
        bounds = limits.get(key)
        if bounds is None or not bounds[0] <= value <= bounds[1]:
            raise ServiceError("invalid_rule_param", 422, rule=rule_type, param=key)
    row = await db.scalar(select(AlertRule).where(AlertRule.type == rule_type))
    before = {"enabled": row.enabled, "params": row.params} if row else None
    if row is None:
        row = AlertRule(workspace_id=ctx.workspace_id, type=rule_type)
        db.add(row)
    row.enabled = enabled
    row.params = {**(row.params or {}), **params}
    await db.flush()
    after = {"enabled": row.enabled, "params": row.params}
    if before != after:
        await audit.record(
            db,
            workspace_id=ctx.workspace_id,
            actor_member_id=ctx.member_id,
            action="alert_rule.update",
            entity_type="alert_rule",
            entity_id=rule_type,
            before=before,
            after=after,
        )


async def update_settings(
    db: AsyncSession, ctx: AuthContext, body: AlertSettingsUpdate
) -> AlertSettingsOut:
    chat_id = (body.chat_id or "").strip() or None
    if chat_id is not None and not CHAT_ID.match(chat_id):
        raise ServiceError("invalid_chat_id", 422)
    settings = await db.get(WorkspaceSettings, ctx.workspace_id)
    if settings is None:
        raise ServiceError("workspace_not_found", 404)
    if settings.telegram_chat_id != chat_id:
        await audit.record(
            db,
            workspace_id=ctx.workspace_id,
            actor_member_id=ctx.member_id,
            action="alert.chat_id",
            entity_type="workspace_settings",
            entity_id=ctx.workspace_id,
            before={"chat_id": settings.telegram_chat_id},
            after={"chat_id": chat_id},
        )
        settings.telegram_chat_id = chat_id
    for rule in body.rules:
        await _save_rule(db, ctx, rule.type, rule.enabled, rule.params)
    await db.commit()
    return await settings_view(db, ctx)


async def toggle_rule(
    db: AsyncSession, ctx: AuthContext, rule_type: str, enabled: bool
) -> RulesView:
    if rule_type not in RULE_TYPES:
        raise ServiceError("unknown_rule", 404)
    await _save_rule(db, ctx, rule_type, enabled, {})
    await db.commit()
    return await rules_view(db, ctx)


async def send_test(
    db: AsyncSession, ctx: AuthContext, sender: TelegramSender | None = None
) -> TestResult:
    chat_id, workspace_name, _ = await _context(db)
    if not chat_id:
        raise ServiceError("telegram_chat_missing", 422)
    try:
        send = sender or get_telegram()
        await send.send(chat_id, vi.ALERT_TEXTS["test"].format(workspace=workspace_name))
    except TelegramError as exc:
        raise ServiceError(f"telegram_{exc.kind}", 502 if exc.kind == "network" else 422) from None
    return TestResult(status="mock" if send.is_mock else "sent")


async def add_fx_rate(db: AsyncSession, ctx: AuthContext, body: FxRateIn) -> AlertSettingsOut:
    row = await db.scalar(
        select(FxRate).where(
            FxRate.currency == body.currency, FxRate.effective_from == body.effective_from
        )
    )
    before = {"vnd_per_unit": str(row.vnd_per_unit)} if row else None
    if row is None:
        row = FxRate(
            workspace_id=ctx.workspace_id,
            currency=body.currency,
            effective_from=body.effective_from,
            vnd_per_unit=body.vnd_per_unit,
            created_by_member_id=ctx.member_id,
        )
        db.add(row)
    row.vnd_per_unit = body.vnd_per_unit
    await db.flush()
    await meta_sync.apply_fx(db, body.currency)
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="fx_rate.set",
        entity_type="fx_rate",
        entity_id=row.id,
        before=before,
        after={
            "currency": body.currency,
            "effective_from": body.effective_from.isoformat(),
            "vnd_per_unit": str(body.vnd_per_unit),
        },
    )
    await db.commit()
    return await settings_view(db, ctx)


async def delete_fx_rate(
    db: AsyncSession, ctx: AuthContext, rate_id: uuid.UUID
) -> AlertSettingsOut:
    row = await db.get(FxRate, rate_id)
    if row is None or row.workspace_id != ctx.workspace_id:
        raise ServiceError("fx_rate_not_found", 404)
    currency = row.currency
    await db.execute(delete(FxRate).where(FxRate.id == rate_id))
    await meta_sync.apply_fx(db, currency)
    await audit.record(
        db,
        workspace_id=ctx.workspace_id,
        actor_member_id=ctx.member_id,
        action="fx_rate.delete",
        entity_type="fx_rate",
        entity_id=rate_id,
        before={"currency": currency},
    )
    await db.commit()
    return await settings_view(db, ctx)
