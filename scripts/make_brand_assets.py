"""Sinh biểu tượng GoCyberTech cho giao diện và PWA từ logo gốc `docs/brand/gocybertech-logo.png`.

    python3 scripts/make_brand_assets.py      # cần Pillow (pip install pillow)

- `frontend/public/brand/logo-mark.png`: phần biểu tượng, nền trong suốt (menu, trang đăng nhập).
- `frontend/public/icons/*`: favicon, biểu tượng app (nền trắng). Bản "maskable" giữ biểu tượng
  trong vùng an toàn 60% ở giữa để Android cắt tròn hay bo góc vẫn không mất hình.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "brand" / "gocybertech-logo.png"
PUBLIC = ROOT / "frontend" / "public"
# Khung bao phần biểu tượng trong ảnh gốc 1024×1024 (phía trên chữ GoCyberTech).
MARK_BOX = (219, 172, 780, 538)
WHITE_LEVEL = 238  # điểm sáng hơn mức này, nối với viền ảnh, coi là nền


def transparent_background(img: Image.Image) -> Image.Image:
    """Xóa nền trắng nối với viền ảnh; phần trắng bên trong khiên giữ nguyên."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    assert px is not None
    seen = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        queue.extend([(x, 0), (x, h - 1)])
    for y in range(h):
        queue.extend([(0, y), (w - 1, y)])
    while queue:
        x, y = queue.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, _ = px[x, y]
        if min(r, g, b) < WHITE_LEVEL:
            continue
        px[x, y] = (r, g, b, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                queue.append((nx, ny))
    return img


def on_square(mark: Image.Image, size: int, fill: float) -> Image.Image:
    """Biểu tượng nằm giữa ô vuông nền trắng, chiếm `fill` cạnh ô."""
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    scale = fill * size / max(mark.size)
    resized = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas.convert("RGB")


def main() -> None:
    mark = transparent_background(Image.open(SOURCE).crop(MARK_BOX))
    (PUBLIC / "brand").mkdir(parents=True, exist_ok=True)
    height = 128
    mark.resize((round(mark.width * height / mark.height), height), Image.LANCZOS).save(
        PUBLIC / "brand" / "logo-mark.png", optimize=True
    )
    icons = PUBLIC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    on_square(mark, 32, 0.92).save(icons / "favicon-32.png", optimize=True)
    on_square(mark, 180, 0.78).save(icons / "apple-touch-icon.png", optimize=True)
    on_square(mark, 192, 0.82).save(icons / "icon-192.png", optimize=True)
    on_square(mark, 512, 0.82).save(icons / "icon-512.png", optimize=True)
    on_square(mark, 512, 0.58).save(icons / "icon-maskable-512.png", optimize=True)
    print("Đã sinh biểu tượng GoCyberTech trong frontend/public/brand và frontend/public/icons")


if __name__ == "__main__":
    main()
