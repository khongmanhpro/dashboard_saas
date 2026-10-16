from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk


class User(Base):
    """Danh tính đăng nhập, dùng chung cho mọi workspace (không có workspace_id).

    Vai trò và quyền nằm ở `WorkspaceMember`, không nằm ở đây.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # NULL khi tài khoản được mời nhưng chưa đặt mật khẩu.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_login_at: Mapped[dt.datetime | None]
    password_changed_at: Mapped[dt.datetime | None]
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()
