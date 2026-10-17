"""Sinh biểu tượng PWA tạm (chữ "P" trắng trên nền màu chính #1F63B8), chỉ dùng thư viện chuẩn.

    python3 scripts/make_icons.py

Thay bằng logo thật khi sản phẩm có tên và logo (quyết định Bước 5). Biểu tượng tràn viền để dùng
được cả cho "maskable" của Android; chữ nằm trong vùng an toàn 60% ở giữa.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"
BLUE = (0x1F, 0x63, 0xB8)
WHITE = (0xFF, 0xFF, 0xFF)
SAMPLES = 4  # khử răng cưa: 4×4 điểm mẫu mỗi pixel


def inside_p(x: float, y: float) -> bool:
    """Chữ P trong hệ tọa độ [0, 1]."""
    stem = 0.36 <= x <= 0.46 and 0.28 <= y <= 0.72
    top_bar = 0.36 <= x <= 0.52 and 0.28 <= y <= 0.35
    mid_bar = 0.36 <= x <= 0.52 and 0.49 <= y <= 0.56
    dx, dy = x - 0.52, y - 0.42
    ring = x >= 0.52 and 0.07**2 <= dx * dx + dy * dy <= 0.14**2
    return stem or top_bar or mid_bar or ring


def render(size: int) -> bytes:
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # bộ lọc PNG: None
        for px in range(size):
            hits = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) / size
                    y = (py + (sy + 0.5) / SAMPLES) / size
                    hits += inside_p(x, y)
            a = hits / (SAMPLES * SAMPLES)
            rows += bytes(round(BLUE[i] * (1 - a) + WHITE[i] * a) for i in range(3))
    return bytes(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # RGB 8 bit
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        (OUT / name).write_bytes(png(size))
        print(f"đã tạo frontend/public/icons/{name}")


if __name__ == "__main__":
    main()
