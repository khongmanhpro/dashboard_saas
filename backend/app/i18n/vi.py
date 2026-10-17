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

# ---------------------------------------------------------------- xuất Excel (Bước 7)

EXPORT_OVERVIEW_SHEET = "Tong quan"
EXPORT_CAMPAIGN_SHEET = "Chien dich"
EXPORT_PAGES_SHEET = "Fanpage"
EXPORT_OVERVIEW_HEADER = ["Chỉ số", "Kỳ này", "Kỳ trước"]
EXPORT_OVERVIEW_ROWS = {
    "new_leads": "Khách mới",
    "median_response_seconds": "Trả lời (trung vị, giây)",
    "phone_rate": "Có số điện thoại (%)",
    "close_rate": "Tỉ lệ chốt (%)",
    "revenue_vnd": "Doanh thu (₫)",
    "cost_per_won_vnd": "Chi phí / khách chốt (₫)",
}
EXPORT_RANGE = "Khoảng thời gian: {first} – {last}"
EXPORT_CAMPAIGN_HEADER = ["Chiến dịch", "Chi tiêu (₫)", "Khách", "Chốt", "Chi phí / chốt (₫)"]
EXPORT_PAGES_HEADER = [
    "Trang",
    "ID Trang",
    "BM",
    "Người phụ trách",
    "Điểm",
    "Hạng",
    "Khách 7 ngày",
    "Trả lời TB (phút)",
    "Chốt 7 ngày",
    "Bài 7 ngày",
    "Lượt xem 30 ngày",
    "Trạng thái",
]
EXPORT_PAGE_STATUS = {
    "ok": "Hoạt động",
    "declining": "Giảm tương tác",
    "disconnected": "Mất kết nối",
}

# ---------------------------------------------------------------- cảnh báo Telegram (Bước 7)
# Không đưa SĐT hay nội dung tin nhắn của khách vào tin cảnh báo.

ALERT_TEXTS: dict[str, str] = {
    "test": "Kết nối Telegram thành công. Cảnh báo của {workspace} sẽ gửi vào đây.",
    "bm_missing_permissions": (
        "BM thiếu quyền: {name}. Vào Kết nối BM để xem và cấp lại quyền.\n{link}"
    ),
    "bm_disconnected": (
        "BM mất kết nối: {name}. {pages} Trang dừng cập nhật. Dán mã mới trong Kết nối BM.\n{link}"
    ),
    "cost_per_result": (
        "Chiến dịch {name}: chi phí/kết quả hôm nay {value} (ngưỡng {limit}), "
        "đã chi {spend}.\n{link}"
    ),
    "cost_per_won": (
        "Chiến dịch {name}: chi phí/khách chốt 7 ngày {value} (ngưỡng {limit}). "
        "Đã chi {spend}, chốt {won} khách.\n{link}"
    ),
    "cost_per_won_none": (
        "Chiến dịch {name}: đã chi {spend} trong 7 ngày nhưng chưa chốt khách nào "
        "(ngưỡng {limit}).\n{link}"
    ),
    "frequency": (
        "Chiến dịch {name}: tần suất 7 ngày khoảng {value} lần mỗi người (ngưỡng {limit}). "
        "Khách đã thấy quảng cáo nhiều lần.\n{link}"
    ),
    "daily_summary": (
        "Tóm tắt ngày {date} · {workspace}\n"
        "Khách mới: {new}\n"
        "Chốt: {won} · Doanh thu: {revenue}\n"
        "Chi tiêu quảng cáo: {spend} · Chi phí/khách chốt: {cpw}\n"
        "Khách quá 48 giờ chưa có kết quả: {overdue}\n{link}"
    ),
}
NO_VALUE = "–"
