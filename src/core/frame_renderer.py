"""Layout: places QR block, logo, frame decoration and text into a Scene (logical pixel units)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

from ..models.project_settings import ProjectSettings
from .fonts import measure
from .logo_composer import plan_logo
from .qr_generator import QRMatrix, build_qr_layers
from .scene import ALL, Scene, Shape, ShapeEl, TextEl

_ROLE_SCALE = {"company": 0.8, "title": 1.0, "caption": 0.6}
_ROLE_ORDER = ("company", "title", "caption")


@dataclass
class _Item:
    role: str
    text: str
    size: float
    w: float
    asc: float
    desc: float
    kind: str          # plain | pill | header
    vpad: float = 0.0

    @property
    def line_h(self) -> float:
        return self.asc + self.desc

    @property
    def box_h(self) -> float:
        return self.line_h + 2 * self.vpad

    @property
    def box_w(self) -> float:
        return self.w + (2 * self.size * 0.9 if self.kind == "pill" else 0.0)


def _fit(text: str, family: str, bold: bool, size: float, max_w: float) -> float:
    w, _, _ = measure(text, family, bold, size)
    while w > max_w and size > 8:
        size = max(8.0, size * 0.92)
        w, _, _ = measure(text, family, bold, size)
    return size


def build_scene(settings: ProjectSettings, qrm: QRMatrix, logo: Image.Image | None) -> Scene:
    f, ex = settings.frame, settings.export
    S = float(ex.qr_size)
    ftype = f.type
    has_frame = ftype != "none"
    t = float(f.thickness) if has_frame else 0.0
    bt = 3 * t if ftype == "double" else t
    pad = float(f.padding) if has_frame else 0.0
    margin = float(f.margin) if has_frame else 0.0
    bold = f.font_weight == "bold"
    gap = float(f.text_gap)
    max_text_w = S if ftype == "badge" else S + 2 * pad

    # ---- text items --------------------------------------------------------------------
    texts = {"company": f.company.strip(), "title": f.title.strip(), "caption": f.caption.strip()}
    header_role = None
    if ftype == "corporate":
        header_role = "company" if texts["company"] else ("title" if texts["title"] else None)
    items: dict[str, _Item] = {}
    for role in _ROLE_ORDER:
        txt = texts[role]
        if not txt:
            continue
        kind = "header" if role == header_role else ("pill" if ftype == "cta" and role == "title" else "plain")
        size = _fit(txt, f.font_family, bold, f.font_size * _ROLE_SCALE[role],
                    max_text_w - (2 * f.font_size * 0.9 if kind == "pill" else 0))
        w, asc, desc = measure(txt, f.font_family, bold, size)
        items[role] = _Item(role, txt, size, w, asc, desc, kind, size * 0.45 if kind != "plain" else 0.0)

    header = items.pop(header_role) if header_role else None
    positions = {"company": f.company_position, "title": f.title_position, "caption": f.caption_position}
    top = [items[r] for r in _ROLE_ORDER if r in items and positions[r] == "top"]
    bottom = [items[r] for r in _ROLE_ORDER if r in items and positions[r] == "bottom"]

    content_w = max([S] + [i.box_w for i in top + bottom])
    content_h = sum(i.box_h + gap for i in top) + S + sum(gap + i.box_h for i in bottom)
    header_h = header.box_h if header else 0.0

    # ---- frame box ---------------------------------------------------------------------
    if not has_frame:
        w_out, h_out = content_w, content_h
    elif ftype == "badge":
        d = math.hypot(content_w, content_h) + 2 * (pad + bt)
        d = max(d, float(f.min_width), float(f.min_height))
        w_out = h_out = d
    else:
        w_out = max(content_w + 2 * pad + 2 * bt, float(f.min_width))
        h_out = max(header_h + content_h + 2 * pad + 2 * bt, float(f.min_height))
    W, H = w_out + 2 * margin, h_out + 2 * margin
    fx, fy = margin, margin
    cx = fx + w_out / 2

    trans = settings.colors.transparent
    scene = Scene(W, H, None if trans else f.outer_color)
    scene.frame_box = (fx, fy, w_out, h_out)
    els = scene.elements

    # ---- frame decoration --------------------------------------------------------------
    radius = float(f.radius)
    if has_frame:
        if ftype == "badge":
            outer = Shape("ellipse", fx, fy, w_out, h_out)
        else:
            r = 0.0 if ftype == "simple" else radius
            outer = Shape("rrect", fx, fy, w_out, h_out, min(r, min(w_out, h_out) / 2))
        fill_bg = None if trans else f.background
        dashed = f.border_style == "dashed"
        if t > 0:
            els.append(ShapeEl(outer, fill=fill_bg))
            els.append(ShapeEl(outer.inset(t / 2), stroke=f.color, stroke_w=t, dashed=dashed))
            if ftype == "double":
                els.append(ShapeEl(outer.inset(t * 2.5), stroke=f.color, stroke_w=t, dashed=dashed))
        else:
            els.append(ShapeEl(outer, fill=fill_bg))

    ix, iy = fx + bt, fy + bt
    w_in = w_out - 2 * bt
    dy = max(0.0, (h_out - 2 * bt - header_h - content_h - 2 * pad) / 2) if has_frame and ftype != "badge" else 0.0
    if ftype == "badge":
        y = fy + (h_out - content_h) / 2
    else:
        y = iy + header_h + pad + dy
    if not has_frame:
        y = fy

    if header and header_h:
        r_in = max(radius - bt, 0.0)
        shape = Shape("rrect", ix, iy, w_in, header_h, min(r_in, header_h), (True, True, False, False))
        els.append(ShapeEl(shape, fill=f.color))
        base = iy + header.vpad + header.asc
        els.append(TextEl(cx, base, header.text, f.font_family, header.size, bold, f.bar_text_color))
        scene.text_boxes.append((cx - header.w / 2, iy + header.vpad, header.w, header.line_h))

    def place(item: _Item, y0: float) -> None:
        if item.kind == "pill":
            bx = cx - item.box_w / 2
            els.append(ShapeEl(Shape("rrect", bx, y0, item.box_w, item.box_h, item.box_h / 2), fill=f.color))
            color = f.bar_text_color
        else:
            color = f.text_color
        base = y0 + item.vpad + item.asc
        els.append(TextEl(cx, base, item.text, f.font_family, item.size, bold, color))
        scene.text_boxes.append((cx - item.w / 2, y0 + item.vpad, item.w, item.line_h))

    for it in top:
        place(it, y)
        y += it.box_h + gap

    # ---- QR block -----------------------------------------------------------------------
    bx = cx - S / 2
    by = y
    scene.qr_block = (bx, by, S, S)
    if not trans:
        pr = min(radius, S * 0.1) if ftype == "card" else 0.0
        els.append(ShapeEl(Shape("rrect", bx, by, S, S, pr), fill=settings.colors.background))
    layers, symbol = build_qr_layers(settings, qrm, bx, by, S)
    scene.symbol = symbol
    els.extend(layers)
    y += S

    for it in bottom:
        y += gap
        place(it, y)
        y += it.box_h

    # ---- logo (always last so it is crisp on top) ----------------------------------------
    if logo is not None and settings.logo.enabled:
        plan = plan_logo(settings, logo, symbol)
        if plan.backing:
            els.append(plan.backing)
        els.append(plan.image)
        scene.logo_box, scene.backing_box = plan.logo_box, plan.backing_box
    return scene
