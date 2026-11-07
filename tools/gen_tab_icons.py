"""生成小程序 tabBar 图标（4 组 × 常态/选中态，81×81 PNG）。

用法：E:/python.exe tools/gen_tab_icons.py
依赖：Pillow。输出：miniprogram/images/tab/。
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "miniprogram" / "images" / "tab"
SIZE = 81
SCALE = 4
S = SIZE * SCALE

COLORS = {
    "": "#65766B",      # 常态
    "-on": "#166A49",   # 选中
}


def canvas():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def box(draw, coords, radius, color, width=4):
    x1, y1, x2, y2 = (int(v * SCALE) for v in coords)
    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=radius * SCALE,
        outline=color,
        width=width * SCALE,
    )


def line(draw, points, color, width=4):
    pts = [(int(x * SCALE), int(y * SCALE)) for x, y in points]
    draw.line(pts, fill=color, width=width * SCALE, joint="curve")


def circle(draw, center, r, color, width=4):
    cx, cy = (int(v * SCALE) for v in center)
    rr = r * SCALE
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=color, width=width * SCALE)


def dot(draw, center, r, color):
    cx, cy = (int(v * SCALE) for v in center)
    rr = r * SCALE
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=color)


def icon_todo(draw, color):
    box(draw, (13, 10, 68, 71), 12, color)
    for i, y in enumerate((27, 42, 57)):
        line(draw, [(21, y), (24.5, y + 3.5), (29.5, y - 3.5)], color, 3)
        line(draw, [(36, y), (57, y)], color, 3)


def icon_plots(draw, color):
    circle(draw, (30, 29), 12, color)
    circle(draw, (51, 29), 12, color)
    circle(draw, (40.5, 19), 12, color)
    line(draw, [(40.5, 38), (40.5, 61)], color, 4)
    line(draw, [(40.5, 50), (31, 43)], color, 3)
    line(draw, [(24, 68), (57, 68)], color, 4)


def icon_scan(draw, color):
    box(draw, (11, 24, 70, 67), 10, color)
    box(draw, (29, 14, 52, 26), 5, color)
    circle(draw, (40.5, 45), 11, color)
    dot(draw, (60, 32), 2.5, color)


def icon_form(draw, color):
    box(draw, (16, 11, 65, 70), 9, color)
    box(draw, (30, 6, 51, 17), 4, color)
    line(draw, [(26, 32), (55, 32)], color, 3)
    line(draw, [(26, 44), (50, 44)], color, 3)
    line(draw, [(26, 56), (43, 56)], color, 3)


ICONS = {
    "todo": icon_todo,
    "plots": icon_plots,
    "scan": icon_scan,
    "form": icon_form,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, painter in ICONS.items():
        for suffix, color in COLORS.items():
            img = canvas()
            painter(ImageDraw.Draw(img), color)
            img = img.resize((SIZE, SIZE), Image.LANCZOS)
            path = OUT / f"{name}{suffix}.png"
            img.save(path, optimize=True)
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
