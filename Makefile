COMPOSE := docker compose
BACKEND := $(COMPOSE) exec -T backend

.PHONY: env up down logs ps test lint

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
	$(BACKEND) pytest -q -p no:cacheprovider

lint:
	$(BACKEND) ruff check app tests
	$(BACKEND) ruff format --check app tests
