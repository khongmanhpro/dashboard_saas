COMPOSE := docker compose
# Container quản trị (có mật khẩu quản trị DB): test, CLI, migration.
ADMIN := $(COMPOSE) run --rm -T migrate

.PHONY: env up down logs ps test lint migrate bootstrap seed

env:            ## Tạo .env dev với bí mật ngẫu nhiên (không ghi đè)
	python3 scripts/init_env.py

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

lint:
	$(ADMIN) sh -c "ruff check app tests migrations && ruff format --check app tests migrations"

migrate:        ## Chạy migration (tài khoản quản trị)
	$(ADMIN) alembic upgrade head

bootstrap:      ## Tạo workspace + chủ sở hữu đầu tiên từ BOOTSTRAP_* trong .env
	$(ADMIN) python -m app.cli bootstrap-owner

seed:           ## Dữ liệu demo cho máy dev (mật khẩu ghi vào backend/.dev-credentials)
	$(ADMIN) python -m app.mock.seed
