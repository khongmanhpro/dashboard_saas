from __future__ import annotations

import enum


class MemberRole(enum.StrEnum):
    OWNER = "owner"  # Chủ sở hữu
    MANAGER = "manager"  # Quản lý
    TEAM_LEAD = "team_lead"  # Trưởng nhóm
    STAFF = "staff"  # Nhân viên
    VIEWER = "viewer"  # Chỉ xem


class MemberStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
