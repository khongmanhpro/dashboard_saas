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


# ---- Khóa VAPID (Web Push, Bước 5): đường cong P-256, chỉ dùng thư viện chuẩn ----
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)


def _add(a: tuple[int, int] | None, b: tuple[int, int] | None) -> tuple[int, int] | None:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        slope = (3 * a[0] * a[0] - 3) * pow(2 * a[1], _P - 2, _P) % _P
    else:
        slope = (b[1] - a[1]) * pow(b[0] - a[0], _P - 2, _P) % _P
    x = (slope * slope - a[0] - b[0]) % _P
    return x, (slope * (a[0] - x) - a[1]) % _P


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_keys() -> tuple[str, str]:
    """(khóa công khai, khóa bí mật) dạng base64url thô, đúng định dạng pywebpush nhận."""
    d = secrets.randbelow(_N - 1) + 1
    result: tuple[int, int] | None = None
    addend: tuple[int, int] | None = _G
    k = d
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    assert result is not None
    public = b"\x04" + result[0].to_bytes(32, "big") + result[1].to_bytes(32, "big")
    return _b64(public), _b64(d.to_bytes(32, "big"))


_VAPID_PUBLIC, _VAPID_PRIVATE = vapid_keys()

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
    "VAPID_PUBLIC_KEY": _VAPID_PUBLIC,
    "VAPID_PRIVATE_KEY": _VAPID_PRIVATE,
}


def add_vapid() -> int:
    """Thêm khóa VAPID vào .env đã có (chỉ khi còn trống), không đụng giá trị khác."""
    if not TARGET.exists():
        print("Chưa có .env, chạy `make env` trước.", file=sys.stderr)
        return 1
    lines = TARGET.read_text(encoding="utf-8").splitlines()
    present = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in lines if "=" in line and not line.startswith("#")}
    if present.get("VAPID_PUBLIC_KEY") and present.get("VAPID_PRIVATE_KEY"):
        print("Khóa VAPID đã có, giữ nguyên.")
        return 0
    lines = [line for line in lines if not line.startswith(("VAPID_PUBLIC_KEY=", "VAPID_PRIVATE_KEY="))]
    lines += [f"VAPID_PUBLIC_KEY={_VAPID_PUBLIC}", f"VAPID_PRIVATE_KEY={_VAPID_PRIVATE}"]
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print("Đã thêm khóa VAPID vào .env (không in ra đây).")
    return 0


def main() -> int:
    if "--add-vapid" in sys.argv:
        return add_vapid()
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
