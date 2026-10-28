"""SVG back-end: vector modules/frame, text as <text>, logo embedded as a PNG data URI."""
from __future__ import annotations

import base64
import io
from xml.sax.saxutils import escape, quoteattr

from PIL import Image

from .scene import Gradient, ImageEl, Layer, Scene, Shape, ShapeEl, TextEl

K = 0.5522847498


def _n(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def shape_path(s: Shape) -> str:
    x, y, w, h = s.x, s.y, s.w, s.h
    if s.kind == "ellipse":
        rx, ry = w / 2, h / 2
        return (f"M{_n(x)} {_n(y + ry)}a{_n(rx)} {_n(ry)} 0 1 0 {_n(w)} 0"
                f"a{_n(rx)} {_n(ry)} 0 1 0 {_n(-w)} 0z")
    r = min(s.r, w / 2, h / 2)
    tl, tr, br, bl = (r if c else 0.0 for c in s.corners)
    if not any((tl, tr, br, bl)):
        return f"M{_n(x)} {_n(y)}h{_n(w)}v{_n(h)}h{_n(-w)}z"
    d = f"M{_n(x + tl)} {_n(y)}h{_n(w - tl - tr)}"
    d += f"a{_n(tr)} {_n(tr)} 0 0 1 {_n(tr)} {_n(tr)}" if tr else ""
    d += f"v{_n(h - tr - br)}"
    d += f"a{_n(br)} {_n(br)} 0 0 1 {_n(-br)} {_n(br)}" if br else ""
    d += f"h{_n(-(w - br - bl))}"
    d += f"a{_n(bl)} {_n(bl)} 0 0 1 {_n(-bl)} {_n(-bl)}" if bl else ""
    d += f"v{_n(-(h - bl - tl))}"
    d += f"a{_n(tl)} {_n(tl)} 0 0 1 {_n(tl)} {_n(-tl)}" if tl else ""
    return d + "z"


def _png_data_uri(img: Image.Image, max_side: int) -> str:
    im = img
    if max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _font_family(family: str) -> str:
    generic = "serif" if any(k in family.lower() for k in ("times", "georgia", "serif")) and \
        "sans" not in family.lower() else "sans-serif"
    return f"'{family.replace(chr(39), '')}', 'Leelawadee UI', 'Khmer Sangam MN', 'Noto Sans Khmer', {generic}"


def render_svg(scene: Scene, width_px: int, title: str = "QR code") -> str:
    W, H = scene.width, scene.height
    out_h = round(width_px * H / W)
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{out_h}" '
        f'viewBox="0 0 {_n(W)} {_n(H)}" shape-rendering="geometricPrecision">',
        f"<title>{escape(title)}</title>",
    ]
    defs: list[str] = []
    body: list[str] = []
    if scene.canvas_fill:
        body.append(f'<rect width="{_n(W)}" height="{_n(H)}" fill="{scene.canvas_fill}"/>')
    gi = 0
    for el in scene.elements:
        if isinstance(el, ShapeEl):
            s = el.shape
            if el.fill:
                body.append(f'<path d="{shape_path(s)}" fill="{el.fill}"/>')
            if el.stroke and el.stroke_w > 0:
                dash = f' stroke-dasharray="{_n(3 * el.stroke_w)} {_n(2 * el.stroke_w)}"' if el.dashed else ""
                body.append(f'<path d="{shape_path(s)}" fill="none" stroke="{el.stroke}" '
                            f'stroke-width="{_n(el.stroke_w)}"{dash}/>')
        elif isinstance(el, Layer):
            if not el.adds:
                continue
            d = "".join(shape_path(s) for s in el.adds) + "".join(shape_path(s) for s in el.cuts)
            fill = el.fill
            if isinstance(fill, Gradient):
                gi += 1
                defs.append(f'<linearGradient id="g{gi}" gradientUnits="userSpaceOnUse" x1="{_n(fill.x1)}" '
                            f'y1="{_n(fill.y1)}" x2="{_n(fill.x2)}" y2="{_n(fill.y2)}">'
                            f'<stop offset="0" stop-color="{fill.c0}"/><stop offset="1" stop-color="{fill.c1}"/>'
                            "</linearGradient>")
                fill = f"url(#g{gi})"
            body.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>')
        elif isinstance(el, TextEl):
            body.append(f'<text x="{_n(el.cx)}" y="{_n(el.baseline)}" text-anchor="middle" '
                        f'font-family={quoteattr(_font_family(el.family))} font-size="{_n(el.size)}" '
                        f'font-weight="{700 if el.bold else 400}" fill="{el.color}">{escape(el.text)}</text>')
        elif isinstance(el, ImageEl):
            px = int(el.w * width_px / W * 2)
            uri = _png_data_uri(el.image, max(64, min(2048, px)))
            body.append(f'<image x="{_n(el.x)}" y="{_n(el.y)}" width="{_n(el.w)}" height="{_n(el.h)}" '
                        f'preserveAspectRatio="xMidYMid meet" href="{uri}"/>')
    if defs:
        parts.append("<defs>" + "".join(defs) + "</defs>")
    parts += body
    parts.append("</svg>")
    return "\n".join(parts)
