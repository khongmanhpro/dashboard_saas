# Hệ thống đo lường nhân viên phụ trách Fanpage

Bối cảnh sản phẩm và quy tắc nghiệp vụ: [CLAUDE.md](CLAUDE.md). Các quyết định đã chốt: [docs/architecture/decisions.md](docs/architecture/decisions.md). Mô hình dữ liệu cho cả 7 bước: [docs/architecture/data-model.md](docs/architecture/data-model.md). Phân quyền: [docs/architecture/rbac.md](docs/architecture/rbac.md).

**Trạng thái:** xong Bước 1–6 (khung dự án, webhook Meta và thời gian trả lời, Khách hàng, điểm và xếp hạng, ứng dụng điện thoại, nhiều BM và nhập Excel). Còn Bước 7 (quảng cáo, Tổng quan, Fanpage, cảnh báo Telegram).

## Chạy trên máy dev

Cần Docker Desktop, Python 3 (chỉ để chạy script tạo `.env`) và Node 22 nếu muốn chạy test giao diện.

```bash
make env     # tạo .env với bí mật ngẫu nhiên (không ghi đè nếu đã có)
make up      # db, redis, migrate, backend, worker, frontend
make seed    # dữ liệu demo: 5 vai trò, 4 Trang demo, mật khẩu ghi vào backend/.dev-credentials
make simulate  # giả lập webhook cho 4 Trang demo, in số phút trả lời so với mong đợi
```

`make simulate` đọc kịch bản trong `backend/tests/fixtures/meta/simulate_scenarios.json`, ký payload bằng `META_APP_SECRET`, gửi vào `/webhooks/meta` và chờ worker xử lý. Chỉ chạy khi `MOCK_MODE=true`. File `.env` tạo trước Bước 2 cần thêm `META_APP_SECRET` (chuỗi ngẫu nhiên cho máy dev) rồi `make up` lại.

Mở http://localhost:5173 và đăng nhập bằng một tài khoản trong `backend/.dev-credentials`. File này nằm trong `.gitignore` và có quyền 600.

| Dịch vụ | Địa chỉ | Ghi chú |
|---|---|---|
| Giao diện | http://localhost:5173 | Vite dev, proxy `/api` sang backend |
| API | http://localhost:8000 | Tài liệu API: `/api/docs` (tắt ở production) |
| PostgreSQL | 127.0.0.1:5433 | Chỉ mở trên máy mình |
| Redis | 127.0.0.1:6380 | Chỉ mở trên máy mình |

## Kiểm thử

```bash
make test              # pytest backend (unit + tích hợp trên DB fanpage_test riêng)
make lint              # ruff + mypy --strict
cd frontend && npm test          # vitest
cd frontend && npx playwright install chromium && npm run e2e   # cần stack đang chạy
```

Test backend tự tạo lại DB `fanpage_test` mỗi lần chạy và từ chối xóa bất kỳ DB nào không có đuôi `_test`.

## Webhook Meta

- `GET /webhooks/meta`: Meta xác minh bằng `META_WEBHOOK_VERIFY_TOKEN`.
- `POST /webhooks/meta`: kiểm tra `X-Hub-Signature-256` bằng `META_APP_SECRET` (sai thì 403), đẩy vào hàng đợi arq, trả 200. Worker (`app/workers/webhook.py`) xử lý, chặn lặp theo `mid` / `leadgen_id`, lỗi thì thử lại có backoff.
- Worker dùng tài khoản DB ứng dụng. Để biết Trang thuộc workspace nào, nó gọi hàm `app_route_page(fb_page_id)`, hàm này chỉ trả về `workspace_id`.
- Thời gian trả lời chỉ tính trong giờ làm việc của workspace (`app/services/response_time.py`). Echo có `app_id` nằm trong `META_AUTOMATED_APP_IDS` là tin tự động, không tính. Worker log mỗi echo kèm `app_id` để điền danh sách này khi ứng dụng đã Live.

## Khách hàng (Bước 3)

- Màn hình `/leads` (dạng cột, dạng bảng, ô lọc nhanh, bộ lọc) và `/leads/:id` (diễn biến, cập nhật kết quả).
- API `GET /api/leads`, `/api/leads/summary`, `/api/leads/filter-options`, `/api/leads/{id}`; ghi qua `POST /api/leads/{id}/called` và `PUT /api/leads/{id}/result`. Phạm vi theo vai trò áp trong câu truy vấn (`app/services/lead_service.py`).
- SĐT được nhận tự động trong tin của khách, kể cả khi viết có dấu cách hoặc dấu chấm. Người không có quyền xem SĐT chỉ thấy số đã che, kể cả trong nội dung tin nhắn. Khách gửi form được gộp với khách nhắn tin nếu cùng Trang, cùng SĐT, trong cùng đợt.
- Quy tắc cập nhật kết quả: xem `docs/architecture/decisions.md`, mục E.

## Điểm và xếp hạng (Bước 4)

- Job `nightly_scores` chạy lúc 01:00 giờ Việt Nam: tính tuần hiện tại (T2–CN), 7 ngày, 30 ngày, tháng này; đêm thứ Hai chốt tuần trước (`is_final`, không bao giờ tính lại).
- Hàm tính điểm thuần nằm ở `app/services/scoring.py`. Job, nút "Tính lại ngay" và "xem thử" đều gọi `score_service.compute_period`, nên cho cùng một kết quả.
- Màn hình `/staff` (bảng xếp hạng), `/staff/:id` (hồ sơ), `/settings#score` (công thức). Chỉ Chủ sở hữu sửa được công thức; lưu là thêm phiên bản mới và áp dụng ngay cho kỳ chưa chốt.
- "Chăm Trang" chưa có số liệu tới Bước 7, nên trọng số của tiêu chí này được chia lại cho các tiêu chí khác (xem `docs/architecture/decisions.md`, mục F).

## Ứng dụng điện thoại (Bước 5)

- Đường dẫn `/m` (PWA): Khách của tôi (3 tab, nút Gọi / Chốt / Hẹn / Hủy), Điểm của tôi, Nhắc việc, Tài khoản. Chỉ hiện khách của chính người đăng nhập.
- Job `send_reminders` chạy mỗi 5 phút, tạo nhắc việc theo các mốc trong `docs/architecture/decisions.md` (mục G) và gửi thông báo đẩy (Web Push).
- Thông báo đẩy cần `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`. `make env` tự sinh khóa; với `.env` đã có thì chạy `make vapid`. Thiếu khóa thì nhắc việc vẫn hiện trong app, chỉ không có thông báo đẩy.
- Service worker (`frontend/public/sw.js`) chỉ lưu khung giao diện, không lưu dữ liệu `/api`.
- Biểu tượng tạm sinh bằng `python3 scripts/make_icons.py`; thay khi sản phẩm có logo.

### Kiểm tra cài lên điện thoại thật

Việc cài cần HTTPS, nên làm trên bản production (`APP_DOMAIN`), không làm được qua `localhost`.

1. **Android (Chrome):** mở `https://<tên miền>/m` → đăng nhập → menu ⋮ → "Cài đặt ứng dụng" (hoặc "Thêm vào màn hình chính"). Mở app từ màn hình chính → Tài khoản → Bật thông báo.
2. **iPhone (Safari, iOS 16.4 trở lên):** mở `https://<tên miền>/m` → nút Chia sẻ → "Thêm vào MH chính". **Mở app từ màn hình chính** rồi vào Tài khoản → Bật thông báo (Safari thường không bật được thông báo đẩy).
3. Thử nhận thông báo: Quản lý mở một khách của nhân viên trên máy tính → "Nhắc người phụ trách". Điện thoại nhân viên phải hiện thông báo; bấm vào thì mở đúng khách.

## Kết nối BM và nhập Excel (Bước 6)

- Màn hình `/bm`: Chủ sở hữu thêm BM bằng mã của người dùng hệ thống "Dashboard" (4 bước theo thiết kế), đổi mã, kiểm tra lại, ngắt kết nối. Quản lý xem và gán người phụ trách Trang.
- Mã BM và mã Trang lưu dạng Fernet, giao diện chỉ hiện 4 ký tự cuối. Gửi mã cho Meta qua header `Authorization`, kèm `appsecret_proof`.
- Job `check_bms` chạy mỗi 6 giờ: kiểm tra mã và quyền, nhận Trang mới, lấy bù form leadgen, nhắc Chủ sở hữu khi BM thiếu quyền hoặc mất kết nối.
- Màn hình Nhân viên: "Nhập từ Excel" (file mẫu có sẵn danh sách Trang) và "+ Thêm nhân viên". File mật khẩu tạm của tài khoản mới chỉ tải được một lần.
- MOCK_MODE dùng client Graph giả (`backend/tests/fixtures/meta/graph_mock.json`). Mã giả để thử: `MOCK-BM-2` (BM thứ hai, 3 Trang), `MOCK-BM-NOLEADS` (thiếu quyền form), `MOCK-INVALID` (mã sai).

### Nối với Meta thật (khi ứng dụng đã Live)

1. Trong `.env`: `MOCK_MODE=false`, `META_APP_ID`, `META_APP_SECRET`, `META_GRAPH_VERSION` (ví dụ `v23.0`), `META_WEBHOOK_VERIFY_TOKEN`.
2. Trang quản lý ứng dụng Meta → Webhooks → đối tượng **Page**: URL gọi lại `https://<tên miền>/webhooks/meta`, mã xác minh = `META_WEBHOOK_VERIFY_TOKEN`; đăng ký các trường `messages`, `message_echoes`, `messaging_referrals`, `leadgen`, `feed`.
3. Trong từng BM: tạo người dùng hệ thống "Dashboard" (vai trò Nhân viên), gán Trang và tài khoản quảng cáo với đúng các quyền ở bước 2 của màn hình Kết nối BM, tạo mã (thời hạn Không bao giờ) rồi Chủ sở hữu dán vào màn hình Kết nối BM. Hệ thống tự đăng ký webhook cho từng Trang.

## Lệnh quản trị

Các lệnh này chạy trong container `migrate`, là container duy nhất có mật khẩu quản trị DB.

```bash
make migrate     # alembic upgrade head
make bootstrap   # tạo workspace + chủ sở hữu đầu tiên từ BOOTSTRAP_* trong .env
```

Tạo migration mới:

```bash
docker compose run --rm migrate alembic revision --autogenerate -m "mo_ta"
```

Bảng mới có `workspace_id` thì phải bật RLS và GRANT cho tài khoản ứng dụng (xem `backend/migrations/helpers.py`). Nếu thiếu, `test_schema_invariants.py` sẽ fail.

## Bảo mật

- Hai tài khoản DB: **quản trị** (chỉ migration và CLI) và **ứng dụng** (API, worker; bị Row-Level Security giới hạn theo workspace, không sửa hay xóa được `audit_logs`).
- Phiên đăng nhập lưu phía server. DB chỉ giữ HMAC của token; cookie `HttpOnly`, `SameSite=Lax`, tiền tố `__Host-` khi chạy https. Mọi request ghi phải kèm CSRF token.
- Log tự che số điện thoại, mã truy cập Meta, cookie và header Authorization.
- Không đặt mã truy cập của BM trong `.env`. Chủ sở hữu dán mã qua màn hình "Kết nối BM" (Bước 6); mã được mã hóa Fernet trước khi lưu.
- Nên cài pre-commit để chặn commit lộ bí mật: `pipx install pre-commit && pre-commit install`.

## Production (VPS)

```bash
cp .env.example .env    # điền giá trị thật; APP_ENV=production, APP_BASE_URL=https://<tên miền>, APP_DOMAIN=<tên miền>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm migrate python -m app.cli bootstrap-owner
```

Caddy tự lấy chứng chỉ HTTPS cho `APP_DOMAIN`. Ở production, ứng dụng từ chối khởi động nếu thiếu bí mật, bí mật yếu, hoặc `APP_BASE_URL` không dùng https.

## Cấu trúc

```
backend/   FastAPI, SQLAlchemy 2, Alembic, arq
  app/api        router theo mô-đun (deps.py: xác thực, CSRF, require(Perm))
  app/core       config, db (RLS), security, crypto, rbac, logging
  app/models     SQLAlchemy
  app/services   nghiệp vụ
  app/workers    job arq
  app/mock       dữ liệu demo
  migrations/    Alembic
  tests/         unit/ và integration/
frontend/  React + Vite + TypeScript
  src/i18n       toàn bộ chữ giao diện
  src/app        router, menu theo quyền
  src/pages      màn hình máy tính
  src/mobile     PWA nhân viên (/m)
  e2e/           Playwright
deploy/    Caddyfile, script khởi tạo Postgres
docs/      thiết kế 14 màn hình, tài liệu kiến trúc
```
