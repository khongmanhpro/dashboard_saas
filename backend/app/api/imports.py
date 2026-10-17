"""API nhập nhân viên từ Excel (Bước 6). File gửi dạng nhị phân thô, không cần multipart."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.api.deps import AuthContext, DbSession, api_error, require
from app.core.rbac import Perm
from app.schemas.imports import ImportPreview, ImportResult
from app.services import import_service

router = APIRouter(prefix="/api/imports", tags=["imports"])

CanImport = Annotated[AuthContext, Depends(require(Perm.MEMBER_MANAGE))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/members/template")
async def template(ctx: CanImport, db: DbSession) -> Response:
    return Response(
        content=await import_service.template(db),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="mau-nhap-nhan-vien.xlsx"'},
    )


@router.post("/members/preview", response_model=ImportPreview)
async def preview(request: Request, ctx: CanImport, db: DbSession) -> ImportPreview:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > import_service.MAX_BYTES:
        raise api_error(413, "import_file_too_large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > import_service.MAX_BYTES:
            raise api_error(413, "import_file_too_large")
    file_name = unquote(request.headers.get("x-file-name", "nhan-vien.xlsx"))
    return await import_service.preview(db, ctx, bytes(body), file_name)


@router.post("/{job_id}/apply", response_model=ImportResult)
async def apply(job_id: uuid.UUID, ctx: CanImport, db: DbSession) -> ImportResult:
    return await import_service.apply(db, ctx, job_id)
