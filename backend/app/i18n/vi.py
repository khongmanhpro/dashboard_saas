"""Chữ tiếng Việt của nhắc việc. Không đưa SĐT hay nội dung tin nhắn của khách vào đây."""

from __future__ import annotations

from app.models import NotificationType

UNNAMED = "Khách ···{ref}"

TITLES: dict[NotificationType, str] = {
    NotificationType.WAIT_15: "Khách đang chờ trả lời",
    NotificationType.WAIT_30: "Khách chờ quá 30 phút",
    NotificationType.PHONE_NOT_CALLED: "Có SĐT nhưng chưa gọi",
    NotificationType.DUE_SOON: "Sắp hết hạn cập nhật kết quả",
    NotificationType.OVERDUE: "Quá hạn cập nhật kết quả",
    NotificationType.CALLBACK_SOON: "Sắp tới giờ hẹn gọi lại",
    NotificationType.CALLBACK_MISSED: "Quá giờ hẹn chưa cập nhật",
    NotificationType.MANUAL: "Nhắc việc",
}

BODIES: dict[NotificationType, str] = {
    NotificationType.WAIT_15: "{name} đã chờ 15 phút chưa được trả lời.",
    NotificationType.WAIT_30: "{name} đã chờ 30 phút. Trả lời ngay để không bị tính chậm thêm.",
    NotificationType.PHONE_NOT_CALLED: (
        "{name} đã để lại số điện thoại hơn 2 giờ. Gọi khách rồi bấm Đã gọi."
    ),
    NotificationType.DUE_SOON: "Còn 4 giờ để cập nhật kết quả cho {name}.",
    NotificationType.OVERDUE: "{name} đã quá 48 giờ chưa có kết quả.",
    NotificationType.CALLBACK_SOON: "15 phút nữa tới giờ hẹn gọi lại {name} ({time}).",
    NotificationType.CALLBACK_MISSED: "Đã quá giờ hẹn với {name} một ngày, hãy cập nhật kết quả.",
    NotificationType.MANUAL: "{actor} nhắc bạn xử lý {name}.",
}

BM_TITLES: dict[str, str] = {
    "missing_permissions": "BM thiếu quyền",
    "disconnected": "BM mất kết nối",
}

BM_BODIES: dict[str, str] = {
    "missing_permissions": "{name} đang thiếu quyền. Vào Kết nối BM để xem và cấp lại quyền.",
    "disconnected": (
        "{name} đã mất kết nối (mã hết hạn hoặc bị thu hồi). Dán mã mới trong Kết nối BM."
    ),
}
