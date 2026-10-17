"""API cấu hình cảnh báo Telegram và tỉ giá (Bước 7)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, DbSession, require
from app.core.rbac import Perm
from app.schemas.alerts import (
    AlertSettingsOut,
    AlertSettingsUpdate,
    FxRateIn,
    RulesView,
    RuleToggle,
    TestResult,
)
from app.services import alert_service

router = APIRouter(prefix="/api", tags=["alerts"])

CanManage = Annotated[AuthContext, Depends(require(Perm.SETTINGS_MANAGE))]
CanSeeAds = Annotated[AuthContext, Depends(require(Perm.ADS_COST_VIEW))]


@router.get("/settings/alerts", response_model=AlertSettingsOut)
async def get_alerts(ctx: CanManage, db: DbSession) -> AlertSettingsOut:
    return await alert_service.settings_view(db, ctx)


@router.put("/settings/alerts", response_model=AlertSettingsOut)
async def update_alerts(
    body: AlertSettingsUpdate, ctx: CanManage, db: DbSession
) -> AlertSettingsOut:
    return await alert_service.update_settings(db, ctx, body)


@router.post("/settings/alerts/test", response_model=TestResult)
async def test_alert(ctx: CanManage, db: DbSession) -> TestResult:
    return await alert_service.send_test(db, ctx)


@router.post("/settings/fx-rates", response_model=AlertSettingsOut)
async def add_fx_rate(body: FxRateIn, ctx: CanManage, db: DbSession) -> AlertSettingsOut:
    return await alert_service.add_fx_rate(db, ctx, body)


@router.delete("/settings/fx-rates/{rate_id}", response_model=AlertSettingsOut)
async def delete_fx_rate(rate_id: uuid.UUID, ctx: CanManage, db: DbSession) -> AlertSettingsOut:
    return await alert_service.delete_fx_rate(db, ctx, rate_id)


@router.get("/alerts/rules", response_model=RulesView)
async def rules(ctx: CanSeeAds, db: DbSession) -> RulesView:
    return await alert_service.rules_view(db, ctx)


@router.put("/alerts/rules/{rule_type}", response_model=RulesView)
async def toggle_rule(rule_type: str, body: RuleToggle, ctx: CanManage, db: DbSession) -> RulesView:
    return await alert_service.toggle_rule(db, ctx, rule_type, body.enabled)
