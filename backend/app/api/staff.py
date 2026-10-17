"""API Nhân viên và Công thức điểm (Bước 4)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, DbSession, require
from app.core.rbac import Perm
from app.models import PeriodType
from app.schemas.staff import (
    FormulaOut,
    FormulaUpdate,
    Leaderboard,
    PreviewOut,
    StaffDetail,
    Weights,
)
from app.services import staff_service

router = APIRouter(prefix="/api", tags=["staff"])

CanViewLeaderboard = Annotated[AuthContext, Depends(require(Perm.LEADERBOARD_VIEW))]
CanEditFormula = Annotated[AuthContext, Depends(require(Perm.SCORE_FORMULA_EDIT))]


@router.get("/staff/leaderboard", response_model=Leaderboard)
async def leaderboard(
    ctx: CanViewLeaderboard, db: DbSession, period: PeriodType = PeriodType.WEEK
) -> Leaderboard:
    return await staff_service.leaderboard(db, ctx, period)


@router.get("/staff/{member_id}", response_model=StaffDetail)
async def staff_detail(
    member_id: uuid.UUID,
    ctx: CanViewLeaderboard,
    db: DbSession,
    period: PeriodType = PeriodType.WEEK,
) -> StaffDetail:
    return await staff_service.staff_detail(db, ctx, member_id, period)


@router.get("/score/formula", response_model=FormulaOut)
async def get_formula(ctx: CanViewLeaderboard, db: DbSession) -> FormulaOut:
    return await staff_service.get_formula(db, ctx)


@router.put("/score/formula", response_model=FormulaOut)
async def update_formula(body: FormulaUpdate, ctx: CanEditFormula, db: DbSession) -> FormulaOut:
    return await staff_service.update_formula(db, ctx, body.weights)


@router.post("/score/preview", response_model=PreviewOut)
async def preview_formula(body: Weights, ctx: CanEditFormula, db: DbSession) -> PreviewOut:
    return await staff_service.preview_formula(db, ctx, body)


@router.post("/score/recompute", response_model=dict[str, int])
async def recompute(ctx: CanEditFormula, db: DbSession) -> dict[str, int]:
    return await staff_service.recompute_now(db, ctx)
