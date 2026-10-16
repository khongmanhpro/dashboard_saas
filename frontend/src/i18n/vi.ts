// Toàn bộ chữ hiển thị trên giao diện. Thêm ngôn ngữ khác: tạo file cùng cấu trúc.
// Test src/i18n/i18n.test.ts chặn chữ tiếng Việt viết cứng ngoài thư mục này.

export const vi = {
  app: {
    name: "[Tên sản phẩm]",
    logoLetter: "P",
    sampleData: "Dữ liệu mẫu",
    later: "Sau",
    loading: "Đang tải…",
  },
  nav: {
    mainLabel: "Điều hướng chính",
    overview: "Tổng quan",
    staff: "Nhân viên",
    leads: "Khách hàng",
    pages: "Fanpage",
    ads: "Quảng cáo",
    inbox: "Inbox",
    bm: "Kết nối BM",
    settings: "Cài đặt",
  },
  roles: {
    owner: "Chủ sở hữu",
    manager: "Quản lý",
    team_lead: "Trưởng nhóm",
    staff: "Nhân viên",
    viewer: "Chỉ xem",
  },
  account: {
    logout: "Đăng xuất",
    changePassword: "Đổi mật khẩu",
  },
  login: {
    title: "Đăng nhập",
    email: "Email",
    password: "Mật khẩu",
    submit: "Đăng nhập",
    submitting: "Đang đăng nhập…",
  },
  changePassword: {
    title: "Đổi mật khẩu",
    firstLogin: "Đây là lần đăng nhập đầu. Hãy đặt mật khẩu mới để tiếp tục.",
    current: "Mật khẩu hiện tại",
    next: "Mật khẩu mới",
    confirm: "Nhập lại mật khẩu mới",
    hint: "Tối thiểu 10 ký tự, không trùng email.",
    mismatch: "Mật khẩu nhập lại không khớp.",
    submit: "Lưu mật khẩu mới",
    done: "Đã đổi mật khẩu.",
  },
  placeholder: {
    body: "Màn hình này làm ở Bước {step}.",
  },
  forbidden: {
    title: "Không có quyền",
    body: "Vai trò của bạn không xem được màn hình này.",
  },
  notFound: {
    title: "Không tìm thấy trang",
    back: "Về trang chính",
  },
  mobile: {
    title: "Khách của tôi",
    body: "Ứng dụng điện thoại cho nhân viên làm ở Bước 5.",
    desktop: "Mở bản máy tính",
  },
  errors: {
    invalid_credentials: "Email hoặc mật khẩu không đúng.",
    too_many_attempts: "Bạn nhập sai quá nhiều lần. Thử lại sau {minutes} phút.",
    password_too_short: "Mật khẩu cần tối thiểu 10 ký tự.",
    password_too_long: "Mật khẩu quá dài (tối đa 128 ký tự).",
    password_same_as_email: "Mật khẩu không được trùng email.",
    password_too_common: "Mật khẩu quá dễ đoán, hãy chọn mật khẩu khác.",
    password_unchanged: "Mật khẩu mới phải khác mật khẩu cũ.",
    wrong_current_password: "Mật khẩu hiện tại không đúng.",
    password_change_required: "Bạn cần đổi mật khẩu trước khi tiếp tục.",
    not_authenticated: "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.",
    csrf_failed: "Phiên làm việc không hợp lệ, hãy tải lại trang.",
    origin_not_allowed: "Yêu cầu không hợp lệ.",
    forbidden: "Bạn không có quyền thực hiện thao tác này.",
    network: "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.",
    unknown: "Có lỗi xảy ra, thử lại sau.",
  },
} as const;

export type Dictionary = typeof vi;
