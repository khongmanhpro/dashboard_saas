"""Tạo file .env cho máy dev từ .env.example, điền bí mật ngẫu nhiên.

    python3 scripts/init_env.py

- Không ghi đè .env đã có.
- Không in bí mật ra màn hình.
- Chỉ dùng thư viện chuẩn để chạy được trước khi cài gì.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


DEV_VALUES = {
    "APP_ENV": "development",
    "APP_BASE_URL": "http://localhost:5173",
    "APP_SECRET_KEY": secrets.token_urlsafe(48),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    "POSTGRES_APP_PASSWORD": secrets.token_urlsafe(24),
    "META_WEBHOOK_VERIFY_TOKEN": secrets.token_urlsafe(24),
    # Bí mật giả cho MOCK_MODE (lệnh giả lập ký webhook bằng giá trị này). Khi nối ứng dụng Meta
    # thật thì thay bằng App Secret trong phần Cài đặt cơ bản của ứng dụng.
    "META_APP_SECRET": secrets.token_hex(16),
    "TOKEN_ENCRYPTION_KEY": fernet_key(),
    "MOCK_MODE": "true",
}


def main() -> int:
    if TARGET.exists():
        print(".env đã tồn tại, không ghi đè.", file=sys.stderr)
        return 1
    lines_out: list[str] = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key, sep, rest = line.partition("=")
        key = key.strip()
        if sep and not line.lstrip().startswith("#") and key in DEV_VALUES:
            comment = ""
            if "#" in rest:
                comment = "  #" + rest.split("#", 1)[1]
            lines_out.append(f"{key}={DEV_VALUES[key]}{comment}")
        else:
            lines_out.append(line)
    TARGET.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print("Đã tạo .env (quyền 600). Bí mật được sinh ngẫu nhiên, không in ra đây.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
