COMPOSE := docker compose
# Container quản trị (có mật khẩu quản trị DB): test, CLI, migration.
ADMIN := $(COMPOSE) run --rm -T migrate

.PHONY: env vapid up down logs ps test test-frontend e2e lint migrate bootstrap seed simulate

env:            ## Tạo .env dev với bí mật ngẫu nhiên (không ghi đè)
	python3 scripts/init_env.py

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

e2e:            ## Playwright (cần stack đang chạy)
	cd frontend && npm run e2e

lint:
	$(ADMIN) sh -c "ruff check app tests migrations && ruff format --check app tests migrations && mypy app"

migrate:        ## Chạy migration (tài khoản quản trị)
	$(ADMIN) alembic upgrade head

bootstrap:      ## Tạo workspace + chủ sở hữu đầu tiên từ BOOTSTRAP_* trong .env
	$(ADMIN) python -m app.cli bootstrap-owner

seed:           ## Dữ liệu demo cho máy dev (mật khẩu ghi vào backend/.dev-credentials)
	$(ADMIN) python -m app.mock.seed

simulate:       ## Giả lập webhook cho 4 Trang demo và kiểm tra số phút trả lời (cần make up, make seed)
	$(ADMIN) python -m app.mock.simulate
