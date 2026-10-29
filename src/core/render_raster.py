"""Pillow back-end: scene -> RGBA image. Everything is drawn supersampled, then downscaled."""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageOps

from .color_manager import hex_to_rgb
from .fonts import has_khmer, load_font, resolve_font
from .scene import Gradient, ImageEl, Layer, Scene, Shape, ShapeEl, TextEl

MAX_SS_PIXELS = 36_000_000


def choose_supersample(w: int, h: int) -> int:
    return int(max(1, min(4, math.isqrt(MAX_SS_PIXELS // max(w * h, 1)))))


class _Ctx:
    def __init__(self, k: float):
        self.k = k  # logical -> supersampled pixels

    def e(self, v: float) -> int:  # consistent edge rounding => neighbouring modules abut exactly
        return round(v * self.k)


def _rr_polygon(x0: float, y0: float, x1: float, y1: float, radii: tuple[float, float, float, float]):
    """Polygon outline of a rectangle with per-corner radii (tl, tr, br, bl); x1/y1 are exclusive edges."""
    pts: list[tuple[float, float]] = []
    corners = ((x0, y0, radii[0], math.pi), (x1, y0, radii[1], 1.5 * math.pi),
               (x1, y1, radii[2], 0.0), (x0, y1, radii[3], 0.5 * math.pi))
    for cx, cy, r, a0 in corners:
        if r <= 0.5:
            pts.append((cx, cy))
            continue
        # arc centre is inset by r towards the interior
        icx = cx + (r if cx == x0 else -r)
        icy = cy + (r if cy == y0 else -r)
        n = max(6, int(r * 0.8))
        for i in range(n + 1):
            a = a0 + (math.pi / 2) * i / n
            pts.append((icx + r * math.cos(a), icy + r * math.sin(a)))
    return pts


def _edges(s: Shape, ox: int, oy: int, c: "_Ctx") -> tuple[int, int, int, int]:
    return c.e(s.x) - ox, c.e(s.y) - oy, c.e(s.x + s.w) - ox, c.e(s.y + s.h) - oy  # x1/y1 exclusive


def _draw_shape(d: ImageDraw.ImageDraw, s: Shape, ox: int, oy: int, c: "_Ctx", *, fill=255) -> None:
    x0, y0, x1, y1 = _edges(s, ox, oy, c)
    if x1 <= x0 or y1 <= y0:
        return
    if s.kind == "ellipse":
        d.ellipse([x0, y0, x1 - 1, y1 - 1], fill=fill)
        return
    r = min(s.r * c.k, (x1 - x0) / 2, (y1 - y0) / 2)
    if r < 1.0 or not any(s.corners):
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=fill)
    else:
        radii = tuple(r if on else 0.0 for on in s.corners)
        d.polygon(_rr_polygon(x0, y0, x1, y1, radii), fill=fill)  # type: ignore[arg-type]


def _bbox(shapes: list[Shape], c: _Ctx, pad: int = 2) -> tuple[int, int, int, int]:
    x0 = min(c.e(s.x) for s in shapes) - pad
    y0 = min(c.e(s.y) for s in shapes) - pad
    x1 = max(c.e(s.x + s.w) for s in shapes) + pad
    y1 = max(c.e(s.y + s.h) for s in shapes) + pad
    return x0, y0, x1, y1


def _gradient_image(g: Gradient, size: tuple[int, int], ox: int, oy: int, c: _Ctx) -> Image.Image:
    x1, y1, x2, y2 = (g.x1 * c.k - ox, g.y1 * c.k - oy, g.x2 * c.k - ox, g.y2 * c.k - oy)
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy or 1.0
    span = 254.0
    coeffs = (0, 0, 128, span * dx / l2, span * dy / l2, 0.5 - span * (x1 * dx + y1 * dy) / l2)
    ramp = Image.linear_gradient("L").transform(size, Image.Transform.AFFINE, coeffs, Image.Resampling.BILINEAR)
    return ImageOps.colorize(ramp, hex_to_rgb(g.c0), hex_to_rgb(g.c1)).convert("RGBA")


STRIP_ROWS = 48


def _composite(canvas: Image.Image, layer: Image.Image, ox: int, oy: int) -> None:
    """alpha_composite in thin horizontal strips.

    Pillow's alpha_composite keeps Python's global lock for the whole call (a 3000x4000 layer blocks every other
    thread for ~150 ms). Strips of a few milliseconds let the GUI thread run in between, which keeps the window
    responsive while a preview renders in the background. Output is identical."""
    w, h = layer.size
    if h <= STRIP_ROWS:
        canvas.alpha_composite(layer, (ox, oy))
        return
    for y in range(0, h, STRIP_ROWS):
        canvas.alpha_composite(layer.crop((0, y, w, min(h, y + STRIP_ROWS))), (ox, oy + y))


def _composite_mask(canvas: Image.Image, mask: Image.Image, ox: int, oy: int, fill) -> None:
    """Alpha-composite `fill` (colour hex or RGBA image the size of `mask`) through `mask` at (ox, oy)."""
    cw, ch = canvas.size
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + mask.width, cw), min(oy + mask.height, ch)
    if x1 <= x0 or y1 <= y0:
        return
    box = (x0 - ox, y0 - oy, x1 - ox, y1 - oy)
    clipped = box != (0, 0, mask.width, mask.height)
    if clipped:
        mask = mask.crop(box)
    if isinstance(fill, str):
        layer = Image.new("RGBA", mask.size, hex_to_rgb(fill) + (255,))
    else:
        layer = fill.crop(box) if clipped else fill
    layer.putalpha(mask)
    _composite(canvas, layer, x0, y0)


def _perimeter(s: Shape, step: float) -> list[tuple[float, float]]:
    """Sample the outline of an rrect/ellipse (clockwise from the top-left) every `step` units."""
    pts: list[tuple[float, float]] = []
    if s.kind == "ellipse":
        a, b = s.w / 2, s.h / 2
        n = max(64, int(math.pi * (a + b) / step))
        for i in range(n + 1):
            t = -math.pi / 2 + 2 * math.pi * i / n
            pts.append((s.x + a + a * math.cos(t), s.y + b + b * math.sin(t)))
        return pts
    r = min(s.r, s.w / 2, s.h / 2)
    x0, y0, x1, y1 = s.x, s.y, s.x + s.w, s.y + s.h

    def arc(cx: float, cy: float, a0: float):
        n = max(4, int(math.pi * r / 2 / step)) if r > 0 else 1
        for i in range(n + 1):
            a = a0 + (math.pi / 2) * i / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    def line(ax: float, ay: float, bx: float, by: float):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        for i in range(n + 1):
            pts.append((ax + (bx - ax) * i / n, ay + (by - ay) * i / n))

    line(x0 + r, y0, x1 - r, y0)
    arc(x1 - r, y0 + r, -math.pi / 2)
    line(x1, y0 + r, x1, y1 - r)
    arc(x1 - r, y1 - r, 0)
    line(x1 - r, y1, x0 + r, y1)
    arc(x0 + r, y1 - r, math.pi / 2)
    line(x0, y1 - r, x0, y0 + r)
    arc(x0 + r, y0 + r, math.pi)
    return pts


def _dash_segments(pts: list[tuple[float, float]], dash: float, gap: float):
    seg, on, left = [pts[0]], True, dash
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dist = math.hypot(bx - ax, by - ay)
        pos = 0.0
        while dist - pos > left:
            pos += left
            t = pos / dist if dist else 0
            p = (ax + (bx - ax) * t, ay + (by - ay) * t)
            if on:
                seg.append(p)
                yield seg
            seg = [p]
            on, left = not on, (gap if on else dash)
        left -= dist - pos
        if on:
            seg.append((bx, by))
    if on and len(seg) > 1:
        yield seg


def _stroke_mask(el: ShapeEl, c: _Ctx) -> tuple[Image.Image, int, int]:
    """Stroke centred on the shape outline (like SVG/PDF)."""
    w, s = el.stroke_w, el.shape
    outer = Shape(s.kind, s.x - w / 2, s.y - w / 2, s.w + w, s.h + w, s.r + w / 2 if s.r else 0.0, s.corners)
    x0, y0, x1, y1 = _bbox([outer], c)
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    d = ImageDraw.Draw(mask)
    if not el.dashed:
        _draw_shape(d, outer, x0, y0, c, fill=255)
        _draw_shape(d, s.inset(w / 2) if s.w > w and s.h > w else Shape(s.kind, s.x, s.y, 0, 0), x0, y0, c, fill=0)
    else:
        wpx = max(1, round(w * c.k))
        pts = [((px * c.k) - x0, (py * c.k) - y0) for px, py in _perimeter(s, max(w / 3, 1.0))]
        for seg in _dash_segments(pts, 3 * w * c.k, 2 * w * c.k):
            d.line(seg, fill=255, width=wpx, joint="curve")
    return mask, x0, y0


def text_mask(t: TextEl, k: float) -> tuple[Image.Image, int, int]:
    """Return (mask, x, y): the text drawn at scale k, positioned so the baseline-centre is (t.cx, t.baseline)."""
    path, synth = resolve_font(t.family, t.bold, has_khmer(t.text))
    font = load_font(path, round(t.size * k))
    sw = max(1, round(t.size * k * 0.03)) if (t.bold and synth) else 0
    l, tp, r, b = font.getbbox(t.text, anchor="ms", stroke_width=sw)
    pad = 4
    mask = Image.new("L", (int(r - l) + 2 * pad, int(b - tp) + 2 * pad), 0)
    d = ImageDraw.Draw(mask)
    d.text((-l + pad, -tp + pad), t.text, font=font, fill=255, anchor="ms", stroke_width=sw, stroke_fill=255)
    return mask, round(t.cx * k) + int(l) - pad, round(t.baseline * k) + int(tp) - pad


def render_raster(scene: Scene, width_px: int, ss: int | None = None) -> Image.Image:
    W = max(1, int(width_px))
    scale = W / scene.width
    H = max(1, round(scene.height * scale))
    ss = ss or choose_supersample(W, H)
    c = _Ctx(scale * ss)
    canvas = Image.new("RGBA", (W * ss, H * ss), hex_to_rgb(scene.canvas_fill) + (255,) if scene.canvas_fill else (0, 0, 0, 0))

    images: list[ImageEl] = []
    for el in scene.elements:
        if isinstance(el, ShapeEl):
            if el.fill:
                x0, y0, x1, y1 = _bbox([el.shape], c, 1)
                mask = Image.new("L", (x1 - x0, y1 - y0), 0)
                _draw_shape(ImageDraw.Draw(mask), el.shape, x0, y0, c, fill=255)
                _composite_mask(canvas, mask, x0, y0, el.fill)
            if el.stroke and el.stroke_w > 0:
                mask, x0, y0 = _stroke_mask(el, c)
                _composite_mask(canvas, mask, x0, y0, el.stroke)
        elif isinstance(el, Layer):
            if not el.adds:
                continue
            x0, y0, x1, y1 = _bbox(el.adds, c)
            mask = Image.new("L", (x1 - x0, y1 - y0), 0)
            d = ImageDraw.Draw(mask)
            for s in el.adds:
                _draw_shape(d, s, x0, y0, c, fill=255)
            for s in el.cuts:
                _draw_shape(d, s, x0, y0, c, fill=0)
            fill = _gradient_image(el.fill, mask.size, x0, y0, c) if isinstance(el.fill, Gradient) else el.fill
            _composite_mask(canvas, mask, x0, y0, fill)
        elif isinstance(el, TextEl):
            mask, x0, y0 = text_mask(el, c.k)
            _composite_mask(canvas, mask, x0, y0, el.color)
        elif isinstance(el, ImageEl):
            images.append(el)

    out = canvas if ss == 1 else canvas.resize((W, H), Image.Resampling.LANCZOS)
    for el in images:  # logo is placed at final resolution for maximum crispness
        x0, y0 = round(el.x * scale), round(el.y * scale)
        w, h = max(1, round(el.w * scale)), max(1, round(el.h * scale))
        img = el.image if el.image.size == (w, h) else _resize_logo(el.image, w, h)
        _composite_mask_img(out, img, x0, y0)
    return out


def _resize_logo(img: Image.Image, w: int, h: int) -> Image.Image:
    # premultiplied resize avoids dark fringes around transparent edges
    return img.resize((w, h), Image.Resampling.LANCZOS, reducing_gap=3.0 if img.width > 4 * w else None)


def flatten(img: Image.Image, color: str = "#FFFFFF") -> Image.Image:
    bg = Image.new("RGB", img.size, hex_to_rgb(color))
    bg.paste(img, mask=img.getchannel("A"))
    return bg


def _composite_mask_img(out: Image.Image, img: Image.Image, x0: int, y0: int) -> None:
    """Draw `img` at (x0, y0), clipped to `out` (only the visible part is touched)."""
    cw, ch = out.size
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + img.width, cw), min(y0 + img.height, ch)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (x0, y0, x0 + img.width, y0 + img.height):
        img = img.crop((sx0 - x0, sy0 - y0, sx1 - x0, sy1 - y0))
    _composite(out, img, sx0, sy0)
