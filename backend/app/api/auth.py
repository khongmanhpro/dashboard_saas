from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    DbSession,
    SessionContext,
    api_error,
    check_origin,
    clear_auth_cookies,
    client_ip,
    set_auth_cookies,
)
from app.core.redis import get_redis
from app.core.security import PasswordPolicyError
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, MeResponse
from app.services import auth_service
from app.services.auth_service import ResolvedSession

router = APIRouter(prefix="/api", tags=["auth"])


def build_me(resolved: ResolvedSession) -> MeResponse:
    user, member, ws = resolved.user, resolved.member, resolved.workspace
    return MeResponse.model_validate(
        {
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
            "workspace": {"id": ws.id, "name": ws.name, "timezone": ws.timezone},
            "member": {"id": member.id, "role": member.role, "team_id": member.team_id},
            "must_change_password": user.must_change_password,
            "permissions": [],
        }
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> object:
    check_origin(request)
    try:
        result = await auth_service.login(
            db,
            get_redis(),
            email=body.email,
            password=body.password,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.TooManyAttempts as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": {"code": exc.code, "retry_after": exc.retry_after}},
            headers={"Retry-After": str(exc.retry_after)},
        )
    except auth_service.InvalidCredentials as exc:
        raise api_error(status.HTTP_401_UNAUTHORIZED, exc.code) from None

    resolved = await auth_service.resolve_session(db, result.session_token)
    if resolved is None:  # pragma: no cover - vừa tạo xong thì phải hợp lệ
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "session_error")
    set_auth_cookies(response, result.session_token, result.csrf_token)
    me = build_me(resolved)
    return LoginResponse(**me.model_dump(), csrf_token=result.csrf_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(ctx: SessionContext, db: DbSession, response: Response) -> None:
    await auth_service.logout(db, ctx.resolved.session)
    clear_auth_cookies(response)


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, ctx: SessionContext, db: DbSession) -> None:
    try:
        await auth_service.change_password(
            db,
            ctx.resolved,
            current_password=body.current_password,
            new_password=body.new_password,
            ip=ctx.ip,
        )
    except auth_service.WrongCurrentPassword as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, exc.code) from None
    except PasswordPolicyError as exc:
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code) from None


@router.get("/me", response_model=MeResponse)
async def me(ctx: SessionContext) -> MeResponse:
    return build_me(ctx.resolved)
