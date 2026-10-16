"""Ghi nhật ký thao tác. Không bao giờ truyền mật khẩu, mã truy cập, SĐT đầy đủ vào đây."""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def clean_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


async def record(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_member_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_member_id=actor_member_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=before,
            after=after,
            ip=clean_ip(ip),
        )
    )
