"""Phân quyền 5 vai trò (CLAUDE.md mục 3 "Vai trò", docs/architecture/rbac.md).

Hai lớp:
- **Quyền hành động** (`Perm`): endpoint khai báo `require(Perm.X)`, mặc định từ chối.
- **Phạm vi dữ liệu** (`Scope`): áp ngay trong câu truy vấn (toàn workspace / nhóm / của mình).

Bảng ROLE_GRANTS là nguồn sự thật duy nhất; frontend nhận lại qua /api/me.
"""

from __future__ import annotations

import enum
from types import MappingProxyType
from typing import Final

from app.models.enums import MemberRole


class Perm(enum.StrEnum):
    BM_CONNECT = "bm.connect"  # Kết nối BM, dán và đổi mã truy cập
    BM_VIEW = "bm.view"  # Xem BM và trạng thái kết nối
    SCORE_FORMULA_EDIT = "score_formula.edit"
    BILLING_MANAGE = "billing.manage"
    SETTINGS_MANAGE = "settings.manage"  # Quy tắc đo lường của workspace
    PAGE_ASSIGN = "page.assign"
    TEAM_VIEW = "team.view"
    TEAM_MANAGE = "team.manage"
    MEMBER_VIEW = "member.view"
    MEMBER_MANAGE = "member.manage"
    LEAD_VIEW = "lead.view"
    LEAD_UPDATE = "lead.update"  # Cập nhật kết quả, đánh dấu đã gọi
    LEAD_REASSIGN = "lead.reassign"
    LEAD_PHONE_VIEW = "lead.phone.view"  # Thiếu quyền này thì SĐT bị che
    REMINDER_SEND = "reminder.send"
    ADS_COST_VIEW = "ads.cost.view"
    LEADERBOARD_VIEW = "leaderboard.view"
    REPORT_VIEW = "report.view"
    # Nhận nhắc việc và thông báo đẩy của chính mình (Bước 5).
    NOTIFICATION_RECEIVE = "notification.receive"


class Scope(enum.StrEnum):
    ALL = "all"  # Toàn workspace
    TEAM = "team"  # Nhóm mình phụ trách hoặc thuộc về, cộng bản thân
    OWN = "own"  # Chỉ của mình. Riêng bảng xếp hạng: điểm của mình + tên, hạng top 10


_A, _T, _O = Scope.ALL, Scope.TEAM, Scope.OWN

ROLE_GRANTS: Final = MappingProxyType(
    {
        MemberRole.OWNER: MappingProxyType({p: _A for p in Perm}),
        MemberRole.MANAGER: MappingProxyType(
            {
                Perm.BM_VIEW: _A,
                Perm.PAGE_ASSIGN: _A,
                Perm.TEAM_VIEW: _A,
                Perm.TEAM_MANAGE: _A,
                Perm.MEMBER_VIEW: _A,
                Perm.MEMBER_MANAGE: _A,
                Perm.LEAD_VIEW: _A,
                Perm.LEAD_UPDATE: _A,
                Perm.LEAD_REASSIGN: _A,
                Perm.LEAD_PHONE_VIEW: _A,
                Perm.REMINDER_SEND: _A,
                Perm.ADS_COST_VIEW: _A,
                Perm.LEADERBOARD_VIEW: _A,
                Perm.REPORT_VIEW: _A,
                Perm.NOTIFICATION_RECEIVE: _O,
            }
        ),
        MemberRole.TEAM_LEAD: MappingProxyType(
            {
                Perm.TEAM_VIEW: _T,
                Perm.MEMBER_VIEW: _T,
                Perm.LEAD_VIEW: _T,
                Perm.LEAD_PHONE_VIEW: _T,
                # Trưởng nhóm phụ trách Trang thì tự cập nhật khách của mình (quyết định #14).
                Perm.LEAD_UPDATE: _O,
                Perm.REMINDER_SEND: _T,
                Perm.LEADERBOARD_VIEW: _T,
                Perm.REPORT_VIEW: _T,
                Perm.NOTIFICATION_RECEIVE: _O,
            }
        ),
        MemberRole.STAFF: MappingProxyType(
            {
                Perm.LEAD_VIEW: _O,
                Perm.LEAD_UPDATE: _O,
                Perm.LEAD_PHONE_VIEW: _O,
                Perm.LEADERBOARD_VIEW: _O,
                Perm.NOTIFICATION_RECEIVE: _O,
            }
        ),
        MemberRole.VIEWER: MappingProxyType(
            {
                Perm.TEAM_VIEW: _A,
                Perm.MEMBER_VIEW: _A,
                Perm.LEAD_VIEW: _A,  # SĐT bị che vì không có LEAD_PHONE_VIEW
                Perm.ADS_COST_VIEW: _A,
                Perm.LEADERBOARD_VIEW: _A,
                Perm.REPORT_VIEW: _A,
                Perm.NOTIFICATION_RECEIVE: _O,
            }
        ),
    }
)

# Vai trò mà mỗi vai trò được phép cấp cho người khác.
ASSIGNABLE_ROLES: Final = MappingProxyType(
    {
        MemberRole.OWNER: frozenset(MemberRole),
        MemberRole.MANAGER: frozenset({MemberRole.TEAM_LEAD, MemberRole.STAFF, MemberRole.VIEWER}),
        MemberRole.TEAM_LEAD: frozenset(),
        MemberRole.STAFF: frozenset(),
        MemberRole.VIEWER: frozenset(),
    }
)


def scope_of(role: MemberRole, perm: Perm) -> Scope | None:
    return ROLE_GRANTS[role].get(perm)


def can(role: MemberRole, perm: Perm) -> bool:
    return perm in ROLE_GRANTS[role]


def can_manage_role(actor: MemberRole, target: MemberRole) -> bool:
    """Người có vai trò `actor` có được sửa người đang có vai trò `target` không."""
    return target in ASSIGNABLE_ROLES[actor]


def permissions_for(role: MemberRole) -> dict[str, str]:
    return {p.value: s.value for p, s in ROLE_GRANTS[role].items()}
