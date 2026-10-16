# Hệ thống đo lường nhân viên phụ trách Fanpage

Bối cảnh sản phẩm và quy tắc nghiệp vụ: [CLAUDE.md](CLAUDE.md). Các quyết định đã chốt: [docs/architecture/decisions.md](docs/architecture/decisions.md). Mô hình dữ liệu cho cả 7 bước: [docs/architecture/data-model.md](docs/architecture/data-model.md). Phân quyền: [docs/architecture/rbac.md](docs/architecture/rbac.md).

**Trạng thái:** xong Bước 1 (khung dự án). Chưa có webhook và các màn hình nghiệp vụ.

## Chạy trên máy dev

Cần Docker Desktop, Python 3 (chỉ để chạy script tạo `.env`) và Node 22 nếu muốn chạy test giao diện.

```bash
make env     # tạo .env với bí mật ngẫu nhiên (không ghi đè nếu đã có)
make up      # db, redis, migrate, backend, worker, frontend
make seed    # dữ liệu demo: 5 vai trò, mật khẩu ghi vào backend/.dev-credentials
```

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
