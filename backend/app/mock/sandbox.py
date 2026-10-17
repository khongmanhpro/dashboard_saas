"""DB riêng cho test, giả lập và e2e (decisions.md mục L): không bao giờ ghi vào DB dev.

    POSTGRES_DB=fanpage_e2e_test POSTGRES_APP_USER=fanpage_app_e2e \
        python -m app.mock.sandbox prepare

Chỉ nhận DB có tên kết thúc bằng `_test`. Role ứng dụng (POSTGRES_APP_USER) tạo nếu chưa có, không
có quyền superuser hay bỏ qua RLS, như role ứng dụng của dev.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _guard(name: str) -> None:
    # Chặn tuyệt đối việc tạo lại hay migrate nhầm DB dev hoặc production.
    if not name.endswith("_test"):
        raise SystemExit(f"Từ chối: DB không phải DB test: {name}")


async def _admin_connect() -> Any:
    s = get_settings()
    return await asyncpg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password.get_secret_value(),
        database="postgres",
    )


async def ensure_database(name: str, *, recreate: bool = False) -> None:
    """Tạo DB test (xóa trước nếu `recreate`) và role ứng dụng với mật khẩu hiện tại."""
    _guard(name)
    s = get_settings()
    conn = await _admin_connect()
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists and recreate:
            await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            exists = None
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
        role = s.postgres_app_user
        if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
            await conn.execute(
                f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'
            )
        alter = await conn.fetchval(
            "SELECT format('ALTER ROLE %I WITH PASSWORD %L', $1::text, $2::text)",
            role,
            s.postgres_app_password.get_secret_value(),
        )
        await conn.execute(alter)
        await conn.execute(f'GRANT CONNECT ON DATABASE "{name}" TO "{role}"')
    finally:
        await conn.close()


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


async def prepare(*, recreate: bool = False) -> None:
    """DB test của cấu hình hiện tại: tạo (hoặc tạo lại) rồi migrate tới bản mới nhất."""
    s = get_settings()
    await ensure_database(s.postgres_db, recreate=recreate)
    await asyncio.to_thread(command.upgrade, alembic_config(s.database_admin_url), "head")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.mock.sandbox")
    parser.add_argument("action", choices=["prepare"])
    parser.add_argument("--recreate", action="store_true", help="xóa DB test rồi tạo lại")
    args = parser.parse_args()
    asyncio.run(prepare(recreate=args.recreate))
    print(f"DB test sẵn sàng: {get_settings().postgres_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
