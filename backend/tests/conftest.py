"""Cấu hình chung cho test.

Biến môi trường được đặt TRƯỚC khi import `app`, để test luôn chạy trên DB và Redis
riêng (`fanpage_test`, Redis db 15) với bí mật sinh ngẫu nhiên, không đụng dữ liệu dev.
"""

from __future__ import annotations

import os
import re
import secrets

from cryptography.fernet import Fernet

os.environ["APP_ENV"] = "test"
os.environ["APP_BASE_URL"] = "http://testserver"
os.environ["APP_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["MOCK_MODE"] = "true"
os.environ["META_APP_SECRET"] = secrets.token_hex(16)
os.environ["META_WEBHOOK_VERIFY_TOKEN"] = secrets.token_urlsafe(24)
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "fanpage_test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ["POSTGRES_APP_USER"] = os.environ.get("TEST_POSTGRES_APP_USER", "fanpage_app_test")
# Mật khẩu role ứng dụng của test sinh mới mỗi lần chạy (fixture đặt lại cho role).
os.environ["POSTGRES_APP_PASSWORD"] = secrets.token_urlsafe(24)
_redis = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
os.environ["REDIS_URL"] = re.sub(r"/\d+$", "", _redis) + "/15"
