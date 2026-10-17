# CLAUDE.md — Hệ thống đo lường nhân viên phụ trách Fanpage

File này là bối cảnh cho Claude Code. Đọc hết trước khi viết code. Gặp chỗ mâu thuẫn hoặc chưa rõ thì hỏi lại, không tự đoán.

## 1. Mục tiêu sản phẩm

Sếp chạy quảng cáo tập trung, đưa khách về khoảng 200 Fanpage. Mỗi nhân viên phụ trách đúng **1 Trang**. Hệ thống đo hiệu quả từng nhân viên qua Trang họ phụ trách:

- **Tốc độ trả lời** tin nhắn đầu tiên của khách
- **Lấy được số điện thoại**
- **Đã gọi cho khách** (nhân viên tự đánh dấu)
- **Kết quả:** Chốt / Hẹn lại / Hủy, kèm giá trị đơn hoặc lý do hủy
- **Doanh thu** (nhân viên nhập)
- **Chăm Trang:** đăng bài đủ mục tiêu

Hướng phát triển là SaaS bán cho doanh nghiệp khác. Code ngay từ đầu phải tách dữ liệu theo **workspace** (`workspace_id` ở mọi bảng nghiệp vụ).

**Chưa làm ở giai đoạn này:** tổng đài và ghi âm cuộc gọi, hộp thư chung (Inbox), Facebook Login for Business / App Review / Tech Provider.

## 2. Tài liệu tham chiếu

- **Kế hoạch chi tiết:** https://claude.ai/code/artifact/c52948d5-1eea-4b47-ac1e-ba33ec2736e5
- **Thiết kế 14 màn hình:** https://claude.ai/artifact/HkydySZzeGQLY75jak87Xx

Cả hai đều riêng tư, chủ tài khoản phải bấm Share thì mới mở được. Tên sản phẩm: **GoCyberTech** (logo ở `docs/brand/`). Giao diện code phải bám theo thiết kế: font Be Vietnam Pro, màu chính `#1F63B8`, nhấn `#EB6834`, nền `#F5F6F8`, viền `#E4E7EC`. Màu hạng: A `#1C5CAB`, B `#2A78D6`, C `#86B6EF`, D `#CDE2FB`.

## 3. Quy tắc nghiệp vụ (bắt buộc)

### Gán khách
- 1 nhân viên ↔ 1 Trang. Khách nhắn vào Trang nào thì tự tính cho người đang phụ trách Trang đó **tại thời điểm khách nhắn tin đầu tiên**.
- Đổi người phụ trách: khách cũ giữ người cũ, khách mới tính cho người mới. Lưu lịch sử gán vào bảng `page_assignments` (có `valid_from`, `valid_to`).
- Trang chưa có người phụ trách: khách vẫn được lưu nhưng `owner_id = NULL` và không tính điểm cho ai.
- **Một khách** = một cặp (Trang, PSID) trong một đợt. Khách im lặng hơn 30 ngày rồi nhắn lại thì mở đợt mới. *(Mặc định đề xuất, chờ sếp xác nhận.)*

### Thời gian trả lời
- Tính từ tin đầu tiên của khách trong đợt đến tin trả lời đầu tiên từ phía Trang.
- Tin trả lời gửi từ Meta Business Suite **vẫn phải được tính**: lấy qua trường webhook `message_echoes`. Loại bỏ tin tự động (chào mừng, trả lời nhanh tự động) nếu nhận biết được qua `app_id` hoặc metadata của echo.
- Chỉ đếm thời gian **trong giờ làm việc** (mặc định 08:00–22:00, múi giờ Asia/Ho_Chi_Minh). Khách nhắn 23:00 thì đồng hồ bắt đầu từ 08:00 sáng hôm sau.
- Ngưỡng trả lời chậm: 30 phút.

### Kết quả và hạn cập nhật
- Trạng thái khách: `new` → `contacted` → `callback` | `won` | `lost`.
- Hạn có kết quả (`won`, `lost` hoặc `callback` có giờ hẹn): **48 giờ** từ tin đầu tiên. Quá hạn thì bị trừ điểm "Cập nhật đúng hạn".
- `won` bắt buộc có giá trị đơn. `lost` bắt buộc có lý do: Giá cao, Ngoài khu vực, Không nghe máy, Đã mua nơi khác, Khác.

### Số điện thoại
- Tự nhận số điện thoại Việt Nam trong tin nhắn của khách: regex `(?:\+?84|0)(?:3|5|7|8|9)\d{8}`, chuẩn hóa về dạng `0xxxxxxxxx`. Lấy cả từ form khách hàng tiềm năng (`leadgen`).
- Che số trên giao diện cho vai trò "Chỉ xem": `09•• ••• 218`.

### Công thức điểm (0–100, tính lại mỗi đêm)

| Tiêu chí | Trọng số mặc định |
|---|---|
| Tỉ lệ chốt | 30% |
| Tốc độ trả lời | 25% |
| Doanh thu | 20% |
| % có số điện thoại | 10% |
| Chăm Trang (mục tiêu 5 bài/tuần) | 10% |
| Cập nhật đúng hạn | 5% |

- Sếp sửa được trọng số trong Cài đặt, tổng phải bằng 100. Lưu mỗi phiên bản công thức (`score_formulas`, có `effective_from`). Điểm các tuần đã tính giữ nguyên, không tính lại.
- Hạng: **A ≥ 85, B 70–84, C 50–69, D < 50**.
- Cách quy mỗi tiêu chí về 0–100 *(đề xuất, chờ sếp xác nhận)*:
  - Tốc độ trả lời: 100 điểm nếu ≤ 5 phút, 0 điểm nếu ≥ 120 phút, nội suy tuyến tính ở giữa.
  - Các tiêu chí còn lại: xếp phần trăm trong toàn workspace.
- Nhân viên có dưới 10 khách trong kỳ thì hiện "Chưa đủ dữ liệu", không xếp hạng.

### Vai trò
| Vai trò | Quyền |
|---|---|
| Chủ sở hữu | Toàn quyền, kết nối BM, dán mã truy cập, công thức điểm, thanh toán |
| Quản lý | Xem mọi nhân viên, Trang, quảng cáo; gán Trang; sửa nhóm |
| Trưởng nhóm | Xem và nhắc việc nhân viên trong nhóm; không thấy chi phí quảng cáo |
| Nhân viên | Chỉ khách của Trang mình; cập nhật kết quả; xem điểm của mình và top 10 |
| Chỉ xem | Báo cáo tổng, không thấy số điện thoại |

Kiểm tra quyền ở **tầng backend** cho mọi API, không chỉ ẩn trên giao diện.

### Quảng cáo
- Gắn khách với quảng cáo qua trường `referral` (`ad_id`) trong webhook tin nhắn, hoặc `ad_id` của form `leadgen`.
- Chi phí ước tính mỗi khách = chi tiêu của chiến dịch trong ngày ÷ số khách mới từ chiến dịch đó trong ngày.
- Chi phí mỗi khách chốt = chi tiêu ÷ số khách `won`.

## 4. Kết nối Meta

### Nhiều BM
Mỗi BM kết nối bằng **một người dùng hệ thống riêng** tên "Dashboard", vai trò Nhân viên, chỉ được gán đúng các quyền tài sản cần thiết. Thêm BM qua màn hình "Kết nối BM": dán mã → hệ thống kiểm tra quyền → liệt kê Trang và tài khoản quảng cáo → đăng ký webhook cho từng Trang.

### Quyền cần có
`pages_show_list`, `pages_read_engagement`, `read_insights`, `pages_read_user_content`, `pages_messaging`, `pages_manage_metadata`, `leads_retrieval`, `ads_read`, `business_management`

### Webhook
- Endpoint `GET/POST /webhooks/meta`. GET dùng để xác minh với `META_WEBHOOK_VERIFY_TOKEN`.
- **Bắt buộc** kiểm tra chữ ký `X-Hub-Signature-256` bằng `META_APP_SECRET`. Sai chữ ký thì trả 403.
- Trả 200 ngay, đẩy payload vào hàng đợi, xử lý ở worker. Xử lý phải idempotent theo `mid` / `leadgen_id`: Meta có thể gửi lặp.
- Trường cần đăng ký cho Trang: `messages`, `message_echoes`, `messaging_referrals`, `leadgen`, `feed`.
- Webhook chỉ chạy khi ứng dụng đã ở chế độ **Live**. Trong lúc chờ, dùng `MOCK_MODE=true` (mục 7).

### Đồng bộ định kỳ
- Mỗi giờ: insights Trang, bài đăng mới, chi tiêu quảng cáo theo chiến dịch.
- Mỗi 6 giờ: kiểm tra mã và quyền của từng BM, đánh dấu "Thiếu quyền" / "Mất kết nối" và gửi cảnh báo.
- Tôn trọng giới hạn gọi API: đọc header `X-Business-Use-Case-Usage`, lùi lại khi gần ngưỡng, retry có backoff.
- Phiên bản Graph API cố định trong `META_GRAPH_VERSION`. Không viết cứng trong code.

## 5. Bảo mật (không được vi phạm)

- **Chỉ chủ sở hữu tạo mã truy cập trong Meta và dán vào hệ thống.** Không bao giờ in mã ra log, trả về qua API, ghi vào file hay commit vào git.
- Mã lưu trong DB phải được mã hóa (Fernet, khóa trong `TOKEN_ENCRYPTION_KEY`). Giao diện chỉ hiện 4 ký tự cuối.
- `.env` nằm trong `.gitignore`. Chỉ commit `.env.example` với giá trị rỗng.
- Không dùng quyền "quản lý hoàn toàn" Trang cho người dùng Dashboard. Chỉ đọc số liệu và nhận tin nhắn.
- Dữ liệu mẫu và fixture dùng tên giả (`[Khách 1042]`, `[Nhân viên 186]`). Không đưa tên hoặc số điện thoại thật của khách vào repo.
- Log có số điện thoại thì che bớt.

## 6. Công nghệ

| Lớp | Lựa chọn |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| CSDL | PostgreSQL 16 (thời gian lưu UTC, hiển thị theo múi giờ của workspace) |
| Hàng đợi & lịch | Redis + `arq` (worker webhook, đồng bộ định kỳ, tính điểm ban đêm) |
| Frontend | React + Vite + TypeScript. Ứng dụng điện thoại cho nhân viên là PWA trong cùng project, đường dẫn `/m` |
| Kiểm thử | pytest; Playwright cho luồng giao diện chính |
| Triển khai | Docker Compose trên VPS, Caddy làm reverse proxy và HTTPS |

Quy ước:
- **Ngôn ngữ:** code, tên bảng và tên biến bằng tiếng Anh; chữ trên giao diện bằng tiếng Việt, gom vào file ngôn ngữ để sau này dịch được.
- **Kiểu dữ liệu:** tiền là số nguyên VND (`BIGINT`), không dùng float. Mọi `datetime` có múi giờ.
- **Kiểm thử:** mỗi quy tắc ở mục 3 phải có test, đặc biệt các trường hợp biên của thời gian trả lời: ngoài giờ, qua đêm, echo tự động.

### Cấu trúc thư mục dự kiến
```
backend/
  app/
    api/          # router FastAPI theo mô-đun
    core/         # config, bảo mật, mã hóa token, phân quyền
    models/       # SQLAlchemy
    services/     # nghiệp vụ: assignment, response_time, scoring, phone_extract
    meta/         # client Graph API, xử lý webhook, đồng bộ
    workers/      # job arq
  migrations/
  tests/
frontend/
  src/
    pages/        # theo 14 màn hình thiết kế
    mobile/       # PWA nhân viên
    components/
docker-compose.yml
.env.example
```

## 7. Chế độ giả lập

`MOCK_MODE=true` thì:
- Không gọi Graph API thật. Đọc dữ liệu từ `backend/tests/fixtures/`.
- Có lệnh `python -m app.mock.simulate` phát sự kiện webhook giả (khách nhắn, echo trả lời, gửi SĐT, form leadgen) cho 4 Trang demo: Phần Mềm Giá Rẻ, FISS, Shop Thỏ, Mua Sắm Thông Minh.
- Giao diện hiện nhãn "Dữ liệu mẫu" như trong thiết kế.

## 8. Thứ tự làm và tiêu chí "xong"

1. **Khung dự án:** Docker Compose chạy được backend, DB, Redis, frontend; migration đầu tiên; đăng nhập theo vai trò. *Xong khi* `docker compose up` chạy sạch và test pass.
2. **Webhook & thời gian trả lời:** nhận và xác thực webhook, tạo khách, tính thời gian trả lời theo mục 3. *Xong khi* chạy giả lập ra đúng số phút cho các tình huống biên, và chạy thật trên 4 Trang demo khi ứng dụng đã Live.
3. **Khách hàng:** nhận SĐT, màn hình Khách hàng (cột và bảng), Hồ sơ khách, cập nhật kết quả, hạn 48 giờ. *Xong khi* đi trọn luồng Mới → Chốt có giá trị đơn.
4. **Điểm & xếp hạng:** job ban đêm, màn hình Nhân viên và Hồ sơ nhân viên, sửa công thức trong Cài đặt. *Xong khi* đổi trọng số thì "xem thử" khớp với kết quả job.
5. **Ứng dụng nhân viên (PWA):** Khách của tôi, nút Gọi / Chốt / Hẹn / Hủy, nhắc việc. *Xong khi* cài được lên màn hình chính Android và iPhone.
6. **Nhiều BM & nhập Excel:** màn hình Kết nối BM, kiểm tra quyền, gán Trang, nhập nhân viên và gán Trang bằng Excel. *Xong khi* thêm BM thứ hai mà không cần sửa code.
7. **Quảng cáo & Tổng quan:** đồng bộ chi tiêu, chi phí mỗi khách và mỗi khách chốt, màn hình Tổng quan, Fanpage, Quảng cáo, cảnh báo Telegram.

Sau bước 7: chạy thử 2 tuần với 4 Trang và 4–10 nhân viên thật, rồi mới mở cho toàn bộ.

## 9. Việc còn chờ phía Facebook (không chặn việc code)

- Hoàn thiện cài đặt cơ bản của ứng dụng (chính sách quyền riêng tư, icon, danh mục) và chuyển sang **Live**.
- Thu hẹp quyền của người dùng Dashboard trên Trang Mua Sắm Thông Minh và Phần Mềm Giá Rẻ.
- Xác minh doanh nghiệp FISSOLUTION đang chờ Meta duyệt.

## 10. Trạng thái hiện tại và cách làm việc (bàn giao, cập nhật 17/10/2026)

Đọc mục này trước khi làm tiếp. Chi tiết từng quyết định ở `docs/architecture/decisions.md` (mục A–I, **ưu tiên hơn CLAUDE.md** nếu khác nhau), mô hình dữ liệu ở `data-model.md`, phân quyền ở `rbac.md`, cách chạy ở `README.md`.

### Tiến độ
- **Xong Bước 1–7** (mục 8). Commit đầu mỗi bước là `docs: chốt quyết định Bước N`. Bước 7: quyết định ở `decisions.md` mục I, migration 0008.
- Việc còn nợ:
  - Thử với Meta thật khi ứng dụng Live: webhook trên 4 Trang demo, kết nối BM bằng mã thật (README mục "Nối với Meta thật"). Kiểm lại tên metric Trang/bài đăng trong `PAGE_METRICS` và `post_media_view` (`app/meta/graph.py`), và cách Meta trả `actions` của insights.
  - Thử Telegram thật (README mục "Bật cảnh báo Telegram thật").
  - Cài PWA lên Android/iPhone thật qua HTTPS (README mục "Kiểm tra cài lên điện thoại thật").
  - Đổi sang gửi link đặt mật khẩu qua email (#20) và email báo cáo tuần khi có SMTP.
  - Ô "Sản phẩm / dịch vụ" khi chốt đơn chưa làm. Tab Đối tượng, Lịch đăng của Chi tiết Trang, Telegram riêng từng nhân viên (`member_telegram`): giai đoạn sau.

### Cách làm việc đã thống nhất với sếp
- Giao tiếp bằng **tiếng Việt**, câu ngắn, rõ.
- Mỗi bước: đọc thiết kế liên quan trong `docs/design/` → đưa **kế hoạch ngắn kèm các quyết định cần duyệt** → **dừng chờ duyệt** → ghi quyết định vào `decisions.md` (mục mới) → code.
- **Commit nhỏ, mỗi commit một việc**, message tiếng Việt kiểu `feat(phạm vi): …`. **Chỉ push khi sếp bảo.**
- Trước khi báo xong phải chạy và báo kết quả thật của: `make test`, `make lint`, `make test-frontend`, `make e2e`, `make simulate`.
- Dữ liệu mẫu chỉ dùng tên giả (`[Khách 1042]`, `[Nhân viên 186]`). Không đưa mã truy cập, mật khẩu, SĐT thật vào code, log hay git.

### Quy ước kỹ thuật dễ sai
- **Test và lệnh quản trị chạy trong container `migrate`** (có tài khoản quản trị DB). API và worker chỉ dùng tài khoản ứng dụng, bị RLS.
- Việc phải đọc xuyên workspace dùng **hàm SECURITY DEFINER chỉ trả id**, không dùng tài khoản quản trị: `app_route_page` (0002), `app_purge_expired_data` (0003), `app_active_workspace_ids` (0005).
- **Bảng mới có `workspace_id`:** gọi `enable_tenant_rls` + `grant_app` (`migrations/helpers.py`). `test_schema_invariants` và `test_migrations` (so model với migration) phải pass.
- **Sau `alembic revision --autogenerate`** phải sửa tay hai chỗ: `sa.Enum(...)` → `sa.String(length=32)`, và xóa các `CheckConstraint(..., name="xxx")` trùng tên (giữ bản `op.f(...)`). Ghi chú đầu migration bằng tiếng Việt.
- **Thêm thư viện:** `docker compose run --rm -T migrate uv add <gói>`, rồi `docker compose build migrate backend worker`, rồi `docker compose up -d`. Chỉ `restart` thì container vẫn dùng image cũ.
- **Frontend:** mọi chữ giao diện nằm trong `frontend/src/i18n/vi.ts`; test `i18n.test.ts` fail nếu có chữ tiếng Việt ở chỗ khác. Màu lấy từ `styles/tokens.css`.
- **Mọi route phải có `require(Perm.X)`** (`test_route_protection`). Thêm quyền thì sửa đồng thời `core/rbac.py`, `tests/unit/test_rbac.py`, `docs/architecture/rbac.md`.
- Lỗi 422 không được trả lại giá trị người dùng gửi (đã có handler trong `main.py`).
- **MOCK_MODE:** client Graph giả đọc `backend/tests/fixtures/meta/graph_mock.json`; mã giả `MOCK-BM-1` (BM demo, seed tự gắn), `MOCK-BM-2`, `MOCK-BM-NOLEADS`, `MOCK-INVALID`, `MOCK-BM-E2E` và `MOCK-BM-E2E-ADS` (chỉ cho e2e). Số liệu QC/bài đăng giả sinh từ mục `content`, cố định theo ngày. Telegram giả: không gửi thật.
- **Số liệu khách và điểm chỉ tính qua `app/services/metrics.py`** (tập khách của kỳ + `summarize`), định nghĩa ở `docs/metrics.md`, quyết định mục J. Không màn nào tự đếm riêng; kỳ chưa chốt tính điểm trực tiếp (`score_service.live_period`). `test_metrics_consistency` kiểm tra Tổng quan = /staff = /pages.
- **Báo cáo:** khoảng thời gian dùng `app/services/report_range.py`; số liệu QC dùng chung `app/services/ads_service.py` (Tổng quan, Quảng cáo, cảnh báo đều qua `level_stats`). Handler/service ghi phải tự `db.commit()`.
- **Test không bao giờ ghi vào DB dev** (decisions.md mục L): `make test` → `fanpage_test`, `make simulate` → `fanpage_simulate_test`, `make e2e` → stack riêng `fanpage_e2e_test` (backend :8001, frontend :5174), chạy xong tự xóa DB e2e (`make e2e-down`). Kiểm tra số liệu bằng mắt trên DB dev thì chỉ đọc, không chạy lệnh ghi.
- **E2E:** `frontend/e2e/global-setup.ts` gọi `python -m app.cli e2e-seed` (chỉ chạy trên DB `_test`) để tạo tài khoản và khách mới mỗi lần chạy; test phải chạy lại nhiều lần vẫn pass. Gọi API thẳng thì dùng backend e2e (`E2E_API_URL`, mặc định :8001).
- **Công thức điểm:** đổi cách chấm hay trọng số là thêm phiên bản (`score_formulas.version`, `score_method`); tuần đã chốt không tính lại, giao diện ghi "khác công thức".

### Chuyển sang máy khác
1. Cài Docker Desktop, Node 22, Python 3. Rồi `git clone` repo.
2. `make env`: tạo `.env` mới với bí mật ngẫu nhiên, gồm cả khóa VAPID và `META_APP_SECRET` giả cho MOCK_MODE. `.env` không nằm trong git.
3. `make up`, rồi `make seed`, rồi `make simulate` (kết quả phải là 15/15, chạy trên DB riêng).
4. Chạy test giao diện: `cd frontend && npm ci && npx playwright install chromium`, rồi `make test-frontend` và `make e2e`.
5. DB dev không đi theo git: máy mới bắt đầu từ dữ liệu demo do seed tạo. Mã Meta thật (nếu có) phải dán lại trên máy mới, vì `TOKEN_ENCRYPTION_KEY` mới không giải mã được dữ liệu cũ.
