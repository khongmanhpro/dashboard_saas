COMPOSE := docker compose
# Container quản trị (có mật khẩu quản trị DB): test, CLI, migration.
ADMIN := $(COMPOSE) run --rm -T migrate
# Giả lập và e2e chạy trên DB / Redis riêng, không ghi vào DB dev (decisions.md mục L).
SIMULATE := $(COMPOSE) run --rm -T -e POSTGRES_DB=fanpage_simulate_test -e POSTGRES_APP_USER=fanpage_app_sim -e REDIS_URL=redis://redis:6379/14 migrate

.PHONY: env env-prod vapid up down logs ps test test-frontend e2e e2e-down lint migrate bootstrap seed simulate check-caddy check-backup

env:            ## Tạo .env dev với bí mật ngẫu nhiên (không ghi đè)
	python3 scripts/init_env.py

env-prod:       ## Tạo .env production cho VPS: make env-prod DOMAIN=app.vidu.vn (mục S)
	python3 scripts/init_env.py --prod --domain "$(DOMAIN)"

vapid:          ## Thêm khóa VAPID (thông báo đẩy) vào .env đã có, không đổi giá trị khác
	python3 scripts/init_env.py --add-vapid

up:             ## Chạy toàn bộ dịch vụ dev
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail 100

ps:
	$(COMPOSE) ps

test:           ## Chạy test backend trong container
	$(ADMIN) pytest -q -p no:cacheprovider

test-frontend:  ## Test đơn vị giao diện (vitest) và kiểm tra kiểu
	cd frontend && npm run typecheck && npm test

e2e:            ## Playwright trên stack e2e riêng (DB fanpage_e2e_test, :5174), chạy xong tự dọn
	$(COMPOSE) --profile e2e up -d --build --wait backend-e2e worker-e2e frontend-e2e
	cd frontend && E2E_BASE_URL=http://localhost:5174 npm run e2e; status=$$?; \
		cd .. && $(MAKE) --no-print-directory e2e-down; exit $$status

e2e-down:       ## Gỡ stack e2e, xóa DB fanpage_e2e_test và Redis db 13
	$(COMPOSE) --profile e2e rm -sf backend-e2e worker-e2e frontend-e2e e2e-migrate
	$(COMPOSE) --profile e2e run --rm -T e2e-migrate python -m app.mock.sandbox drop

lint:
	$(ADMIN) sh -c "ruff check app tests migrations && ruff format --check app tests migrations && mypy app"

migrate:        ## Chạy migration (tài khoản quản trị)
	$(ADMIN) alembic upgrade head

bootstrap:      ## Tạo workspace + chủ sở hữu đầu tiên từ BOOTSTRAP_* trong .env
	$(ADMIN) python -m app.cli bootstrap-owner

seed:           ## Dữ liệu demo cho máy dev (mật khẩu ghi vào backend/.dev-credentials)
	$(ADMIN) python -m app.mock.seed

simulate:       ## Giả lập webhook cho 4 Trang demo và kiểm tra số phút trả lời (cần make up, make seed)
	$(SIMULATE) python -m app.mock.simulate

check-caddy:    ## Kiểm tra deploy/Caddyfile bằng Caddy thật: hai chế độ, IP thật qua tunnel (mục Q)
	sh scripts/check_caddy.sh

check-backup:   ## Chạy thật sao lưu → khôi phục (mục R), so dữ liệu. Cần make up và make simulate
	sh scripts/check_backup.sh
