from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AuditLog, AuthSession, MemberRole, MemberStatus, User, Workspace
from app.models.enums import WorkspaceStatus
from tests.integration import factories as f

pytestmark = pytest.mark.integration

GENERIC_401 = {"detail": {"code": "invalid_credentials"}}


async def _account(admin_db: AsyncSession, **kw: object) -> f.Account:
    acc = await f.create_account(admin_db, **kw)  # type: ignore[arg-type]
    await admin_db.commit()
    return acc


# ---------------- Đăng nhập ----------------


async def test_login_sets_secure_cookies_and_returns_profile(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db, role=MemberRole.MANAGER)
    resp = await client.post("/api/auth/login", json={"email": acc.email, "password": acc.password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == acc.email
    assert body["member"]["role"] == "manager"
    assert body["workspace"]["id"] == str(acc.workspace.id)
    assert "password_hash" not in resp.text
    assert "$argon2" not in resp.text
    assert acc.password not in resp.text

    cookies = resp.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("fp_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("fp_csrf="))
    assert "HttpOnly" in session_cookie
    assert "samesite=lax" in session_cookie.lower()
    assert "Path=/" in session_cookie
    assert "HttpOnly" not in csrf_cookie


async def test_login_email_is_case_insensitive(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    resp = await client.post(
        "/api/auth/login", json={"email": "  " + acc.email.upper(), "password": acc.password}
    )
    assert resp.status_code == 200


async def test_db_stores_only_token_digest(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    resp = await client.post("/api/auth/login", json={"email": acc.email, "password": acc.password})
    raw_token = resp.cookies["fp_session"]
    rows = (await admin_db.scalars(select(AuthSession))).all()
    assert len(rows) == 1
    assert raw_token.encode() not in rows[0].token_hmac
    dump = await admin_db.scalar(text("SELECT row_to_json(s)::text FROM auth_sessions s"))
    assert raw_token not in dump


@pytest.mark.parametrize(
    "case",
    [
        "wrong_password",
        "unknown_email",
        "inactive_user",
        "disabled_member",
        "suspended_workspace",
        "no_password_set",
    ],
)
async def test_login_failures_are_indistinguishable(
    client: httpx.AsyncClient, admin_db: AsyncSession, case: str
) -> None:
    acc = await _account(admin_db)
    email, password = acc.email, acc.password
    if case == "wrong_password":
        password = "sai-mat-khau-123"
    elif case == "unknown_email":
        email = "khong-ton-tai@example.com"
    elif case == "inactive_user":
        await admin_db.execute(update(User).values(is_active=False))
    elif case == "disabled_member":
        acc.member.status = MemberStatus.DISABLED
    elif case == "suspended_workspace":
        await admin_db.execute(update(Workspace).values(status=WorkspaceStatus.SUSPENDED))
    elif case == "no_password_set":
        await admin_db.execute(update(User).values(password_hash=None))
    await admin_db.commit()

    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 401
    assert resp.json() == GENERIC_401
    assert "set-cookie" not in resp.headers


async def test_rate_limit_blocks_after_max_failures(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    limit = get_settings().login_max_failures
    for _ in range(limit):
        r = await client.post(
            "/api/auth/login", json={"email": acc.email, "password": "sai-sai-sai-1"}
        )
        assert r.status_code == 401
    # Đúng mật khẩu cũng bị chặn khi đã vượt ngưỡng.
    r = await client.post("/api/auth/login", json={"email": acc.email, "password": acc.password})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_attempts"
    assert int(r.headers["Retry-After"]) > 0


async def test_successful_login_resets_failure_counter(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    limit = get_settings().login_max_failures
    for _ in range(limit - 1):
        await client.post("/api/auth/login", json={"email": acc.email, "password": "sai-sai-sai-1"})
    assert (
        await client.post("/api/auth/login", json={"email": acc.email, "password": acc.password})
    ).status_code == 200
    for _ in range(limit - 1):
        r = await client.post(
            "/api/auth/login", json={"email": acc.email, "password": "sai-sai-sai-1"}
        )
        assert r.status_code == 401


async def test_login_rejects_foreign_origin(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    resp = await client.post(
        "/api/auth/login",
        json={"email": acc.email, "password": acc.password},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "origin_not_allowed"


async def test_login_writes_audit_log_without_secrets(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    logs = (await admin_db.scalars(select(AuditLog))).all()
    assert [log.action for log in logs] == ["auth.login"]
    assert acc.password not in str(logs[0].after) + str(logs[0].before)


# ---------------- Phiên ----------------


async def test_me_requires_session(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "not_authenticated"


async def test_me_with_session(client: httpx.AsyncClient, admin_db: AsyncSession) -> None:
    acc = await _account(admin_db, role=MemberRole.TEAM_LEAD)
    await f.login(client, acc)
    resp = await client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["member"]["role"] == "team_lead"


async def test_logout_revokes_session(client: httpx.AsyncClient, admin_db: AsyncSession) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    stolen = client.cookies["fp_session"]
    assert (await client.post("/api/auth/logout")).status_code == 204
    # Dùng lại cookie cũ (ví dụ bị đánh cắp) cũng không được.
    client.cookies.set("fp_session", stolen)
    assert (await client.get("/api/me")).status_code == 401


@pytest.mark.parametrize("column", ["expires_at", "idle_expires_at"])
async def test_expired_session_is_rejected(
    client: httpx.AsyncClient, admin_db: AsyncSession, column: str
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await admin_db.execute(update(AuthSession).values({column: past}))
    await admin_db.commit()
    assert (await client.get("/api/me")).status_code == 401


async def test_session_rejected_when_member_disabled_later(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    acc.member.status = MemberStatus.DISABLED
    admin_db.add(acc.member)
    await admin_db.commit()
    assert (await client.get("/api/me")).status_code == 401


async def test_activity_extends_idle_expiry(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    old = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    await admin_db.execute(
        update(AuthSession).values(last_seen_at=old, idle_expires_at=old + dt.timedelta(days=1))
    )
    await admin_db.commit()
    assert (await client.get("/api/me")).status_code == 200
    admin_db.expire_all()
    session = (await admin_db.scalars(select(AuthSession))).one()
    assert session.last_seen_at > old + dt.timedelta(minutes=59)
    assert session.idle_expires_at > dt.datetime.now(dt.UTC) + dt.timedelta(days=6)


# ---------------- CSRF ----------------


async def test_write_without_csrf_header_is_rejected(
    client: httpx.AsyncClient, admin_db: AsyncSession
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    del client.headers["X-CSRF-Token"]
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = "gia-mao"
    assert (await client.post("/api/auth/logout")).status_code == 403
    # Phiên vẫn còn: request giả mạo không làm gì được.
    assert (await client.get("/api/me")).status_code == 200


# ---------------- Đổi mật khẩu ----------------


async def test_change_password_flow(client: httpx.AsyncClient, admin_db: AsyncSession) -> None:
    acc = await _account(admin_db, must_change_password=True)
    # Đăng nhập thêm một thiết bị khác.
    other = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    await f.login(other, acc)
    await f.login(client, acc)

    me = await client.get("/api/me")
    assert me.json()["must_change_password"] is True

    new_password = "Mat-khau-moi-2026"
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": acc.password, "new_password": new_password},
    )
    assert resp.status_code == 204
    assert (await client.get("/api/me")).json()["must_change_password"] is False
    # Thiết bị khác bị đăng xuất.
    assert (await other.get("/api/me")).status_code == 401
    await other.aclose()
    # Mật khẩu cũ hết dùng được, mật khẩu mới dùng được.
    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    r = await fresh.post("/api/auth/login", json={"email": acc.email, "password": acc.password})
    assert r.status_code == 401
    r = await fresh.post("/api/auth/login", json={"email": acc.email, "password": new_password})
    assert r.status_code == 200
    await fresh.aclose()


@pytest.mark.parametrize(
    ("current", "new", "status", "code"),
    [
        ("sai-mat-khau-cu", "Mat-khau-moi-2026", 400, "wrong_current_password"),
        (None, "ngan", 422, "password_too_short"),
        (None, None, 422, "password_unchanged"),
    ],
)
async def test_change_password_errors(
    client: httpx.AsyncClient,
    admin_db: AsyncSession,
    current: str | None,
    new: str | None,
    status: int,
    code: str,
) -> None:
    acc = await _account(admin_db)
    await f.login(client, acc)
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": current or acc.password, "new_password": new or acc.password},
    )
    assert resp.status_code == status
    assert resp.json()["detail"]["code"] == code


async def test_public_config(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"mock_mode": True, "app_env": "test"}
