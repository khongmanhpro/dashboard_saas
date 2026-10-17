# Quyết định đã chốt

Sếp duyệt ngày 17/10/2026, cùng lúc duyệt kế hoạch Bước 1. Nếu chỗ nào khác với CLAUDE.md thì theo file này, và cập nhật lại CLAUDE.md khi có dịp.

## A. Chỗ tài liệu mâu thuẫn

| # | Vấn đề | Quyết định |
|---|---|---|
| 1 | Ngưỡng hạng (Staff.dc.html dùng 80/60/40) | **A ≥ 85, B 70–84, C 50–69, D < 50** theo CLAUDE.md. Lưu trong `score_formulas`. |
| 2 | Tốc độ trả lời 0 điểm (60 hay 120 phút) | **120 phút**, là tham số của công thức (`speed_zero_minutes`). 100 điểm khi ≤ 5 phút. |
| 3 | Số khách tối thiểu để xếp hạng | **10** khách trong kỳ. |
| 4 | Cách quy đổi tiêu chí về 0–100 | Tốc độ: nội suy tuyến tính. Các tiêu chí còn lại: **xếp phần trăm trong workspace**. |
| 5 | Định nghĩa "Chăm Trang" | MVP chỉ đếm bài đăng: `min(số bài / mục tiêu, 1) × 100`, mục tiêu 5 bài/tuần. |
| 6 | Một nhân viên nhiều Trang | CSDL cho phép N Trang mỗi nhân viên. Cài đặt "1 nhân viên – 1 Trang" **bật mặc định**. Một Trang **không bao giờ** có 2 người phụ trách cùng lúc (ràng buộc trong DB). |
| 7 | Luật tự động tạm dừng hoặc tăng ngân sách quảng cáo | **Không làm.** Bước 7 chỉ gửi cảnh báo. Hệ thống chỉ có quyền đọc. |
| 8 | Thư viện nội dung (đăng bài lên nhiều Trang) | **Ngoài phạm vi** giai đoạn này. |
| 9 | Nhân viên xem bảng xếp hạng | Thấy tên và hạng của top 10; **chỉ thấy điểm của chính mình**. |

## B. Nghiệp vụ

| # | Câu hỏi | Quyết định |
|---|---|---|
| 10 | `new → contacted` | Tự chuyển khi Trang có tin trả lời đầu tiên (không tính echo tự động). |
| 11 | Hẹn lại nhưng quá giờ hẹn | Nhắc việc khi quá `callback_at` + 24 giờ. Điểm "đúng hạn" chỉ xét mốc 48 giờ đầu. |
| 12 | Sửa kết quả đã lưu | Nhân viên tự sửa trong 7 ngày, sau đó chỉ Quản lý/Chủ sở hữu. Mọi lần sửa ghi `audit_logs`. |
| 13 | Nhân viên nghỉ việc | Quản lý chuyển từng khách cho người khác, có ghi lịch sử. Điểm tính cho người nhận kể từ lúc chuyển. |
| 14 | Trưởng nhóm/Quản lý phụ trách Trang | Được. **Vai trò và việc phụ trách Trang độc lập nhau.** Ai phụ trách Trang đều có điểm. |
| 15 | Giờ làm việc | Áp dụng 7 ngày/tuần, cấu hình theo workspace. Bảng ngày nghỉ làm sau. |
| 16 | Khách từ form leadgen | Không đo thời gian trả lời. Gộp với khách nhắn tin nếu cùng Trang, cùng SĐT, trong cùng đợt. |
| 17 | Tài khoản quảng cáo không dùng VND | Lưu chi tiêu theo tiền gốc kèm mã tiền tệ, quy đổi sang VND qua bảng `fx_rates`. |
| 18 | Kỳ tính điểm | Kỳ chính thức là **tuần T2–CN** theo múi giờ workspace. Mỗi đêm tính lại tuần hiện tại, hết Chủ nhật thì chốt (`is_final`). Các khoảng 7 ngày / 30 ngày / tháng chỉ để tham khảo. |
| 19 | Lưu nội dung tin nhắn | **180 ngày**, sau đó xóa nội dung, giữ số liệu. |
| 20 | Đăng nhập | Email + mật khẩu. Quản lý tạo tài khoản; hệ thống gửi link đặt mật khẩu (hạn 72 giờ). Người không có email: Quản lý đặt mật khẩu tạm, hệ thống bắt đổi ở lần đăng nhập đầu. |
| 21 | Một người thuộc nhiều workspace | CSDL hỗ trợ (`users` + `workspace_members`). Giao diện hiện chỉ dùng 1 workspace. |
| 22 | Hai workspace cùng theo dõi một Trang | Không cho phép. |

## C. Kỹ thuật

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Migration | Thiết kế đủ 7 bước (xem `data-model.md`), nhưng mỗi bước chỉ tạo bảng của bước đó. | Trong DB không có bảng nào chưa có code và test. |
| Tách tenant | (1) Truy vấn luôn lọc `workspace_id`, khóa ngoại ghép `(workspace_id, id)`. (2) **Row-Level Security** của Postgres với `SET LOCAL app.workspace_id`. Ứng dụng dùng role `*_app`, role này không bỏ qua được RLS. | Lỡ quên lọc ở một câu truy vấn cũng không lộ dữ liệu workspace khác. |
| Phiên đăng nhập | Session lưu phía server; DB chỉ giữ HMAC của token. Cookie `HttpOnly; Secure; SameSite=Lax`. Có CSRF token cho mọi request ghi. | Không dùng JWT trong localStorage (dễ bị XSS lấy mất, khó thu hồi). |
| Mật khẩu | argon2id, tối thiểu 10 ký tự. Giới hạn số lần đăng nhập sai qua Redis. | |
| Mã truy cập Meta | Fernet; `TOKEN_ENCRYPTION_KEY` nhận nhiều khóa cách nhau dấu phẩy để xoay khóa (khóa đầu dùng để mã hóa). | |
| ID | UUIDv7 sinh ở ứng dụng. | Sắp theo thời gian, index gọn hơn UUIDv4. |
| Log | JSON, tự che SĐT, chuỗi giống mã truy cập, header Authorization/Cookie. | |

## D. Bước 2 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Định tuyến webhook | API chỉ kiểm tra chữ ký rồi đẩy vào hàng đợi, không ghi DB. Worker gọi `app_route_page(fb_page_id)` (SECURITY DEFINER, chỉ trả `workspace_id`), đặt workspace rồi mới ghi. `webhook_events.workspace_id` NOT NULL và bật RLS. | Worker không được dùng tài khoản quản trị DB. |
| `messages.contact_id`, `lead_id` được NULL | Lưu được echo đến trước tin của khách và tin Trang nhắn trước. | Meta có thể gửi sai thứ tự. |
| Thời gian trả lời | Tính lại từ dữ liệu trong DB: tin đầu tiên = tin khách sớm nhất của đợt; trả lời = echo không tự động sớm nhất sau mốc đó. | Kết quả đúng kể cả khi Meta gửi lặp hoặc sai thứ tự. |
| Echo tự động | `app_id` nằm trong `META_AUTOMATED_APP_IDS` (mặc định rỗng) thì không tính. Echo khác, kể cả từ Business Suite, là người trả lời. Worker log số echo theo `app_id` để điền danh sách khi ứng dụng Live. | Meta không đánh dấu rõ tin tự động. |
| Hạn lưu dữ liệu | Job arq `purge_expired_data` chạy 02:30 giờ Việt Nam mỗi đêm, gọi `app_purge_expired_data(30, 180)` (SECURITY DEFINER, migration 0003): xóa `webhook_events` cũ hơn 30 ngày, đặt `messages.text = NULL` cho tin cũ hơn 180 ngày. Hàm từ chối ngưỡng nhỏ hơn 30 / 180, trả về số dòng; log chỉ ghi số đếm. | Worker không được dùng tài khoản quản trị DB, mà job chạy xuyên mọi workspace. |
| Để sau | Nhận SĐT trong tin nhắn và gộp khách leadgen với khách nhắn tin: Bước 3. Khách chưa được trả lời tính điểm thế nào: Bước 4. | |
