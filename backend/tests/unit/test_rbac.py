"""Ma trận quyền viết lại độc lập với code, theo CLAUDE.md mục 3 và docs/architecture/rbac.md.

Đổi quyền trong app/core/rbac.py mà không sửa bảng này thì test fail: buộc phải cân nhắc.
"""

from __future__ import annotations

import pytest

from app.core.rbac import ROLE_GRANTS, Perm, Scope, can_manage_role, permissions_for
from app.models import MemberRole

OW, M, TL, S, V = (
    MemberRole.OWNER,
    MemberRole.MANAGER,
    MemberRole.TEAM_LEAD,
    MemberRole.STAFF,
    MemberRole.VIEWER,
)
A, T, OWN, NO = Scope.ALL, Scope.TEAM, Scope.OWN, None

#                          Chủ  Quản lý  Trưởng nhóm  Nhân viên  Chỉ xem
EXPECTED: dict[Perm, tuple[Scope | None, ...]] = {
    Perm.BM_CONNECT:         (A, NO, NO, NO, NO),
    Perm.SCORE_FORMULA_EDIT: (A, NO, NO, NO, NO),
    Perm.BILLING_MANAGE:     (A, NO, NO, NO, NO),
    Perm.SETTINGS_MANAGE:    (A, NO, NO, NO, NO),
    Perm.BM_VIEW:            (A, A, NO, NO, NO),
    Perm.PAGE_ASSIGN:        (A, A, NO, NO, NO),
    Perm.TEAM_MANAGE:        (A, A, NO, NO, NO),
    Perm.MEMBER_MANAGE:      (A, A, NO, NO, NO),
    Perm.LEAD_REASSIGN:      (A, A, NO, NO, NO),
    Perm.TEAM_VIEW:          (A, A, T, NO, A),
    Perm.MEMBER_VIEW:        (A, A, T, NO, A),
    Perm.LEAD_VIEW:          (A, A, T, OWN, A),
    Perm.LEAD_UPDATE:        (A, A, OWN, OWN, NO),
    Perm.LEAD_PHONE_VIEW:    (A, A, T, OWN, NO),
    Perm.REMINDER_SEND:      (A, A, T, NO, NO),
    Perm.ADS_COST_VIEW:      (A, A, NO, NO, A),
    Perm.LEADERBOARD_VIEW:   (A, A, T, OWN, A),
    Perm.REPORT_VIEW:        (A, A, T, NO, A),
    Perm.NOTIFICATION_RECEIVE: (A, OWN, OWN, OWN, OWN),
}  # fmt: skip
ROLES = (OW, M, TL, S, V)


def test_expected_table_covers_every_permission() -> None:
    assert set(EXPECTED) == set(Perm)


@pytest.mark.parametrize("perm", list(Perm))
@pytest.mark.parametrize("role", ROLES)
def test_matrix(role: MemberRole, perm: Perm) -> None:
    expected = EXPECTED[perm][ROLES.index(role)]
    assert ROLE_GRANTS[role].get(perm) == expected


def test_viewer_never_sees_phone_numbers() -> None:
    assert Perm.LEAD_PHONE_VIEW not in ROLE_GRANTS[V]


def test_team_lead_and_staff_never_see_ad_cost() -> None:
    assert Perm.ADS_COST_VIEW not in ROLE_GRANTS[TL]
    assert Perm.ADS_COST_VIEW not in ROLE_GRANTS[S]


def test_only_owner_handles_tokens_and_formula() -> None:
    for perm in (Perm.BM_CONNECT, Perm.SCORE_FORMULA_EDIT, Perm.BILLING_MANAGE):
        assert [r for r in ROLES if perm in ROLE_GRANTS[r]] == [OW]


@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        (OW, OW, True),
        (OW, M, True),
        (M, M, False),
        (M, OW, False),
        (M, TL, True),
        (M, S, True),
        (M, V, True),
        (TL, S, False),
        (S, S, False),
        (V, S, False),
    ],
)
def test_role_assignment(actor: MemberRole, target: MemberRole, allowed: bool) -> None:
    assert can_manage_role(actor, target) is allowed


def test_permissions_payload_is_plain_strings() -> None:
    assert permissions_for(S) == {
        "lead.view": "own",
        "lead.update": "own",
        "lead.phone.view": "own",
        "leaderboard.view": "own",
        "notification.receive": "own",
    }
