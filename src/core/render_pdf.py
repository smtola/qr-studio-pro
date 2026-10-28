"""PDF back-end (ReportLab): vector shapes; text as live text when Latin, otherwise as high-res image."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .fonts import has_khmer, resolve_font
from .render_raster import text_mask
from .scene import Gradient, ImageEl, Layer, Scene, Shape, ShapeEl, TextEl

K = 0.5522847498
_registered: dict[str, str] = {}


def _latin1(s: str) -> bool:
    try:
        s.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _pdf_font(family: str, bold: bool) -> str:
    low = family.lower()
    base = ("Times" if any(k in low for k in ("times", "georgia")) else
            "Courier" if any(k in low for k in ("courier", "mono")) else "Helvetica")
    std = {"Helvetica": ("Helvetica", "Helvetica-Bold"), "Times": ("Times-Roman", "Times-Bold"),
           "Courier": ("Courier", "Courier-Bold")}[base]
    path, synth = resolve_font(family, bold, False)
    if path and path.lower().endswith(".ttf") and not synth and base == "Helvetica" and \
            Path(path).stem.lower() not in ("arial", "arialbd", "helvetica"):
        name = f"QRS-{Path(path).stem}"
        if name not in _registered:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                _registered[name] = name
            except Exception:  # noqa: BLE001 - any font problem => fall back to a base-14 font
                return std[1] if bold else std[0]
        return name
    return std[1] if bold else std[0]


def _path(c: Canvas, p, s: Shape) -> None:
    x, y, w, h = s.x, s.y, s.w, s.h
    if s.kind == "ellipse":
        rx, ry = w / 2, h / 2
        cx, cy = x + rx, y + ry
        p.moveTo(cx + rx, cy)
        p.curveTo(cx + rx, cy + K * ry, cx + K * rx, cy + ry, cx, cy + ry)
        p.curveTo(cx - K * rx, cy + ry, cx - rx, cy + K * ry, cx - rx, cy)
        p.curveTo(cx - rx, cy - K * ry, cx - K * rx, cy - ry, cx, cy - ry)
        p.curveTo(cx + K * rx, cy - ry, cx + rx, cy - K * ry, cx + rx, cy)
        p.close()
        return
    r = min(s.r, w / 2, h / 2)
    tl, tr, br, bl = (r if cc else 0.0 for cc in s.corners)
    p.moveTo(x + tl, y)
    p.lineTo(x + w - tr, y)
    if tr:
        p.curveTo(x + w - tr + K * tr, y, x + w, y + tr - K * tr, x + w, y + tr)
    p.lineTo(x + w, y + h - br)
    if br:
        p.curveTo(x + w, y + h - br + K * br, x + w - br + K * br, y + h, x + w - br, y + h)
    p.lineTo(x + bl, y + h)
    if bl:
        p.curveTo(x + bl - K * bl, y + h, x, y + h - bl + K * bl, x, y + h - bl)
    p.lineTo(x, y + tl)
    if tl:
        p.curveTo(x, y + tl - K * tl, x + tl - K * tl, y, x + tl, y)
    p.close()


def render_pdf(scene: Scene, width_px: int, dpi: int, title: str = "QR code") -> bytes:
    W, H = scene.width, scene.height
    pt_w = width_px / dpi * 72.0
    pt_h = pt_w * H / W
    k = pt_w / W
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(pt_w, pt_h), invariant=1, pageCompression=1)
    c.setTitle(title)
    c.setAuthor("")
    c.setCreator("QR Studio Pro")
    c.setProducer("QR Studio Pro")
    c.translate(0, pt_h)
    c.scale(k, -k)  # y-down logical units, same as the SVG and raster back-ends

    if scene.canvas_fill:
        c.setFillColor(HexColor(scene.canvas_fill))
        c.rect(0, 0, W, H, stroke=0, fill=1)

    for el in scene.elements:
        if isinstance(el, ShapeEl):
            if el.fill:
                c.setFillColor(HexColor(el.fill))
                p = c.beginPath()
                _path(c, p, el.shape)
                c.drawPath(p, stroke=0, fill=1)
            if el.stroke and el.stroke_w > 0:
                c.setStrokeColor(HexColor(el.stroke))
                c.setLineWidth(el.stroke_w)
                c.setDash(*( ([3 * el.stroke_w, 2 * el.stroke_w], 0) if el.dashed else ([], 0)))
                p = c.beginPath()
                _path(c, p, el.shape)
                c.drawPath(p, stroke=1, fill=0)
                c.setDash([], 0)
        elif isinstance(el, Layer):
            if not el.adds:
                continue
            p = c.beginPath()
            for s in el.adds + el.cuts:
                _path(c, p, s)
            if isinstance(el.fill, Gradient):
                g = el.fill
                c.saveState()
                c.clipPath(p, stroke=0, fill=0, fillMode=0)  # 0 = even-odd
                c.linearGradient(g.x1, g.y1, g.x2, g.y2, (HexColor(g.c0), HexColor(g.c1)), extend=True)
                c.restoreState()
            else:
                c.setFillColor(HexColor(el.fill))
                c.drawPath(p, stroke=0, fill=1, fillMode=0)
        elif isinstance(el, TextEl):
            if _latin1(el.text) and not has_khmer(el.text):
                font = _pdf_font(el.family, el.bold)
                c.saveState()
                c.translate(el.cx, el.baseline)
                c.scale(1, -1)
                c.setFillColor(HexColor(el.color))
                c.setFont(font, el.size)
                c.drawCentredString(0, 0, el.text)
                c.restoreState()
            else:  # complex scripts (e.g. Khmer) need shaping: embed the text as a high-res image
                kk = 6.0 * max(1.0, 300 / dpi * 2)
                mask, x0, y0 = text_mask(el, kk)
                col = Image.new("RGBA", mask.size, _rgb(el.color) + (255,))
                col.putalpha(mask)
                c.saveState()
                c.translate(x0 / kk, y0 / kk + mask.height / kk)
                c.scale(1, -1)
                c.drawImage(ImageReader(col), 0, 0, mask.width / kk, mask.height / kk, mask="auto")
                c.restoreState()
        elif isinstance(el, ImageEl):
            img = el.image
            px = int(el.w * k / 72 * 600)  # ~600 dpi at placed size
            if max(img.size) > max(256, px):
                img = img.copy()
                img.thumbnail((max(256, px),) * 2, Image.Resampling.LANCZOS)
            c.saveState()
            c.translate(el.x, el.y + el.h)
            c.scale(1, -1)
            c.drawImage(ImageReader(img), 0, 0, el.w, el.h, mask="auto", preserveAspectRatio=True)
            c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def _rgb(hexv: str) -> tuple[int, int, int]:
    h = hexv.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
