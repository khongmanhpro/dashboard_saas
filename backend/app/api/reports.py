"""API Tổng quan, Fanpage, Chi tiết Trang, Quảng cáo (Bước 7)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import AuthContext, DbSession, require
from app.core.config import get_settings
from app.core.rbac import Perm
from app.schemas.reports import (
    AdsLevel,
    AdsReport,
    OverviewOut,
    PageDetailOut,
    PageReportList,
    PageSort,
    PageTab,
)
from app.services import ads_service, report_export, report_service
from app.services.report_range import RangeKey, resolve_range

router = APIRouter(prefix="/api/reports", tags=["reports"])

CanReport = Annotated[AuthContext, Depends(require(Perm.REPORT_VIEW))]
CanSeeAds = Annotated[AuthContext, Depends(require(Perm.ADS_COST_VIEW))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, name: str) -> Response:
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/overview", response_model=OverviewOut)
async def overview(
    ctx: CanReport,
    db: DbSession,
    range: RangeKey = "7d",
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    team_id: uuid.UUID | None = None,
) -> OverviewOut:
    return await report_service.overview(
        db, ctx, range, date_from=date_from, date_to=date_to, team_id=team_id
    )


@router.get("/overview.xlsx")
async def overview_export(
    ctx: CanReport,
    db: DbSession,
    range: RangeKey = "7d",
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    team_id: uuid.UUID | None = None,
) -> Response:
    data = await report_service.overview(
        db, ctx, range, date_from=date_from, date_to=date_to, team_id=team_id
    )
    return _xlsx(report_export.overview_xlsx(data), "tong-quan.xlsx")


@router.get("/pages", response_model=PageReportList)
async def pages(
    ctx: CanReport,
    db: DbSession,
    tab: PageTab = "all",
    q: Annotated[str | None, Query(max_length=100)] = None,
    bm_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    sort: PageSort = "leads",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
) -> PageReportList:
    return await report_service.pages_report(
        db, ctx, tab=tab, q=q, bm_id=bm_id, team_id=team_id, sort=sort, page=page
    )


@router.get("/pages.xlsx")
async def pages_export(ctx: CanReport, db: DbSession) -> Response:
    rows = await report_service.all_page_rows(db, ctx)
    return _xlsx(report_export.pages_xlsx(rows), "fanpage.xlsx")


@router.get("/pages/{page_id}", response_model=PageDetailOut)
async def page_detail(page_id: uuid.UUID, ctx: CanReport, db: DbSession) -> PageDetailOut:
    return await report_service.page_detail(db, ctx, page_id)


@router.get("/ads", response_model=AdsReport)
async def ads(
    ctx: CanSeeAds,
    db: DbSession,
    range: RangeKey = "30d",
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    level: AdsLevel = "campaign",
    account_id: uuid.UUID | None = None,
) -> AdsReport:
    now = dt.datetime.now(dt.UTC)
    tz = await report_service.workspace_tz(db, ctx.workspace_id)
    r = resolve_range(range, tz, now, date_from, date_to)
    return await ads_service.report(
        db, r, level, account_id=account_id, now=now, is_mock=get_settings().mock_mode
    )
