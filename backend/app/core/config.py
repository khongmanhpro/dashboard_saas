"""Cấu hình đọc từ biến môi trường (.env).

Thiếu hoặc yếu bí mật thì ứng dụng từ chối khởi động thay vì chạy với giá trị mặc định.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "staging", "production"]

# app_id giả của tin tự động trong dữ liệu mẫu (tests/fixtures/meta/simulate_scenarios.json).
# Chỉ có hiệu lực khi MOCK_MODE=true.
MOCK_AUTOMATED_APP_ID = "1000000000000001"

_WEAK_SECRETS = {"changeme", "secret", "password", "dev", "test", "123456"}
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # --- Ứng dụng ---
    app_env: AppEnv = "development"
    app_base_url: str = "http://localhost:5173"
    app_secret_key: SecretStr
    app_timezone: str = "Asia/Ho_Chi_Minh"
    log_level: str = "INFO"
    # Mục O: mặc định là dữ liệu thật; dev bật qua .env (`make env`).
    mock_mode: bool = False

    # --- Cơ sở dữ liệu & hàng đợi ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "fanpage"
    postgres_user: str = "fanpage"
    postgres_password: SecretStr = SecretStr("")
    postgres_app_user: str = "fanpage_app"
    postgres_app_password: SecretStr = SecretStr("")
    redis_url: str = "redis://redis:6379/0"

    # --- Meta (dùng từ Bước 2) ---
    meta_app_id: str = ""
    meta_app_secret: SecretStr = SecretStr("")
    meta_graph_version: str = ""
    meta_webhook_verify_token: SecretStr = SecretStr("")
    # app_id của tin trả lời tự động (chào mừng, trả lời nhanh), cách nhau dấu phẩy. Echo có
    # app_id trong danh sách này không tính là Trang đã trả lời.
    meta_automated_app_ids: str = ""

    # Một hoặc nhiều khóa Fernet, cách nhau dấu phẩy. Khóa đầu dùng để mã hóa.
    token_encryption_key: SecretStr

    # --- Thông báo đẩy (Web Push, Bước 5). Trống thì chỉ có nhắc việc trong app. ---
    vapid_public_key: str = ""
    vapid_private_key: SecretStr = SecretStr("")

    # --- Quy tắc đo lường mặc định cho workspace mới ---
    work_hours_start: dt.time = dt.time(8, 0)
    work_hours_end: dt.time = dt.time(22, 0)
    slow_reply_minutes: int = Field(default=30, ge=1)
    result_deadline_hours: int = Field(default=48, ge=1)
    lead_session_gap_days: int = Field(default=30, ge=1)
    posts_per_week_target: int = Field(default=5, ge=0)
    min_leads_for_ranking: int = Field(default=10, ge=0)

    # --- Phiên đăng nhập ---
    session_ttl_days: int = Field(default=30, ge=1)
    session_idle_days: int = Field(default=7, ge=1)
    login_max_failures: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=900, ge=60)

    # --- Tài khoản quản trị đầu tiên ---
    bootstrap_workspace_name: str = ""
    bootstrap_owner_email: str = ""
    bootstrap_owner_password: SecretStr = SecretStr("")

    # --- Cảnh báo (Bước 7) ---
    # Một bot cho cả hệ thống; chat ID nhận cảnh báo do Chủ sở hữu từng workspace nhập.
    telegram_bot_token: SecretStr = SecretStr("")

    @field_validator("app_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Múi giờ không hợp lệ: {value}") from exc
        return value

    @field_validator("token_encryption_key")
    @classmethod
    def _valid_fernet_keys(cls, value: SecretStr) -> SecretStr:
        keys = [k.strip() for k in value.get_secret_value().split(",") if k.strip()]
        if not keys:
            raise ValueError("TOKEN_ENCRYPTION_KEY đang trống")
        for key in keys:
            try:
                Fernet(key.encode())
            except (ValueError, TypeError) as exc:
                # Không đưa giá trị khóa vào thông báo lỗi.
                raise ValueError("TOKEN_ENCRYPTION_KEY không phải khóa Fernet hợp lệ") from exc
        return value

    @field_validator("app_secret_key")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < MIN_SECRET_KEY_LENGTH or raw.lower() in _WEAK_SECRETS:
            raise ValueError(f"APP_SECRET_KEY phải dài tối thiểu {MIN_SECRET_KEY_LENGTH} ký tự")
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.app_env not in ("staging", "production"):
            return self
        problems: list[str] = []
        if not self.app_base_url.startswith("https://"):
            problems.append("APP_BASE_URL phải dùng https")
        if not self.postgres_app_password.get_secret_value():
            problems.append("POSTGRES_APP_PASSWORD đang trống")
        if self.postgres_app_user == self.postgres_user:
            problems.append("POSTGRES_APP_USER phải khác POSTGRES_USER để RLS có hiệu lực")
        if self.app_env == "production" and self.mock_mode:
            problems.append("MOCK_MODE phải tắt ở production (đặt MOCK_MODE=false)")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    # --- Giá trị suy ra ---
    @property
    def is_production_like(self) -> bool:
        return self.app_env in ("staging", "production")

    @property
    def cookie_secure(self) -> bool:
        return self.app_base_url.startswith("https://")

    @property
    def automated_app_ids(self) -> frozenset[str]:
        ids = {x.strip() for x in self.meta_automated_app_ids.split(",") if x.strip()}
        if self.mock_mode:
            ids.add(MOCK_AUTOMATED_APP_ID)
        return frozenset(ids)

    @property
    def fernet_keys(self) -> list[str]:
        raw = self.token_encryption_key.get_secret_value()
        return [k.strip() for k in raw.split(",") if k.strip()]

    def _dsn(self, user: str, password: SecretStr) -> str:
        pw = quote(password.get_secret_value(), safe="")
        return (
            f"postgresql+asyncpg://{quote(user, safe='')}:{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url(self) -> str:
        """Kết nối của ứng dụng (bị RLS giới hạn)."""
        return self._dsn(self.postgres_app_user, self.postgres_app_password)

    @property
    def database_admin_url(self) -> str:
        """Kết nối quản trị: chỉ cho migration và lệnh CLI."""
        return self._dsn(self.postgres_user, self.postgres_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
