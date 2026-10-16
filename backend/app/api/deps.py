"""Dependency xác thực dùng chung cho mọi API cần đăng nhập.

- `get_session_context`: đã đăng nhập (kể cả khi đang bị bắt đổi mật khẩu).
- `get_auth_context`: đã đăng nhập và không còn bị bắt đổi mật khẩu. Mặc định dùng cái này.

Test `test_route_protection` kiểm tra mọi route (trừ danh sách công khai) đều đi qua một
trong hai dependency trên.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.rbac import Perm, Scope, scope_of
from app.models import MemberRole
from app.services import auth_service
from app.services.auth_service import ResolvedSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "fp_csrf"

DbSession = Annotated[AsyncSession, Depends(get_db)]


def api_error(status_code: int, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **extra})


def session_cookie_name() -> str:
    # Tiền tố __Host- buộc cookie Secure, Path=/ và không gắn Domain (chỉ dùng được khi https).
    return "__Host-fp_session" if get_settings().cookie_secure else "fp_session"


def set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    s = get_settings()
    max_age = s.session_ttl_days * 86400
    response.set_cookie(
        session_cookie_name(),
        session_token,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    # Cookie CSRF để JavaScript đọc rồi gửi lại qua header (double-submit).
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    for name in (session_cookie_name(), CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=s.cookie_secure, samesite="lax")


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def check_origin(request: Request) -> None:
    """Request ghi đến từ trang khác (Origin lạ) thì từ chối."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    expected = urlsplit(get_settings().app_base_url)
    actual = urlsplit(origin)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        raise api_error(status.HTTP_403_FORBIDDEN, "origin_not_allowed")


@dataclass(frozen=True, slots=True)
class AuthContext:
    resolved: ResolvedSession
    ip: str | None

    @property
    def user_id(self) -> uuid.UUID:
        return self.resolved.user.id

    @property
    def member_id(self) -> uuid.UUID:
        return self.resolved.member.id

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.resolved.member.workspace_id

    @property
    def role(self) -> MemberRole:
        return self.resolved.member.role

    @property
    def team_id(self) -> uuid.UUID | None:
        return self.resolved.member.team_id

    def scope(self, perm: Perm) -> Scope | None:
        return scope_of(self.role, perm)

    def can(self, perm: Perm) -> bool:
        return self.scope(perm) is not None


async def get_session_context(request: Request, db: DbSession) -> AuthContext:
    token = request.cookies.get(session_cookie_name())
    if not token:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    resolved = await auth_service.resolve_session(db, token)
    if resolved is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    if request.method not in SAFE_METHODS:
        check_origin(request)
        if not auth_service.csrf_valid(resolved.session, request.headers.get(CSRF_HEADER)):
            raise api_error(status.HTTP_403_FORBIDDEN, "csrf_failed")
    return AuthContext(resolved=resolved, ip=client_ip(request))


SessionContext = Annotated[AuthContext, Depends(get_session_context)]


async def get_auth_context(ctx: SessionContext) -> AuthContext:
    if ctx.resolved.user.must_change_password:
        raise api_error(status.HTTP_403_FORBIDDEN, "password_change_required")
    return ctx


CurrentContext = Annotated[AuthContext, Depends(get_auth_context)]


def require(perm: Perm) -> Callable[[AuthContext], Awaitable[AuthContext]]:
    """Dependency kiểm tra quyền hành động. Phạm vi dữ liệu do service áp trong truy vấn."""

    async def dependency(ctx: CurrentContext) -> AuthContext:
        if not ctx.can(perm):
            raise api_error(status.HTTP_403_FORBIDDEN, "forbidden", permission=perm.value)
        return ctx

    dependency.__name__ = f"require_{perm.name.lower()}"
    dependency.required_permission = perm  # type: ignore[attr-defined]
    return dependency
