# Hệ thống đo lường nhân viên phụ trách Fanpage

Bối cảnh sản phẩm và quy tắc nghiệp vụ: [CLAUDE.md](CLAUDE.md). Các quyết định đã chốt: [docs/architecture/decisions.md](docs/architecture/decisions.md). Mô hình dữ liệu cho cả 7 bước: [docs/architecture/data-model.md](docs/architecture/data-model.md). Phân quyền: [docs/architecture/rbac.md](docs/architecture/rbac.md).

**Trạng thái:** xong Bước 1–7 (khung dự án, webhook Meta và thời gian trả lời, Khách hàng, điểm và xếp hạng, ứng dụng điện thoại, nhiều BM và nhập Excel, quảng cáo, Tổng quan, Fanpage, cảnh báo Telegram). Tiếp theo: chạy thử 2 tuần với Meta thật (CLAUDE.md mục 8).

## Chạy trên máy dev

Cần Docker Desktop, Python 3 (chỉ để chạy script tạo `.env`) và Node 22 nếu muốn chạy test giao diện.

```bash
make env     # tạo .env với bí mật ngẫu nhiên (không ghi đè nếu đã có)
make up      # db, redis, migrate, backend, worker, frontend
make seed    # dữ liệu demo: 5 vai trò, 4 Trang demo, 30 ngày khách mẫu, quảng cáo giả; mật khẩu ghi vào backend/.dev-credentials
make simulate  # giả lập webhook cho 4 Trang demo trên DB riêng, in số phút trả lời so với mong đợi
```

`make simulate` đọc kịch bản trong `backend/tests/fixtures/meta/simulate_scenarios.json`, ký payload bằng `META_APP_SECRET`, gửi vào `/webhooks/meta` của app trong tiến trình và chạy worker một lượt. Chạy trên DB riêng `fanpage_simulate_test` (tạo lại mỗi lần, Redis db 14), **không ghi vào DB dev**. Chỉ chạy khi `MOCK_MODE=true`.

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
make test-frontend     # typecheck + vitest
make e2e               # Playwright trên stack e2e riêng (lần đầu: cd frontend && npx playwright install chromium)
make e2e-down          # gỡ stack e2e, xóa DB e2e (make e2e tự gọi khi chạy xong)
```

**Không test nào ghi vào DB dev** (decisions.md mục L). DB dev chỉ do `make seed` và người dùng ghi.

| Lệnh | DB | Redis | Ghi chú |
|---|---|---|---|
| `make test` | `fanpage_test` | db 15 | tạo lại mỗi lần chạy |
| `make simulate` | `fanpage_simulate_test` | db 14 | tạo lại mỗi lần chạy |
| `make e2e` | `fanpage_e2e_test` | db 13 | stack riêng (profile `e2e`): backend :8001, frontend :5174; tạo lại khi bật, xóa khi chạy xong |

Các lệnh trên từ chối tạo lại, migrate hay xóa bất kỳ DB nào không có đuôi `_test` (`app/mock/sandbox.py`). `app.cli e2e-seed` cũng vậy, nên chạy nhầm trên container `migrate` (DB dev) sẽ bị chặn.

### CI (GitHub Actions)

`.github/workflows/ci.yml` chạy mỗi khi mở hoặc cập nhật PR vào `main` và khi `main` có commit mới. Ba việc chạy song song, PR chỉ gộp được khi cả ba xanh (decisions.md mục P):

| Việc | Chạy |
|---|---|
| Backend | `make env` (bí mật ngẫu nhiên, MOCK_MODE) → `make lint`, `make test`, `make simulate` |
| Giao diện | `make test-frontend` |
| E2E | `make e2e`; fail thì tải `e2e-test-results` (trace Playwright) ở trang của lần chạy |

CI không dùng bí mật thật nào.

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
- Logo GoCyberTech gốc ở `docs/brand/gocybertech-logo.png`. Biểu tượng menu, favicon, biểu tượng app sinh bằng `python3 scripts/make_brand_assets.py` (cần Pillow).

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
- MOCK_MODE dùng client Graph giả (`backend/tests/fixtures/meta/graph_mock.json`). Mã giả để thử: `MOCK-BM-2` (BM thứ hai, 3 Trang), `MOCK-BM-NOLEADS` (thiếu quyền form), `MOCK-INVALID` (mã sai). Số liệu quảng cáo, bài đăng, số liệu Trang giả sinh từ mục `content` của file này, cố định theo ngày.

### Nối với Meta thật (khi ứng dụng đã Live)

1. Trong `.env`: `MOCK_MODE=false`, `META_APP_ID`, `META_APP_SECRET`, `META_GRAPH_VERSION` (ví dụ `v23.0`), `META_WEBHOOK_VERIFY_TOKEN`.
2. Trang quản lý ứng dụng Meta → Webhooks → đối tượng **Page**: URL gọi lại `https://<tên miền>/webhooks/meta`, mã xác minh = `META_WEBHOOK_VERIFY_TOKEN`; đăng ký các trường `messages`, `message_echoes`, `messaging_referrals`, `leadgen`, `feed`.
3. Trong từng BM: tạo người dùng hệ thống "Dashboard" (vai trò Nhân viên), gán Trang và tài khoản quảng cáo với đúng các quyền ở bước 2 của màn hình Kết nối BM, tạo mã (thời hạn Không bao giờ) rồi Chủ sở hữu dán vào màn hình Kết nối BM. Hệ thống tự đăng ký webhook cho từng Trang.

## Quảng cáo, Tổng quan, Fanpage, cảnh báo (Bước 7)

- Màn hình `/overview` (Tổng quan; màn hình hẹp tự đổi sang bố cục điện thoại, có menu dưới), `/pages` và `/pages/:id` (Fanpage, Chi tiết Trang), `/ads` (Quảng cáo), mục Cảnh báo và Tỉ giá trong `/settings`.
- API `GET /api/reports/overview`, `/api/reports/pages`, `/api/reports/pages/{id}`, `/api/reports/ads`; xuất Excel `/api/reports/overview.xlsx`, `/api/reports/pages.xlsx`. Cấu hình: `/api/settings/alerts`, `/api/settings/fx-rates`, `/api/alerts/rules`.
- Job `sync_meta` (mỗi giờ, phút 40): cấu trúc và chi tiêu quảng cáo theo ngày ở 3 cấp, bài đăng, số liệu Trang; gắn khách với quảng cáo qua `fb_ad_id`. Lần đầu lấy bù 30 ngày, sau đó lấy lại 3 ngày gần nhất.
- Job `send_alerts` (mỗi giờ, phút 0): cảnh báo Telegram theo quy tắc, tóm tắt hôm qua từ 08:00. Mỗi quy tắc × đối tượng × ngày gửi một lần; gửi lỗi thì lần sau thử lại. BM xấu đi thì job `check_bms` báo ngay.
- Chi phí mỗi khách = chi tiêu chiến dịch trong ngày ÷ khách mới của chiến dịch cùng ngày; chi phí mỗi khách chốt = chi tiêu trong kỳ ÷ khách chốt. Tài khoản QC không dùng VND cần Chủ sở hữu nhập tỉ giá (Cài đặt → Tỉ giá); thiếu tỉ giá thì số đó chưa được cộng và giao diện ghi rõ.
- Chăm Trang tính vào điểm theo số bài trên Trang lúc người đó phụ trách: `min(bài / mục tiêu, 1) × 100`.
- Chi tiết các quyết định: `docs/architecture/decisions.md`, mục I.

### Bật cảnh báo Telegram thật

1. Tạo bot qua @BotFather, đặt mã vào `TELEGRAM_BOT_TOKEN` trong `.env` rồi `docker compose up -d` (mã bot không bao giờ ghi vào log).
2. Thêm bot vào nhóm Telegram của sếp, lấy chat ID của nhóm (dạng `-100…`).
3. Chủ sở hữu vào Cài đặt → Cảnh báo, dán chat ID, bấm "Lưu cảnh báo" rồi "Gửi thử".

Ở `MOCK_MODE=true` hệ thống không gửi Telegram thật, chỉ ghi nhật ký gửi với trạng thái "Giả lập".

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

### Xử lý yêu cầu xóa dữ liệu của khách

Khách gửi yêu cầu qua email theo trang `/data-deletion` (decisions.md mục U). Phải xóa trong 30 ngày rồi email báo lại cho khách. Trên VPS thêm `-f docker-compose.prod.yml` (và `-f docker-compose.tunnel.yml` nếu chạy qua tunnel) sau `docker compose`.

1. **Khách gửi số điện thoại:** xóa theo số, ở mọi Trang (thêm `--page <ID Trang>` để chỉ xóa ở một Trang):

   ```bash
   docker compose run --rm migrate python -m app.cli delete-customer --phone 0912345678
   ```

2. **Khách chỉ gửi tên Facebook và thời gian nhắn:** tìm khách trên màn hình Khách hàng của Trang đó. Lấy ID Trang và PSID của khách bằng truy vấn chỉ đọc theo thời gian tin đầu tiên (sửa ID Trang và khoảng thời gian):

   ```bash
   docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT c.psid, c.display_name, l.first_inbound_at FROM contacts c JOIN pages p ON p.id = c.page_id JOIN leads l ON l.contact_id = c.id WHERE p.fb_page_id = '"'"'<ID Trang>'"'"' AND l.first_inbound_at BETWEEN '"'"'2026-10-01'"'"' AND '"'"'2026-10-03'"'"' ORDER BY 3"'
   docker compose run --rm migrate python -m app.cli delete-customer --page <ID Trang> --psid <PSID>
   ```

Lệnh chỉ in số dòng đã xóa từng loại, ghi `audit_logs` dạng `customer.erase` chỉ với số đếm, không ghi PSID hay số điện thoại. Bản sao lưu cũ tự hết hạn sau 14 ngày (mục R).

## Bảo mật

- Hai tài khoản DB: **quản trị** (chỉ migration và CLI) và **ứng dụng** (API, worker; bị Row-Level Security giới hạn theo workspace, không sửa hay xóa được `audit_logs`).
- Phiên đăng nhập lưu phía server. DB chỉ giữ HMAC của token; cookie `HttpOnly`, `SameSite=Lax`, tiền tố `__Host-` khi chạy https. Mọi request ghi phải kèm CSRF token.
- Log tự che số điện thoại, mã truy cập Meta, cookie và header Authorization.
- Không đặt mã truy cập của BM trong `.env`. Chủ sở hữu dán mã qua màn hình "Kết nối BM" (Bước 6); mã được mã hóa Fernet trước khi lưu.
- Nên cài pre-commit để chặn commit lộ bí mật: `pipx install pre-commit && pre-commit install`.

## Production (VPS)

Hướng dẫn đầy đủ từ lúc thuê VPS: **[docs/deploy.md](docs/deploy.md)**. Tóm tắt:

```bash
make env-prod DOMAIN=<tên miền>   # .env production, bí mật ngẫu nhiên; chủ sở hữu điền các mã còn trống
scripts/deploy.sh                 # sao lưu, git pull, build, migration, chờ backend khỏe (cũng dùng để cập nhật)
docker compose -f docker-compose.prod.yml run --rm migrate python -m app.cli bootstrap-owner
```

Caddy tự lấy chứng chỉ HTTPS cho `APP_DOMAIN`. Ở production, ứng dụng từ chối khởi động nếu thiếu bí mật, bí mật yếu, hoặc `APP_BASE_URL` không dùng https.

### Production qua Cloudflare Tunnel

VPS không mở cổng 80/443: `cloudflared` chủ động nối ra Cloudflare, Cloudflare giữ HTTPS (decisions.md mục Q).

1. Tên miền dùng nameserver của Cloudflare.
2. Cloudflare Zero Trust → Networks → Tunnels → tạo tunnel (loại Cloudflared). Chủ sở hữu tự chép token vào `CLOUDFLARE_TUNNEL_TOKEN` trong `.env` trên VPS.
3. Trong tunnel, thêm Public hostname: `APP_DOMAIN` → `HTTP` → `caddy:80`.
4. Cài đặt của tên miền trên Cloudflare: **tắt** Bot Fight Mode (có thể chặn webhook Meta), Rocket Loader và Email Obfuscation (chèn script, trái CSP). Không tạo Cache Rule cho `/api/*`, `/webhooks/*`.
5. Chạy thêm file chồng:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.tunnel.yml up -d --build
```

Caddy chỉ tin `CF-Connecting-IP` khi request đến từ `cloudflared` (mạng `edge`), rồi ghi đè `X-Forwarded-For` gửi backend, nên giới hạn đăng nhập theo IP và nhật ký thấy IP thật của khách. `make check-caddy` kiểm tra điều này bằng Caddy thật (CI chạy ở việc "Triển khai").

### Sao lưu DB

Service `backup` (có sẵn trong `docker-compose.prod.yml`) sao lưu lúc 02:00 giờ VN mỗi đêm: `pg_dump`, mã hóa bằng `age`, giữ 14 bản trên VPS và đẩy một bản lên Cloudflare R2 (decisions.md mục R). Chưa có bản nào xong trong 26 giờ (kể cả khi thiếu cấu hình R2) thì `docker compose ps` báo `backup` là `unhealthy`.

Chuẩn bị (chủ sở hữu làm một lần):

1. **Khóa mã hóa, tạo trên máy của chủ sở hữu, không tạo trên VPS:** `brew install age`, rồi `age-keygen -o fanpage-backup-key.txt`. Dòng `# public key: age1…` dán vào `BACKUP_AGE_RECIPIENT`. File khóa cất ở chỗ an toàn ngoài VPS (trình quản lý mật khẩu, USB). **Mất file này thì không mở được bản sao lưu nào.**
2. **R2:** Cloudflare → R2 → tạo bucket riêng. Tạo API token loại "Object Read & Write", chỉ áp cho bucket đó. Điền `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` vào `.env` trên VPS.

Thao tác thường dùng (thêm `-f docker-compose.tunnel.yml` nếu chạy qua tunnel):

```bash
docker compose -f docker-compose.prod.yml logs --tail 20 backup                         # kết quả các lần sao lưu
docker compose -f docker-compose.prod.yml exec backup backup.sh                         # sao lưu ngay
docker compose -f docker-compose.prod.yml exec backup sh -c 'rclone ls "r2:$R2_BUCKET"' # các bản trên R2
```

Khôi phục: tắt backend và worker, đưa khóa lên VPS tạm thời, khôi phục, rồi xóa khóa. `--replace` xóa DB đang có rồi tạo lại. Script giải mã xong mới đụng vào DB, nên sai khóa thì DB cũ vẫn còn nguyên.

```bash
docker compose -f docker-compose.prod.yml stop backend worker
docker compose -f docker-compose.prod.yml run --rm --user root -v "$PWD/fanpage-backup-key.txt:/run/age-key:ro" \
  backup restore.sh r2:<tên file .dump.age> fanpage --replace
docker compose -f docker-compose.prod.yml up -d
rm fanpage-backup-key.txt
```

`POSTGRES_USER` và `POSTGRES_APP_USER` trên máy khôi phục phải trùng với máy cũ. `make check-backup` chạy thật cả vòng trên máy dev và trong CI: sao lưu `fanpage_simulate_test`, khôi phục vào `fanpage_restore_test`, so số dòng từng bảng, RLS, quyền và hàm.

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
