from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, LargeBinary, String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class AuthSession(Base):
    """Phiên đăng nhập. Chỉ lưu HMAC của token, không lưu token gốc.

    Không bật RLS: phải tra theo token trước khi biết workspace.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "member_id"],
            ["workspace_members.workspace_id", "workspace_members.id"],
            ondelete="CASCADE",
            name="fk_auth_sessions_member",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID]
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    csrf_hmac: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[dt.datetime] = created_at_col()
    last_seen_at: Mapped[dt.datetime]
    expires_at: Mapped[dt.datetime]
    idle_expires_at: Mapped[dt.datetime]
    revoked_at: Mapped[dt.datetime | None]
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(300))
