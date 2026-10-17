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

## E. Bước 3 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Tên khách | `contacts.display_name`: lấy từ form leadgen nếu có; chưa có thì hiện "Khách ···1234" (4 số cuối PSID). Tên thật qua Graph API khi có mã của Trang (Bước 6). | Webhook chỉ gửi PSID. |
| Nhận SĐT | Bỏ dấu cách, dấu chấm, dấu gạch giữa các chữ số rồi mới áp regex ở CLAUDE.md. Chỉ quét tin của khách. Số đầu tiên thành `leads.phone`; mọi số lưu ở `lead_phones`. | Khách hay gõ `0912 345 678`. |
| Gộp khách form với khách nhắn tin (#16) | Cùng Trang, cùng SĐT, trong cùng đợt. Giữ đợt nhắn tin, đợt form ghi `merged_into_lead_id` và ẩn khỏi danh sách. **Chỉ gộp khi đợt form vẫn Mới và chưa gọi**; đã có người cập nhật thì giữ cả hai. | Không làm mất kết quả nhân viên đã nhập. |
| Sản phẩm / dịch vụ khi chốt | Chưa làm (chưa có danh mục). Có ô ghi chú. | |
| Quá hạn 48 giờ | Tính lúc đọc: chưa có `result_at` và đã qua `result_due_at`. Không có job ghi sự kiện; nhắc việc làm ở Bước 5. | |
| Cập nhật kết quả | Chỉ chọn Hẹn lại / Chốt / Hủy, không quay về Mới / Đã liên hệ. Hẹn lại: giờ hẹn ở tương lai. Chốt: giá trị > 0. Hủy: có lý do, lý do "Khác" bắt buộc ghi chú. `result_at` là lần có kết quả **đầu tiên**, sửa sau không đổi. Nhân viên tự sửa trong 7 ngày kể từ `result_at`, sau đó chỉ Quản lý/Chủ sở hữu. Mọi lần sửa ghi `audit_logs` (không ghi SĐT). | Điểm "đúng hạn" (Bước 4) dựa vào lần cập nhật đầu. |
| Che SĐT | Backend che cả `leads.phone` lẫn số trong nội dung tin nhắn với người không có quyền xem SĐT của khách đó. | |
| Mở Business Suite | Nút dẫn tới hộp thư của Trang trong Business Suite. Đường dẫn tới đúng hội thoại kiểm tra lại khi ứng dụng Live. | Chưa xác minh được định dạng. |

## F. Bước 4 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Chăm Trang trước Bước 7 | Chưa có số bài đăng: bỏ tiêu chí khỏi tổng, chia lại trọng số của nó cho 5 tiêu chí còn lại theo đúng tỉ lệ. Giao diện ghi "Chưa có dữ liệu (Bước 7)". | Bài đăng chỉ đồng bộ ở Bước 7. |
| Khách chưa được trả lời | Chờ quá `speed_zero_minutes` (120 phút trong giờ làm việc) mà chưa trả lời thì tính bằng 120 phút (0 điểm tốc độ). Đang chờ ít hơn thì chưa tính. Khách từ form không tính tốc độ. | |
| Tập khách của kỳ | Khách có tin đầu tiên trong kỳ, gán cho nhân viên đó, không tính đợt form đã gộp. Tỉ lệ chốt = Chốt ÷ khách; Doanh thu = tổng giá trị đơn của các khách đó; % có SĐT = có SĐT ÷ khách; Đúng hạn = có kết quả trước hạn ÷ khách đã qua hạn hoặc đã có kết quả. Tốc độ = trung vị thời gian trả lời. | Mọi chỉ số tính trên cùng một tập khách. |
| Xếp phần trăm | Chỉ giữa những người đủ số khách tối thiểu: (số người thấp hơn + ½ số người bằng) ÷ (n − 1) × 100; n = 1 thì 100. | Quyết định #4. |
| Áp dụng công thức mới | Áp dụng ngay cho kỳ chưa chốt; tuần đã chốt (`is_final`) không bao giờ tính lại. Chủ sở hữu có nút "Tính lại ngay". | "Xem thử" phải khớp kết quả job. |
| Ai được tính điểm | Mọi người có khách trong kỳ hoặc phụ trách Trang trong kỳ (cả Trưởng nhóm/Quản lý, #14). Dưới số khách tối thiểu: "Chưa đủ dữ liệu", không hạng, không thứ hạng. | |
| Ai thấy bảng xếp hạng | Nhân viên: điểm của mình, tên và hạng top 10 (tắt `staff_can_see_leaderboard` thì chỉ của mình). Trưởng nhóm: người trong nhóm. Quản lý/Chủ sở hữu/Chỉ xem: tất cả. | Quyết định #9. |
| Ngưỡng hạng | Theo #1–#3 (85/70/50, tối thiểu 10 khách), không theo số mẫu trong `Staff.dc.html`. | |
| Lịch job | 01:00 giờ Việt Nam mỗi đêm: tính tuần hiện tại và các kỳ tham khảo (7 ngày, 30 ngày, tháng này). Đêm thứ Hai chốt tuần trước. Job xuyên workspace qua `app_active_workspace_ids()` (SECURITY DEFINER, chỉ trả danh sách id). | Worker không dùng tài khoản quản trị DB. |
| Chưa làm | Ghi chú huấn luyện, mục tiêu tuần, đổi Trang phụ trách / nhập Excel / thêm nhân viên (Bước 6), các phần khác của Cài đặt. | |

## G. Bước 5 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Ai dùng `/m` | Ai phụ trách Trang đều dùng được (cả Trưởng nhóm/Quản lý, #14). `/m` chỉ hiện khách của chính người đăng nhập. | |
| Ba tab | Cần xử lý = chưa có kết quả, xếp: quá hạn 48 giờ → chưa trả lời → có SĐT chưa gọi → còn lại. Hẹn lại = theo giờ hẹn. Đã xong = Chốt/Hủy trong 7 ngày gần nhất. | |
| Nút trên thẻ | Chốt / Hẹn / Hủy hiện với mọi khách; Gọi chỉ khi có SĐT. Gọi mở trình gọi (`tel:`) và tự đánh dấu "Đã gọi". Khách chưa được trả lời có nút "Trả lời trên Messenger". | |
| Bảng chọn | Hẹn: "Chiều nay 15:00", "Tối nay 19:00" (chỉ khi còn kịp), "Mai 9:00", "Chọn giờ khác". Hủy: 5 lý do, "Khác" bắt buộc ghi chú. | |
| Nhắc việc tự động | Job mỗi 5 phút, chỉ nhắc người phụ trách. Mỗi mốc nhắc một lần (`dedupe_key`): chờ 15 phút và 30 phút chưa trả lời (giờ làm việc); có SĐT 2 giờ chưa gọi; còn 4 giờ tới hạn 48 giờ và khi quá hạn; 15 phút trước giờ hẹn; quá giờ hẹn 24 giờ chưa cập nhật (#11). Ngoài giờ làm việc chỉ gửi nhắc giờ hẹn. | |
| Nhắc thủ công | Trưởng nhóm (khách trong nhóm), Quản lý/Chủ sở hữu (mọi khách) bấm "Nhắc người phụ trách" trên Hồ sơ khách (`reminder.send`). | |
| Web Push | VAPID (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`), thư viện `pywebpush`. Nội dung không có SĐT, không có nội dung tin nhắn. iPhone chỉ nhận khi đã thêm vào màn hình chính (iOS 16.4+). Endpoint trả 404/410 thì xóa đăng ký. | |
| Gợi ý lên hạng | "Thêm X điểm để lên hạng Y" và "Bạn còn N khách có SĐT chưa gọi". Không hứa trước kết quả. | Điểm là xếp phần trăm. |
| Biểu tượng | Chữ "P" trên màu chính, thay khi có tên và logo sản phẩm. | |
| Bộ nhớ đệm | Service worker chỉ lưu khung giao diện, không lưu dữ liệu API. | SĐT khách không nằm lại trên điện thoại. |
| Quyền mới | `notification.receive` cho cả 5 vai trò, phạm vi của mình. | Mọi route phải khai báo quyền. |
