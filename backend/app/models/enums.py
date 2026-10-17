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


class ConnectionStatus(enum.StrEnum):
    """Trạng thái kết nối của BM hoặc Trang."""

    ACTIVE = "active"
    MISSING_PERMISSIONS = "missing_permissions"  # Thiếu quyền
    DISCONNECTED = "disconnected"  # Mất kết nối


class WebhookEventStatus(enum.StrEnum):
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


class LeadSource(enum.StrEnum):
    MESSAGE = "message"
    LEADGEN = "leadgen"


class LeadStatus(enum.StrEnum):
    NEW = "new"  # Mới
    CONTACTED = "contacted"  # Đã liên hệ
    CALLBACK = "callback"  # Hẹn lại
    WON = "won"  # Chốt
    LOST = "lost"  # Hủy


class LostReason(enum.StrEnum):
    PRICE = "price"  # Giá cao
    OUT_OF_AREA = "out_of_area"  # Ngoài khu vực
    NO_ANSWER = "no_answer"  # Không nghe máy
    BOUGHT_ELSEWHERE = "bought_elsewhere"  # Đã mua nơi khác
    OTHER = "other"  # Khác


class MessageDirection(enum.StrEnum):
    IN = "in"  # Khách gửi Trang
    OUT = "out"  # Trang gửi khách (echo)


class LeadEventType(enum.StrEnum):
    CREATED = "created"
    REPLIED = "replied"
    PHONE_DETECTED = "phone_detected"
    CALLED = "called"
    STATUS_CHANGED = "status_changed"
    OVERDUE = "overdue"
    REMINDER_SENT = "reminder_sent"
    REASSIGNED = "reassigned"
    MERGED = "merged"  # Gộp đợt form vào đợt nhắn tin cùng SĐT


class LeadgenFetchStatus(enum.StrEnum):
    FETCHED = "fetched"
    PENDING = "pending"  # Chưa lấy được chi tiết form (cần mã của Trang)


class PeriodType(enum.StrEnum):
    WEEK = "week"  # Kỳ chính thức: T2–CN theo múi giờ workspace (quyết định #18)
    ROLLING_7 = "rolling_7"
    ROLLING_30 = "rolling_30"
    MONTH = "month"


class Tier(enum.StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class NotificationType(enum.StrEnum):
    """Loại nhắc việc (quyết định Bước 5)."""

    WAIT_15 = "wait_15"  # Khách chờ 15 phút chưa được trả lời
    WAIT_30 = "wait_30"  # Khách chờ 30 phút (ngưỡng trả lời chậm)
    PHONE_NOT_CALLED = "phone_not_called"  # Có SĐT 2 giờ chưa gọi
    DUE_SOON = "due_soon"  # Còn 4 giờ tới hạn 48 giờ
    OVERDUE = "overdue"  # Quá hạn 48 giờ chưa có kết quả
    CALLBACK_SOON = "callback_soon"  # 15 phút trước giờ hẹn
    CALLBACK_MISSED = "callback_missed"  # Quá giờ hẹn 24 giờ chưa cập nhật
    MANUAL = "manual"  # Trưởng nhóm / Quản lý bấm Nhắc
