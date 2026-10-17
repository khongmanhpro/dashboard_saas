"""API Kết nối BM và gán Trang (Bước 6). Mã truy cập không bao giờ được trả về."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthContext, DbSession, require
from app.core.rbac import Perm
from app.schemas.bms import (
    AssignInput,
    BmOut,
    BmOverview,
    CheckResult,
    ConnectInput,
    PageList,
    TokenInput,
)
from app.services import bm_service, page_service

router = APIRouter(prefix="/api", tags=["bms"])

CanViewBms = Annotated[AuthContext, Depends(require(Perm.BM_VIEW))]
CanConnect = Annotated[AuthContext, Depends(require(Perm.BM_CONNECT))]
CanAssign = Annotated[AuthContext, Depends(require(Perm.PAGE_ASSIGN))]


@router.get("/bms", response_model=BmOverview)
async def list_bms(ctx: CanViewBms, db: DbSession) -> BmOverview:
    return await bm_service.overview(db, ctx)


@router.post("/bms/check", response_model=CheckResult)
async def check_bm(body: TokenInput, ctx: CanConnect, db: DbSession) -> CheckResult:
    return await bm_service.check_token(db, ctx, body)


@router.post("/bms", response_model=BmOut, status_code=status.HTTP_201_CREATED)
async def connect_bm(body: ConnectInput, ctx: CanConnect, db: DbSession) -> BmOut:
    return await bm_service.connect(db, ctx, body)


@router.put("/bms/{bm_id}/token", response_model=BmOut)
async def rotate_token(bm_id: uuid.UUID, body: TokenInput, ctx: CanConnect, db: DbSession) -> BmOut:
    return await bm_service.rotate_token(db, ctx, bm_id, body)


@router.post("/bms/{bm_id}/check", response_model=BmOut)
async def recheck(bm_id: uuid.UUID, ctx: CanConnect, db: DbSession) -> BmOut:
    return await bm_service.recheck(db, ctx, bm_id)


@router.post("/bms/{bm_id}/disconnect", response_model=BmOut)
async def disconnect(bm_id: uuid.UUID, ctx: CanConnect, db: DbSession) -> BmOut:
    return await bm_service.disconnect(db, ctx, bm_id)


@router.get("/pages", response_model=PageList)
async def list_pages(ctx: CanViewBms, db: DbSession) -> PageList:
    return await page_service.list_pages(db, ctx)


@router.put("/pages/{page_id}/owner", status_code=status.HTTP_204_NO_CONTENT)
async def set_owner(page_id: uuid.UUID, body: AssignInput, ctx: CanAssign, db: DbSession) -> None:
    await page_service.set_owner(db, ctx, page_id, body.member_id)
