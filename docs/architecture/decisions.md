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
| Biểu tượng | Chữ "P" trên màu chính, thay khi có tên và logo sản phẩm. Đã thay bằng logo GoCyberTech (17/10/2026, xem mục I). | |
| Bộ nhớ đệm | Service worker chỉ lưu khung giao diện, không lưu dữ liệu API. | SĐT khách không nằm lại trên điện thoại. |
| Quyền mới | `notification.receive` cho cả 5 vai trò, phạm vi của mình. | Mọi route phải khai báo quyền. |

## H. Bước 6 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Đọc từ Meta | Mã người dùng hệ thống "Dashboard": `debug_token` (hiệu lực, quyền, BM), `/me/accounts` (Trang + mã Trang), `/me/adaccounts`, `/{page}/subscribed_apps` với `messages, message_echoes, messaging_referrals, leadgen, feed`. Không tự tìm ra BM ID thì hỏi thêm ô "BM ID". | |
| Bảo mật mã | Chỉ Chủ sở hữu dán mã. Mã BM và mã Trang mã hóa Fernet, giao diện chỉ hiện 4 ký tự cuối. Gửi mã qua header `Authorization` (không trong URL) kèm `appsecret_proof`. Bước "Kiểm tra" không lưu mã; "Lưu" gửi lại mã và kiểm tra lại. | Mã không lọt vào log khi có lỗi. |
| Trang của workspace khác | Không theo dõi, ghi "Đang được workspace khác theo dõi", không nói là workspace nào. | Quyết định #22. |
| Kiểm tra 6 giờ | Job `check_bms`: kiểm tra mã và quyền, đánh dấu "Thiếu quyền"/"Mất kết nối", Trang mới tự xuất hiện và tự đăng ký webhook, nhắc việc trong app cho Chủ sở hữu khi trạng thái xấu đi (Telegram ở Bước 7). Ghi `sync_runs` kèm `X-Business-Use-Case-Usage`; lùi lại khi dùng quá 80%; lỗi giới hạn thì thử lại có backoff. | |
| Việc còn nợ | Lấy chi tiết form leadgen ở chế độ thật (và lấy bù các form "pending"); lấy tên thật của khách khi nhắn lần đầu, Meta không cho thì giữ "Khách ···1234". | Cần mã Trang. |
| Gán Trang | Quản lý / Chủ sở hữu (`page.assign`): bảng Trang chưa có người phụ trách và Tất cả Trang. Mọi lần đổi ghi `audit_logs`; khách cũ giữ người cũ. | |
| Cột Excel | Họ tên · Email · Nhóm · Vai trò (Nhân viên/Trưởng nhóm, trống = Nhân viên) · ID hoặc tên Trang. Trưởng nhóm làm trưởng của nhóm ghi trên dòng đó. Nhóm chưa có thì tạo. Email đã có thì cập nhật. | Cột "Trưởng nhóm" trong thiết kế không rõ nghĩa. |
| Mật khẩu tài khoản mới | Mật khẩu tạm ngẫu nhiên, bắt đổi lần đầu. Quản lý tải `mat-khau-tam.xlsx` **một lần** ngay sau khi nhập; không lưu trên máy chủ. Có email (Bước 7) thì đổi sang link đặt mật khẩu (#20). | Chưa gửi được email. |
| Kiểm tra dòng | Thiếu tên, email sai/trùng, Trang không có/trùng tên, Trang đã có người, 2 dòng cùng Trang, vai trò sai, dòng sửa Quản lý/Chủ sở hữu. Tối đa 500 dòng, 2 MB. Nhập dòng hợp lệ, bỏ dòng lỗi. `import_jobs` lưu nhật ký, không lưu file gốc. | |
| Thư viện | `openpyxl` + `defusedxml` (đọc .xlsx an toàn), `httpx` chuyển sang thư viện chạy thật. File tải lên gửi dạng nhị phân thô, không cần `python-multipart`. | |
| Thêm nhân viên | Nút "+ Thêm nhân viên" trên màn hình Nhân viên, dùng API tạo thành viên của Bước 1. | |
| Giả lập | Mã giả `MOCK-BM-1` (BM demo), `MOCK-BM-2` (BM thứ hai, 3 Trang mới), `MOCK-BM-NOLEADS` (thiếu quyền form), `MOCK-INVALID`. Chỉ nhận khi `MOCK_MODE=true`. | |

## I. Bước 7 (sếp duyệt 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Mức lưu số liệu QC | `ad_insights_daily` lưu cả 3 cấp (chiến dịch, nhóm, quảng cáo) theo ngày. Mỗi giờ lấy lại hôm nay và 2 ngày trước; lần đầu lấy bù 30 ngày. | Meta còn sửa số liệu vài ngày sau. |
| "Kết quả" | Tin nhắn bắt đầu + khách tiềm năng. Chiến dịch mục tiêu khác hiện "–". | Theo ghi chú trong Ads.dc.html. |
| Tần suất, ROAS | Tần suất nhiều ngày là **ước tính** (lượt hiển thị ÷ tổng tiếp cận theo ngày), giao diện ghi rõ. ROAS hiện "–". | Meta không cho cộng dồn tiếp cận. |
| Tỉ giá | `fx_rates` **theo workspace** (có RLS, khác data-model ban đầu). Chủ sở hữu nhập trong Cài đặt. Thiếu tỉ giá thì `spend_vnd = NULL` và cảnh báo "Thiếu tỉ giá". Không gọi API tỉ giá bên ngoài. | SaaS: không ai được sửa bảng toàn cục. |
| Gắn khách với QC | `leads.fb_ad_id` → `ads` → `ad_sets` → `campaigns`, ghi `leads.ad_id`, `leads.campaign_id`. Gắn ngay khi khách đến nếu QC đã có; chưa có thì job đồng bộ gắn bù. | |
| Chi phí mỗi khách | Chi tiêu chiến dịch trong ngày ÷ khách mới của chiến dịch trong ngày; "ngày" theo múi giờ tài khoản QC. Chi phí mỗi khách chốt = chi tiêu trong kỳ ÷ khách chốt trong tập khách có tin đầu tiên trong kỳ (như mục F). | CLAUDE.md mục 3 "Quảng cáo". |
| Bài đăng, insights Trang | Đồng bộ mỗi giờ, lấy bù 30 ngày. Tên metric của Meta kiểm lại khi ứng dụng Live; hiện chạy bằng fixture. | |
| Chăm Trang | Theo #5: `min(số bài trong kỳ / mục tiêu của kỳ, 1) × 100`, mục tiêu theo tuần quy đổi theo số ngày của kỳ. Bài tính cho người phụ trách Trang lúc đăng. Trang chưa đồng bộ được bài thì "chưa có dữ liệu", chia lại trọng số như mục F. Tuần đã chốt không tính lại. | Code Bước 4 đang xếp phần trăm, lệch #5. |
| Tab lọc Fanpage | Chưa có người phụ trách · Ít đăng bài (< 3 bài tuần này) · Giảm tương tác (lượt xem 7 ngày giảm ≥ 30% so với 7 ngày trước) · Mất kết nối. | |
| Thao tác hàng loạt trên Fanpage | Bỏ "Gán nhóm" / "Đổi người phụ trách" hàng loạt. Trang chưa có người thì chọn người ngay trên dòng (`page.assign`). Có "Xuất Excel". | Nhóm thuộc nhân viên, không thuộc Trang; 1 người – 1 Trang. |
| Chi tiết Trang | Làm tab Tổng quan và Bài viết; Đối tượng và Lịch đăng gắn "Sau". Bỏ "Lên lịch bài đăng" (chỉ có quyền đọc). Bảng nhiệt giờ đăng từ bài 30 ngày; dưới 10 bài thì "Chưa đủ bài để phân tích". | |
| Quy tắc trên màn Quảng cáo | Chỉ là cảnh báo (bật/tắt): chi phí/kết quả vượt ngưỡng, tần suất cao, chi phí/khách chốt cao. Không tạm dừng, không đổi ngân sách. | Quyết định #7. |
| Bảng chiến dịch | Thêm cột Khách · Chốt · Chi phí/khách chốt. Không làm "Chọn cột". | Mục tiêu chính của CLAUDE.md. |
| Tổng quan | Hôm nay / 7 ngày / 30 ngày / Tùy chọn (tối đa 90 ngày), so với kỳ liền trước cùng độ dài, lọc nhóm. Phễu bấm được, mở `/leads` đã lọc. Top / cần hỗ trợ lấy từ điểm 7 hoặc 30 ngày. "Xuất báo cáo" tải Excel. | |
| Theo vai trò | Trưởng nhóm: Tổng quan và Fanpage chỉ nhóm mình, backend không trả số tiền QC. Chỉ xem: tất cả. Nhân viên: không vào. Không thêm quyền mới; cấu hình cảnh báo dùng `settings.manage`. | |
| Điện thoại của sếp | Không làm app riêng. Tổng quan tự đổi bố cục khi màn hẹp (< 640px) theo Mobile.dc.html, thanh menu dưới. `/m` vẫn chỉ cho nhân viên. | |
| Telegram | Một bot cho cả hệ thống (`TELEGRAM_BOT_TOKEN` trong `.env`). Mỗi workspace một chat ID do Chủ sở hữu nhập, có nút "Gửi thử". Chưa tạo `member_telegram`. Email báo cáo tuần để sau (chưa có SMTP). | |
| Loại cảnh báo | BM mất kết nối / thiếu quyền; chiến dịch chi phí/kết quả > 25.000 ₫ khi đã chi ≥ 300.000 ₫ trong ngày; chi phí/khách chốt 7 ngày > ngưỡng; tần suất 7 ngày > 3,5; tóm tắt 08:00 mỗi sáng về hôm qua. Bật/tắt và sửa ngưỡng được. | |
| Gửi cảnh báo | Mỗi quy tắc × đối tượng × ngày gửi một lần, ghi `alert_deliveries`. Không có SĐT, không có nội dung tin nhắn. Mã bot không vào log, lỗi HTTP không kèm URL. MOCK_MODE không gửi thật, ghi `status = mock`. | |
| Thương hiệu | Tên sản phẩm **GoCyberTech**, logo gốc `docs/brand/gocybertech-logo.png`. Giao diện dùng phần biểu tượng và tên hai màu; không dùng câu "Autonomous IT & Cybersecurity" (không khớp sản phẩm). Màu giao diện giữ theo thiết kế. | Sếp gửi logo 17/10/2026. |
| Dữ liệu mẫu | Fixture QC (2 tài khoản, 1 dùng USD), bài đăng, insights cho 4 Trang demo. Seed tạo khoảng 30 ngày khách mẫu rồi chạy đồng bộ một lần. `make simulate` thêm tình huống khách từ QC gắn đúng chiến dịch. | |

## J. Một nguồn tính số liệu (sếp duyệt 17/10/2026)

Sau khi phát hiện số liệu lệch nhau giữa Tổng quan, Nhân viên, Fanpage. Định nghĩa chi tiết: `docs/metrics.md`.

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Nguồn tính | Mọi màn (Tổng quan, Fanpage, Nhân viên, Hồ sơ nhân viên, cảnh báo) lấy số khách từ `app/services/metrics.py`: một tập khách của kỳ, cùng một cách đếm, chỉ khác cách nhóm (theo Trang / theo người / tổng). | Ba cách đếm cũ (kỳ theo ngày, 168 giờ trôi, ảnh chụp điểm) cho ra 81 / 90 / 71. |
| Kỳ | Ngày trọn theo giờ workspace (Asia/Ho_Chi_Minh). "7 ngày" = hôm nay và 6 ngày trước, giống kỳ điểm 7 ngày. Bỏ cách đếm 168 giờ trôi ở Fanpage. Khối nào khác kỳ của màn hình thì ghi rõ kỳ ngay trên khối. | |
| Phễu | Lồng nhau: Khách mới ⊇ Đã trả lời ⊇ Có SĐT (trong số đã trả lời) ⊇ Đã gọi; chỗ rơi là hiệu đúng. Kết quả tách riêng: Chốt + Hủy + Hẹn lại + Đang chờ = Khách mới. Ô "Có số điện thoại %" và tiêu chí điểm vẫn đếm mọi khách có SĐT. | Khách có thể chốt ngay qua tin nhắn mà không bấm "Đã gọi". |
| Khách chưa có người phụ trách | Vẫn theo quy tắc cũ (không tính cho ai). /staff có dòng riêng "Chưa có người phụ trách" (không xếp hạng) để tổng các dòng = Tổng quan; Tổng quan có thẻ "khách chưa tính cho ai". Chủ sở hữu / Quản lý phụ trách Trang vẫn hiện ở /staff, có nhãn vai trò. | |
| Điểm | Kỳ chưa chốt (tuần này, 7 ngày, 30 ngày, tháng này) tính trực tiếp mỗi lần xem bằng đúng hàm của job, nên số khách và điểm luôn khớp. Job đêm vẫn chạy để chốt tuần và lưu lịch sử; tuần đã chốt đọc từ bảng lưu. | Ảnh chụp lúc 01:00 lệch với số đếm trực tiếp trong ngày. |
| Quá hạn 48 giờ | Thẻ cảnh báo Tổng quan: mọi thời điểm, ghi rõ "tất cả thời gian". Cột ở /staff, /pages, ô chỉ số: khách trong kỳ, ghi "trong kỳ". | |
| Thời gian trả lời | Mọi nơi dùng trung vị theo cách lấy mẫu của điểm tốc độ (khách chưa trả lời đã chờ ≥ 120 phút trong giờ làm việc tính là 120 phút). | |
| Hiển thị điểm | "Điểm đến từ đâu" ghi cách quy đổi từng tiêu chí (xếp hạng trong workspace, ngưỡng tốc độ, mục tiêu bài). Tiêu đề khối theo số người thật. Biểu đồ điểm theo tuần có trục giá trị và ngày đầu tuần. | |

## K. Chấm điểm theo ngưỡng tuyệt đối (sếp duyệt 17/10/2026)

Thay quyết định #4 và mục F phần "xếp phần trăm".

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Cách chấm | Tỉ lệ chốt, Doanh thu, % có SĐT, Cập nhật đúng hạn chấm theo **ngưỡng tuyệt đối** như Tốc độ trả lời: dưới ngưỡng "0 điểm" được 0, từ ngưỡng "100 điểm" trở lên được 100, ở giữa nội suy tuyến tính. Không còn xếp phần trăm. | Điểm của một người không còn phụ thuộc người khác; nhân viên biết cần đạt bao nhiêu. |
| Ngưỡng mặc định | Chốt 5% → 30%; Doanh thu 0 → 20 triệu/tuần; % có SĐT 30% → 80%; Đúng hạn 50% → 95%; Tốc độ giữ 120 → 5 phút. | |
| Doanh thu | Nhập theo tuần, quy theo số ngày đã qua của kỳ (như mục tiêu bài đăng). | Công bằng giữa kỳ 7 ngày, 30 ngày, tuần đang dở. |
| Sửa ngưỡng | Chủ sở hữu sửa trong Cài đặt → Công thức điểm, cả ngưỡng Tốc độ. Có "Xem thử" theo trọng số và ngưỡng mới trước khi lưu. Lưu là thêm phiên bản công thức; kỳ chưa chốt áp dụng ngay, tuần đã chốt giữ nguyên. | |
| Trang Nhân viên | Người có lượt phụ trách Trang kết thúc trong kỳ: hiện tên Trang và lúc kết thúc. | |
| Trang Fanpage | Khách của Trang trong kỳ thuộc hơn một người (tính cả "Chưa có người phụ trách", và người đang phụ trách dù 0 khách): hiện ghi chú số khách của từng người. | Giải thích vì sao số khách của Trang khác số khách của người đang phụ trách. |

## L. Tách test khỏi DB dev, phiên bản công thức, kỳ đếm bài (sếp yêu cầu 17/10/2026)

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Test không ghi vào DB dev | `make test`: DB `fanpage_test`, Redis db 15 (như cũ). `make simulate`: DB `fanpage_simulate_test` tạo mới mỗi lần, Redis db 14, gửi webhook trong tiến trình (không qua backend dev). `make e2e`: stack riêng (profile `e2e`): backend :8001, frontend :5174, worker, DB `fanpage_e2e_test`, Redis db 13. DB dev chỉ do `make seed` và người dùng ghi. Tên DB test bắt buộc kết thúc bằng `_test`. | `make simulate` từng ghi 108 khách giả lập và 14 lượt bàn giao Shop Thỏ vào workspace demo. |
| Phiên bản công thức | Bảng `score_formulas` có `score_method` (`percentile` / `threshold`). Bản cũ đánh dấu `percentile`; mỗi workspace thêm phiên bản mới `threshold` (thường là 2). | Đổi cách chấm phải thấy được trong lịch sử. |
| So sánh điểm khác công thức | Không tính lại tuần đã chốt (mục F). Chỗ so sánh ▲▼ với tuần trước và biểu đồ điểm theo tuần ghi chú "khác công thức" khi tuần đó dùng phiên bản công thức khác phiên bản đang áp dụng. | |
| Kỳ đếm bài đăng | Fanpage đếm bài cùng kỳ 7 ngày với các cột khác (thay "Bài tuần này"); mục tiêu quy theo số ngày như điểm Chăm Trang. Tổng quan, Nhân viên, Fanpage cùng một cách đếm. | |
| E2E tự dọn | `make e2e` chạy xong (pass hay fail) gọi `make e2e-down`: gỡ container e2e, xóa DB `fanpage_e2e_test`, dọn Redis db 13 (`python -m app.mock.sandbox drop`, chỉ nhận DB `_test` và Redis khác db 0). Khi bật, DB e2e luôn tạo lại từ đầu. `app.cli e2e-seed` từ chối DB không có đuôi `_test`. | Trước khi có stack riêng, `e2e-seed` ghi vào DB dev: workspace "E2E Playwright" (228 khách, 8 tài khoản, 3.078 dòng) đã được sao lưu rồi xóa ngày 17/10/2026. |
