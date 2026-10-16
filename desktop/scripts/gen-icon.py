"""生成桌面应用图标（build/icon.png 512 + build/icon.ico 多尺寸）。

品牌口径与 frontend Logo 组件（components/common/Logo.tsx）同源：
暗底 #0d0f10 圆角方 + 霓虹绿 #00ff2c 方格外框 + 白/绿双竖条（音符标）。
运行：backend/.venv/Scripts/python.exe desktop/scripts/gen-icon.py（需 pillow）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "build"
BG = (13, 15, 16, 255)        # --bg（与壳启动页同底）
ACC = (0, 255, 44, 255)       # --color-acc
WHITE = (255, 255, 255, 255)

# Logo.tsx 的 22×22 viewBox 等比放大
SCALE = 512 / 22


def s(v: float) -> int:
    return round(v * SCALE)


def rounded(v: float, r: float) -> int:
    return round(v * SCALE + r * SCALE)


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = size / 512
    # 底：圆角方（暗底）
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=round(96 * k), fill=BG)
    # 外框：绿色方格（stroke≈2/22）
    stroke = max(2, round(26 * k))
    pad = round(30 * k)
    d.rounded_rectangle(
        [pad, pad, size - 1 - pad, size - 1 - pad],
        radius=round(14 * k), outline=ACC, width=stroke,
    )
    # 双竖条：白条（x=6,y=9,w=3,h=7）+ 绿条（x=11,y=5,w=3,h=11）
    bar = max(2, round(3 * SCALE * k))
    x1 = round(6.5 * SCALE * k)
    y1 = round(9.5 * SCALE * k)
    d.rounded_rectangle([x1, y1, x1 + bar, y1 + round(7 * SCALE * k)], radius=bar // 2, fill=WHITE)
    x2 = round(11.5 * SCALE * k)
    y2 = round(5.5 * SCALE * k)
    d.rounded_rectangle([x2, y2, x2 + bar, y2 + round(11 * SCALE * k)], radius=bar // 2, fill=ACC)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = render(512)
    base.save(OUT_DIR / "icon.png")
    base.save(
        OUT_DIR / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icons written: {OUT_DIR / 'icon.png'}, {OUT_DIR / 'icon.ico'}")


if __name__ == "__main__":
    main()
