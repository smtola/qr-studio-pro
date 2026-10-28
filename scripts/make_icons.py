"""Generate assets/icons/app.png, app.ico and app.icns from code (no external artwork).

    python scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets" / "icons"
GRID = [  # a fixed 9x9 pattern with three finder eyes, drawn as a QR-like glyph
    "XXXXXXX..", "X.....X.X", "X.XXX.X..", "X.XXX.X.X", "X.XXX.X..",
    "X.....X.X", "XXXXXXX..", ".X.X.X.X.", "X..X.XX.X",
]


def draw(size: int = 1024) -> Image.Image:
    ss = 2
    s = size * ss
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # gradient rounded-square tile
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=(int(79 + (30 - 79) * t), int(70 + (41 - 70) * t), int(229 + (140 - 229) * t), 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((int(s * .06), int(s * .06), int(s * .94), int(s * .94)), int(s * .2), fill=255)
    im.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # white card with the glyph
    m = int(s * .2)
    d.rounded_rectangle((m, m, s - m, s - m), int(s * .08), fill=(255, 255, 255, 255))
    pad = int(s * .08)
    cell = (s - 2 * m - 2 * pad) / 9
    for r, row in enumerate(GRID):
        for c, ch in enumerate(row):
            if ch == "X":
                x0, y0 = m + pad + c * cell, m + pad + r * cell
                d.rounded_rectangle((x0, y0, x0 + cell * .94, y0 + cell * .94), cell * .18, fill=(17, 24, 39, 255))
    # logo badge in the centre, like the product feature
    cx = cy = s // 2
    rr = int(s * .075)
    d.ellipse((cx - rr - 14 * ss, cy - rr - 14 * ss, cx + rr + 14 * ss, cy + rr + 14 * ss), fill=(255, 255, 255, 255))
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(79, 70, 229, 255))
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw(1024)
    big.resize((512, 512), Image.LANCZOS).save(OUT / "app.png")
    big.save(OUT / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(OUT / "app.icns")
    print("wrote", [p.name for p in sorted(OUT.iterdir())])


if __name__ == "__main__":
    main()
