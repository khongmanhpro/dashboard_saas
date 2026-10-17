from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, AuthSession, MemberRole, MemberStatus, User, WorkspaceMember
from tests.integration import factories as f

pytestmark = pytest.mark.integration

ROLES = list(MemberRole)


@pytest.fixture
async def org(admin_db: AsyncSession) -> dict[str, object]:
    """Một workspace đủ 5 vai trò, 2 nhóm; thêm một workspace khác để thử cách ly."""
    ws = await f.create_workspace(admin_db, "[Workspace chính]")
    team_a = await f.create_team(admin_db, ws, "[Nhóm A]")
    team_b = await f.create_team(admin_db, ws, "[Nhóm B]")
    owner = await f.create_account(admin_db, MemberRole.OWNER, workspace=ws)
    manager = await f.create_account(admin_db, MemberRole.MANAGER, workspace=ws)
    lead = await f.create_account(admin_db, MemberRole.TEAM_LEAD, workspace=ws, team=team_a)
    staff_a = await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=team_a)
    staff_b = await f.create_account(admin_db, MemberRole.STAFF, workspace=ws, team=team_b)
    viewer = await f.create_account(admin_db, MemberRole.VIEWER, workspace=ws)
    team_a.lead_member_id = lead.member.id
    other = await f.create_account(admin_db, MemberRole.OWNER)
    await admin_db.commit()
    return {
        "ws": ws,
        "team_a": team_a,
        "team_b": team_b,
        MemberRole.OWNER: owner,
        MemberRole.MANAGER: manager,
        MemberRole.TEAM_LEAD: lead,
        MemberRole.STAFF: staff_a,
        "staff_b": staff_b,
        MemberRole.VIEWER: viewer,
        "other": other,
    }


async def _as(client: httpx.AsyncClient, org: dict, role: MemberRole) -> f.Account:
    acc = org[role]
    await f.login(client, acc)
    return acc  # type: ignore[no-any-return]


# ---------------- Xem danh sách ----------------


@pytest.mark.parametrize("role", [MemberRole.OWNER, MemberRole.MANAGER, MemberRole.VIEWER])
async def test_full_list_for_owner_manager_viewer(
    client: httpx.AsyncClient, org: dict, role: MemberRole
) -> None:
    await _as(client, org, role)
    resp = await client.get("/api/members")
    assert resp.status_code == 200
    assert len(resp.json()) == 6  # không lẫn người của workspace khác


async def test_team_lead_sees_only_own_team(client: httpx.AsyncClient, org: dict) -> None:
    lead = await _as(client, org, MemberRole.TEAM_LEAD)
    ids = {m["id"] for m in (await client.get("/api/members")).json()}
    assert ids == {str(lead.member.id), str(org[MemberRole.STAFF].member.id)}


async def test_staff_cannot_list_members(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.STAFF)
    resp = await client.get("/api/members")
    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "forbidden", "permission": "member.view"}


# ---------------- Tạo thành viên ----------------


def _new_member(role: str = "staff", **kw: object) -> dict[str, object]:
    return {
        "email": "nv-moi@example.com",
        "full_name": "[Nhân viên 200]",
        "role": role,
        "temp_password": "Tam-thoi-2026",
        **kw,
    }


async def test_manager_creates_staff_who_must_change_password(
    client: httpx.AsyncClient, admin_db: AsyncSession, org: dict
) -> None:
    await _as(client, org, MemberRole.MANAGER)
    resp = await client.post("/api/members", json=_new_member(team_id=str(org["team_b"].id)))
    assert resp.status_code == 201, resp.text
    assert resp.json()["team_id"] == str(org["team_b"].id)
    assert "temp_password" not in resp.text

    user = await admin_db.scalar(select(User).where(User.email == "nv-moi@example.com"))
    assert user is not None and user.must_change_password
    actions = (await admin_db.scalars(select(AuditLog.action))).all()
    assert "member.create" in actions

    # Người mới đăng nhập được nhưng bị chặn ở mọi API cho tới khi đổi mật khẩu.
    newbie = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    r = await newbie.post(
        "/api/auth/login", json={"email": "nv-moi@example.com", "password": "Tam-thoi-2026"}
    )
    assert r.status_code == 200
    newbie.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    blocked = await newbie.get("/api/members")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "password_change_required"
    await newbie.aclose()


@pytest.mark.parametrize("new_role", ["owner", "manager"])
async def test_manager_cannot_create_privileged_roles(
    client: httpx.AsyncClient, org: dict, new_role: str
) -> None:
    await _as(client, org, MemberRole.MANAGER)
    resp = await client.post("/api/members", json=_new_member(new_role))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "role_not_assignable"


async def test_owner_can_create_manager(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.OWNER)
    assert (await client.post("/api/members", json=_new_member("manager"))).status_code == 201


@pytest.mark.parametrize("role", [MemberRole.TEAM_LEAD, MemberRole.STAFF, MemberRole.VIEWER])
async def test_other_roles_cannot_create(
    client: httpx.AsyncClient, org: dict, role: MemberRole
) -> None:
    await _as(client, org, role)
    assert (await client.post("/api/members", json=_new_member())).status_code == 403


async def test_duplicate_and_validation_errors(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.OWNER)
    existing = org[MemberRole.STAFF].email
    dup = await client.post("/api/members", json=_new_member(email=existing))
    assert (dup.status_code, dup.json()["detail"]["code"]) == (409, "member_exists")
    weak = await client.post("/api/members", json=_new_member(temp_password="123"))
    assert (weak.status_code, weak.json()["detail"]["code"]) == (422, "password_too_short")
    foreign_team = await client.post(
        "/api/members", json=_new_member(team_id=str(org["other"].workspace.id))
    )
    assert (foreign_team.status_code, foreign_team.json()["detail"]["code"]) == (
        422,
        "team_not_found",
    )
    bad_email = await client.post("/api/members", json=_new_member(email="khong-phai-email"))
    assert bad_email.status_code == 422


async def test_user_from_other_workspace_is_refused(
    client: httpx.AsyncClient, admin_db: AsyncSession, org: dict
) -> None:
    """Mục O: không gắn người của workspace khác, không lộ họ tên của họ."""
    owner = await _as(client, org, MemberRole.OWNER)
    outsider = org["other"]
    resp = await client.post("/api/members", json=_new_member(email=outsider.email))
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "email_unavailable")
    user = await admin_db.scalar(select(User).where(User.email == outsider.email))
    assert user is not None and not user.must_change_password
    assert user.full_name not in resp.text
    joined = await admin_db.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.workspace_id == owner.member.workspace_id,
        )
    )
    assert joined is None


# ---------------- Sửa thành viên ----------------


async def test_cannot_modify_self(client: httpx.AsyncClient, org: dict) -> None:
    owner = await _as(client, org, MemberRole.OWNER)
    resp = await client.patch(f"/api/members/{owner.member.id}", json={"role": "staff"})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (403, "cannot_modify_self")


async def test_manager_cannot_touch_owner_or_promote(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.MANAGER)
    owner_id = org[MemberRole.OWNER].member.id
    staff_id = org[MemberRole.STAFF].member.id
    r1 = await client.patch(f"/api/members/{owner_id}", json={"status": "disabled"})
    r2 = await client.patch(f"/api/members/{staff_id}", json={"role": "manager"})
    assert r1.status_code == r2.status_code == 403
    r3 = await client.patch(f"/api/members/{staff_id}", json={"role": "team_lead"})
    assert r3.status_code == 200 and r3.json()["role"] == "team_lead"


async def test_owner_can_demote_another_owner(
    client: httpx.AsyncClient, admin_db: AsyncSession, org: dict
) -> None:
    second = await f.create_account(admin_db, MemberRole.OWNER, workspace=org["ws"])
    await admin_db.commit()
    await f.login(client, second)
    first_id = org[MemberRole.OWNER].member.id
    resp = await client.patch(f"/api/members/{first_id}", json={"role": "manager"})
    assert resp.status_code == 200 and resp.json()["role"] == "manager"


async def test_last_owner_guard_handles_concurrent_disable(
    client: httpx.AsyncClient, admin_db: AsyncSession, org: dict
) -> None:
    """Qua API, chủ sở hữu không tự sửa mình nên luôn còn ít nhất một chủ. Kiểm tra này
    chặn trường hợp tranh chấp: người thao tác vừa bị khóa ở request khác."""
    from app.api.deps import AuthContext
    from app.core.db import _app_sessionmaker
    from app.schemas.members import MemberUpdate
    from app.services import auth_service, member_service
    from app.services.errors import ServiceError

    second = await f.create_account(admin_db, MemberRole.OWNER, workspace=org["ws"])
    await admin_db.commit()
    await f.login(client, second)
    token = client.cookies["fp_session"]
    async with _app_sessionmaker()() as db:
        resolved = await auth_service.resolve_session(db, token)
        assert resolved is not None
        ctx = AuthContext(resolved=resolved, ip=None)
        # Request khác khóa `second` trong lúc này.
        second.member.status = MemberStatus.DISABLED
        admin_db.add(second.member)
        await admin_db.commit()
        first_id = org[MemberRole.OWNER].member.id
        with pytest.raises(ServiceError) as info:
            await member_service.update_member(
                db, ctx, first_id, MemberUpdate(role=MemberRole.MANAGER)
            )
        assert info.value.code == "last_owner"


async def test_disabling_member_revokes_their_sessions(
    client: httpx.AsyncClient, admin_db: AsyncSession, org: dict
) -> None:
    staff = org[MemberRole.STAFF]
    staff_client = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    await f.login(staff_client, staff)
    await _as(client, org, MemberRole.MANAGER)
    resp = await client.patch(f"/api/members/{staff.member.id}", json={"status": "disabled"})
    assert resp.status_code == 200 and resp.json()["status"] == MemberStatus.DISABLED
    assert (await staff_client.get("/api/me")).status_code == 401
    sessions = (
        await admin_db.scalars(select(AuthSession).where(AuthSession.member_id == staff.member.id))
    ).all()
    assert all(s.revoked_at is not None for s in sessions)
    await staff_client.aclose()


async def test_member_of_other_workspace_is_not_found(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.OWNER)
    foreign = org["other"].member.id
    resp = await client.patch(f"/api/members/{foreign}", json={"role": "staff"})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (404, "member_not_found")


async def test_move_member_between_teams_and_out(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.MANAGER)
    staff_id = org[MemberRole.STAFF].member.id
    r = await client.patch(f"/api/members/{staff_id}", json={"team_id": str(org["team_b"].id)})
    assert r.json()["team_id"] == str(org["team_b"].id)
    r = await client.patch(f"/api/members/{staff_id}", json={"team_id": None})
    assert r.status_code == 200 and r.json()["team_id"] is None


async def test_unknown_fields_rejected(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.OWNER)
    staff_id = org[MemberRole.STAFF].member.id
    resp = await client.patch(f"/api/members/{staff_id}", json={"workspace_id": "x"})
    assert resp.status_code == 422


# ---------------- Nhóm ----------------


async def test_team_crud_and_scope(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.MANAGER)
    lead_id = str(org[MemberRole.TEAM_LEAD].member.id)
    created = await client.post("/api/teams", json={"name": "[Nhóm C]", "lead_member_id": lead_id})
    assert created.status_code == 201
    dup = await client.post("/api/teams", json={"name": "[Nhóm C]"})
    assert (dup.status_code, dup.json()["detail"]["code"]) == (409, "team_name_taken")
    bad_lead = await client.post(
        "/api/teams",
        json={"name": "[Nhóm D]", "lead_member_id": str(org[MemberRole.STAFF].member.id)},
    )
    assert (bad_lead.status_code, bad_lead.json()["detail"]["code"]) == (422, "invalid_team_lead")
    foreign_lead = await client.post(
        "/api/teams", json={"name": "[Nhóm E]", "lead_member_id": str(org["other"].member.id)}
    )
    assert foreign_lead.status_code == 422
    renamed = await client.patch(f"/api/teams/{created.json()['id']}", json={"name": "[Nhóm C2]"})
    assert renamed.json()["name"] == "[Nhóm C2]"

    all_teams = (await client.get("/api/teams")).json()
    assert {t["name"] for t in all_teams} == {"[Nhóm A]", "[Nhóm B]", "[Nhóm C2]"}
    team_a = next(t for t in all_teams if t["name"] == "[Nhóm A]")
    assert team_a["member_count"] == 2


async def test_team_lead_sees_teams_they_lead(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.TEAM_LEAD)
    names = [t["name"] for t in (await client.get("/api/teams")).json()]
    assert names == ["[Nhóm A]"]
    assert (await client.post("/api/teams", json={"name": "[Nhóm X]"})).status_code == 403


async def test_me_exposes_permissions(client: httpx.AsyncClient, org: dict) -> None:
    await _as(client, org, MemberRole.VIEWER)
    perms = (await client.get("/api/me")).json()["permissions"]
    assert perms["lead.view"] == "all"
    assert "lead.phone.view" not in perms
