"""API khách hàng (Bước 3). Phạm vi dữ liệu và che SĐT nằm ở `lead_service`."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthContext, DbSession, require
from app.core.rbac import Perm
from app.models import LeadStatus
from app.schemas.leads import FilterOptions, LeadDetail, LeadPage, LeadSummary
from app.services import lead_service
from app.services.lead_service import Chip, LeadFilters, Period, SourceFilter

router = APIRouter(prefix="/api/leads", tags=["leads"])

CanViewLeads = Annotated[AuthContext, Depends(require(Perm.LEAD_VIEW))]


def _filters(
    period: Period = "7d",
    chip: Chip | None = None,
    status: LeadStatus | None = None,
    page_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    source: SourceFilter | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> LeadFilters:
    return LeadFilters(
        period=period,
        chip=chip,
        status=status,
        page_id=page_id,
        owner_id=owner_id,
        source=source,
        q=q,
    )


Filters = Annotated[LeadFilters, Depends(_filters)]


@router.get("", response_model=LeadPage)
async def list_leads(
    ctx: CanViewLeads,
    db: DbSession,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> LeadPage:
    return await lead_service.list_leads(db, ctx, filters, limit=limit, cursor=cursor)


@router.get("/summary", response_model=LeadSummary)
async def lead_summary(ctx: CanViewLeads, db: DbSession, filters: Filters) -> LeadSummary:
    return await lead_service.summary(db, ctx, filters)


@router.get("/filter-options", response_model=FilterOptions)
async def lead_filter_options(ctx: CanViewLeads, db: DbSession) -> FilterOptions:
    return await lead_service.filter_options(db, ctx)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: uuid.UUID, ctx: CanViewLeads, db: DbSession) -> LeadDetail:
    return await lead_service.get_lead(db, ctx, lead_id)
