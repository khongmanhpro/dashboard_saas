# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./

# --- Dev: có thư viện test, mã nguồn được bind-mount từ máy ---
FROM base AS dev
RUN uv sync --frozen
COPY . .
CMD ["sh", "scripts/start.sh"]

# --- Production: không có thư viện dev, chạy bằng user không phải root ---
FROM base AS prod
RUN uv sync --frozen --no-dev
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser
CMD ["sh", "scripts/start.sh"]
