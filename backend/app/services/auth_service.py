"""Đăng nhập, phiên, đổi mật khẩu.

Mọi lỗi đăng nhập trả cùng một mã `invalid_credentials` để không lộ email nào tồn tại.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import TenantContext, set_tenant
from app.core.security import (
    PasswordPolicyError,
    digest_matches,
    hash_password,
    new_token,
    password_needs_rehash,
    token_digest,
    validate_password,
    verify_password,
)
from app.models import (
    AuthSession,
    MemberStatus,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceStatus,
)
from app.services import audit
from app.services.audit import clean_ip

SESSION_PURPOSE = "session"
CSRF_PURPOSE = "csrf"
# Chỉ cập nhật last_seen_at tối đa mỗi 5 phút để đỡ ghi DB.
TOUCH_INTERVAL = dt.timedelta(minutes=5)
EMAIL_MAX_LENGTH = 254


class AuthError(Exception):
    code = "auth_error"


class InvalidCredentials(AuthError):
    code = "invalid_credentials"


class TooManyAttempts(AuthError):
    code = "too_many_attempts"

    def __init__(self, retry_after: int) -> None:
        super().__init__(self.code)
        self.retry_after = retry_after


class WrongCurrentPassword(AuthError):
    code = "wrong_current_password"


@dataclass(frozen=True, slots=True)
class LoginResult:
    session_token: str
    csrf_token: str
    user: User
    member: WorkspaceMember


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session: AuthSession
    user: User
    member: WorkspaceMember
    workspace: Workspace


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()[:EMAIL_MAX_LENGTH]


# ---------------- Giới hạn số lần đăng nhập sai ----------------


def _email_key(email: str) -> str:
    return "auth:fail:email:" + hashlib.sha256(email.encode()).hexdigest()[:32]


def _ip_key(ip: str | None) -> str:
    return f"auth:fail:ip:{ip or 'unknown'}"


async def _check_rate_limit(redis: Redis, email: str, ip: str | None) -> None:
    s = get_settings()
    email_key, ip_key = _email_key(email), _ip_key(ip)
    email_fails, ip_fails = await redis.mget(email_key, ip_key)
    # Theo IP cho phép nhiều hơn vì nhiều nhân viên có thể dùng chung mạng văn phòng.
    if int(email_fails or 0) >= s.login_max_failures:
        raise TooManyAttempts(max(await redis.ttl(email_key), 1))
    if int(ip_fails or 0) >= s.login_max_failures * 10:
        raise TooManyAttempts(max(await redis.ttl(ip_key), 1))


async def _record_failure(redis: Redis, email: str, ip: str | None) -> None:
    window = get_settings().login_window_seconds
    async with redis.pipeline(transaction=True) as pipe:
        for key in (_email_key(email), _ip_key(ip)):
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
        await pipe.execute()


# ---------------- Đăng nhập ----------------


async def _active_membership(db: AsyncSession, user_id: uuid.UUID) -> WorkspaceMember | None:
    await set_tenant(db, TenantContext(workspace_id=None, user_id=user_id))
    stmt = (
        select(WorkspaceMember)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
            Workspace.status == WorkspaceStatus.ACTIVE,
        )
        .order_by(WorkspaceMember.created_at)
        .limit(1)
    )
    return (await db.scalars(stmt)).first()


async def login(
    db: AsyncSession,
    redis: Redis,
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> LoginResult:
    email = normalize_email(email)
    await _check_rate_limit(redis, email, ip)

    user = (await db.scalars(select(User).where(User.email == email))).first()
    # Luôn chạy argon2, kể cả khi không có user, để thời gian phản hồi như nhau.
    ok = verify_password(user.password_hash if user else None, password)
    member = await _active_membership(db, user.id) if (ok and user and user.is_active) else None
    if user is None or not ok or not user.is_active or member is None:
        await _record_failure(redis, email, ip)
        raise InvalidCredentials(InvalidCredentials.code)

    await redis.delete(_email_key(email))
    await set_tenant(db, TenantContext(workspace_id=member.workspace_id, user_id=user.id))

    now = _now()
    s = get_settings()
    session_token, csrf_token = new_token(), new_token()
    db.add(
        AuthSession(
            user_id=user.id,
            workspace_id=member.workspace_id,
            member_id=member.id,
            token_hmac=token_digest(session_token, SESSION_PURPOSE),
            csrf_hmac=token_digest(csrf_token, CSRF_PURPOSE),
            last_seen_at=now,
            expires_at=now + dt.timedelta(days=s.session_ttl_days),
            idle_expires_at=now + dt.timedelta(days=s.session_idle_days),
            ip=clean_ip(ip),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    user.last_login_at = now
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await audit.record(
        db,
        workspace_id=member.workspace_id,
        actor_member_id=member.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        ip=ip,
    )
    await db.commit()
    return LoginResult(session_token, csrf_token, user, member)


# ---------------- Phiên ----------------


async def resolve_session(db: AsyncSession, token: str) -> ResolvedSession | None:
    """Trả về phiên còn hiệu lực và đặt ngữ cảnh tenant cho `db`; None nếu không hợp lệ."""
    now = _now()
    session = (
        await db.scalars(
            select(AuthSession).where(
                AuthSession.token_hmac == token_digest(token, SESSION_PURPOSE),
                AuthSession.revoked_at.is_(None),
            )
        )
    ).first()
    if session is None or now >= session.expires_at or now >= session.idle_expires_at:
        return None

    await set_tenant(db, TenantContext(workspace_id=session.workspace_id, user_id=session.user_id))
    user = await db.get(User, session.user_id)
    member = await db.get(WorkspaceMember, session.member_id)
    workspace = await db.get(Workspace, session.workspace_id)
    if (
        user is None
        or not user.is_active
        or member is None
        or member.status != MemberStatus.ACTIVE
        or workspace is None
        or workspace.status != WorkspaceStatus.ACTIVE
    ):
        return None

    if now - session.last_seen_at >= TOUCH_INTERVAL:
        idle = dt.timedelta(days=get_settings().session_idle_days)
        session.last_seen_at = now
        session.idle_expires_at = min(now + idle, session.expires_at)
        await db.commit()
    return ResolvedSession(session, user, member, workspace)


def csrf_valid(session: AuthSession, csrf_token: str | None) -> bool:
    return bool(csrf_token) and digest_matches(csrf_token or "", CSRF_PURPOSE, session.csrf_hmac)


async def logout(db: AsyncSession, session: AuthSession) -> None:
    session.revoked_at = _now()
    await db.commit()


async def change_password(
    db: AsyncSession,
    resolved: ResolvedSession,
    *,
    current_password: str,
    new_password: str,
    ip: str | None,
) -> None:
    user = resolved.user
    if not verify_password(user.password_hash, current_password):
        raise WrongCurrentPassword(WrongCurrentPassword.code)
    validate_password(new_password, user.email)
    if verify_password(user.password_hash, new_password):
        raise PasswordPolicyError("password_unchanged")

    now = _now()
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = now
    # Đăng xuất mọi thiết bị khác.
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != resolved.session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await audit.record(
        db,
        workspace_id=resolved.member.workspace_id,
        actor_member_id=resolved.member.id,
        action="auth.password_change",
        entity_type="user",
        entity_id=user.id,
        ip=ip,
    )
    await db.commit()
