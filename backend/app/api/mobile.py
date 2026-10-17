"""API cho ứng dụng điện thoại (/m), nhắc việc, thông báo đẩy, nhắc thủ công (Bước 5)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import AuthContext, DbSession, api_error, require
from app.core.config import get_settings
from app.core.rbac import Perm
from app.models import Notification, PushSubscription
from app.schemas.mobile import (
    MobileHome,
    MobileLead,
    MobileTab,
    NotificationList,
    NotificationOut,
    PushConfig,
    PushSubscribe,
    PushUnsubscribe,
)
from app.services import mobile_service, notify_service, push

router = APIRouter(prefix="/api", tags=["mobile"])

CanViewLeads = Annotated[AuthContext, Depends(require(Perm.LEAD_VIEW))]
CanReceive = Annotated[AuthContext, Depends(require(Perm.NOTIFICATION_RECEIVE))]
CanRemind = Annotated[AuthContext, Depends(require(Perm.REMINDER_SEND))]


@router.get("/m/home", response_model=MobileHome)
async def mobile_home(ctx: CanViewLeads, db: DbSession) -> MobileHome:
    return await mobile_service.home(db, ctx)


@router.get("/m/leads", response_model=list[MobileLead])
async def mobile_leads(
    ctx: CanViewLeads, db: DbSession, tab: MobileTab = "todo"
) -> list[MobileLead]:
    return await mobile_service.mobile_leads(db, ctx, tab)


@router.post("/leads/{lead_id}/remind", status_code=status.HTTP_204_NO_CONTENT)
async def remind(lead_id: uuid.UUID, ctx: CanRemind, db: DbSession) -> None:
    await notify_service.remind_owner(db, ctx, lead_id)


# ---------------------------------------------------------------- nhắc việc của mình


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    ctx: CanReceive, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> NotificationList:
    rows = await db.scalars(
        select(Notification)
        .where(Notification.member_id == ctx.member_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    items = [
        NotificationOut(
            id=n.id,
            type=n.type,
            title=n.title,
            body=n.body,
            lead_id=n.lead_id,
            created_at=n.created_at,
            read_at=n.read_at,
        )
        for n in rows
    ]
    return NotificationList(
        items=items, unread=await notify_service.unread_count(db, ctx.member_id)
    )


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(notification_id: int, ctx: CanReceive, db: DbSession) -> None:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.member_id == ctx.member_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=dt.datetime.now(dt.UTC))
    )
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        exists = await db.scalar(
            select(Notification.id).where(
                Notification.id == notification_id, Notification.member_id == ctx.member_id
            )
        )
        if exists is None:
            raise api_error(status.HTTP_404_NOT_FOUND, "notification_not_found")


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(ctx: CanReceive, db: DbSession) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.member_id == ctx.member_id, Notification.read_at.is_(None))
        .values(read_at=dt.datetime.now(dt.UTC))
    )
    await db.commit()


# ---------------------------------------------------------------- thông báo đẩy


@router.get("/push/config", response_model=PushConfig)
async def push_config(ctx: CanReceive) -> PushConfig:
    enabled = push.push_configured()
    return PushConfig(
        enabled=enabled, public_key=get_settings().vapid_public_key if enabled else None
    )


@router.post("/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(body: PushSubscribe, request: Request, ctx: CanReceive, db: DbSession) -> None:
    stmt = pg_insert(PushSubscription).values(
        id=uuid.uuid4(),
        workspace_id=ctx.workspace_id,
        member_id=ctx.member_id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    )
    # Cùng máy đăng nhập người khác thì đăng ký chuyển sang người mới.
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["workspace_id", "endpoint"],
            set_={
                "member_id": stmt.excluded.member_id,
                "p256dh": stmt.excluded.p256dh,
                "auth": stmt.excluded.auth,
                "user_agent": stmt.excluded.user_agent,
                "failure_count": 0,
            },
        )
    )
    await db.commit()


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(body: PushUnsubscribe, ctx: CanReceive, db: DbSession) -> None:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.member_id == ctx.member_id
        )
    )
    await db.commit()
