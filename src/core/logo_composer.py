"""Centre-logo loading (safely) and geometry planning."""
from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..models.project_settings import ProjectSettings
from ..utils.validation import ValidationError
from .scene import ImageEl, Shape, ShapeEl

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 8000
STORE_SIDE = 2048           # logos are kept at most this big in memory
SUPPORTED = (".png", ".jpg", ".jpeg", ".svg")


class LogoError(ValidationError):
    """Logo could not be used; message is user-facing."""


@dataclass
class LogoInfo:
    image: Image.Image          # RGBA, at most STORE_SIDE on the longest side
    sha256: str
    has_alpha: bool


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rasterize_svg(data: bytes) -> Image.Image:
    text = data[:2_000_000].decode("utf-8", errors="ignore").lower()
    if "<svg" not in text:
        raise LogoError("This file is not a valid SVG image.")
    if re.search(r"<script|<foreignobject|<!entity|(?:xlink:)?href\s*=\s*[\"']\s*(?:https?:|file:|ftp:)", text):
        raise LogoError("This SVG contains scripts or external references and cannot be used safely. "
                        "Export a plain SVG or use PNG instead.")
    try:
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError as e:  # pragma: no cover
        raise LogoError("SVG logos need the Qt SVG module, which is not available.") from e
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        raise LogoError("This SVG file could not be read.")
    size = renderer.defaultSize()
    if size.isEmpty():
        size = renderer.viewBox().size()
    if size.isEmpty():
        raise LogoError("This SVG has no usable size.")
    scale = STORE_SIDE / max(size.width(), size.height())
    w, h = max(1, round(size.width() * scale)), max(1, round(size.height() * scale))
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, w, h))
    p.end()
    ptr = img.constBits()
    return Image.frombytes("RGBA", (w, h), bytes(ptr), "raw", "RGBA", img.bytesPerLine(), 1)


def load_logo(path: str | os.PathLike) -> LogoInfo:
    p = Path(path)
    if not str(path).strip():
        raise LogoError("No logo file has been chosen.")
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        raise LogoError("Unsupported logo format. Use PNG, JPG or SVG.")
    try:
        size = p.stat().st_size
    except OSError:
        raise LogoError(f"The logo file '{p.name}' could not be found or opened.") from None
    if size == 0 or size > MAX_FILE_BYTES:
        raise LogoError(f"The logo file must be between 1 byte and {MAX_FILE_BYTES // 1024 // 1024} MB.")
    try:
        data = p.read_bytes()
    except OSError:
        raise LogoError(f"The logo file '{p.name}' could not be read.") from None
    digest = hashlib.sha256(data).hexdigest()
    try:
        if ext == ".svg":
            img = _rasterize_svg(data)
        else:
            import io
            with Image.open(io.BytesIO(data)) as im:
                if im.format not in ("PNG", "JPEG"):
                    raise LogoError("The file content does not match a PNG or JPG image.")
                if im.width > MAX_SIDE or im.height > MAX_SIDE or im.width * im.height > MAX_PIXELS:
                    raise LogoError(f"The logo is too large ({im.width}×{im.height}px). "
                                    f"Maximum is {MAX_SIDE}px per side.")
                im.load()
                img = ImageOps.exif_transpose(im).convert("RGBA")
    except LogoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        raise LogoError("This file is damaged or is not a valid image.") from None
    if img.width < 1 or img.height < 1:
        raise LogoError("The logo image is empty.")
    if max(img.size) > STORE_SIDE:
        img.thumbnail((STORE_SIDE, STORE_SIDE), Image.Resampling.LANCZOS)
    alpha = img.getchannel("A")
    return LogoInfo(img, digest, alpha.getextrema()[0] < 255)


_cache: dict[tuple[str, int, int], LogoInfo] = {}


def load_logo_cached(path: str) -> LogoInfo:
    try:
        st = os.stat(path)
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        raise LogoError(f"The logo file '{Path(path).name}' could not be found or opened.") from None
    hit = _cache.get(key)
    if hit is None:
        if len(_cache) > 8:
            _cache.clear()
        hit = _cache[key] = load_logo(path)
    return hit


@dataclass
class LogoPlan:
    backing: ShapeEl | None
    image: ImageEl
    backing_box: tuple[float, float, float, float]
    logo_box: tuple[float, float, float, float]
    covered_fraction: float     # share of the symbol area hidden by backing / logo


def plan_logo(settings: ProjectSettings, logo: Image.Image,
              symbol: tuple[float, float, float, float]) -> LogoPlan:
    """Place the logo at the exact centre of the symbol, aspect ratio preserved, never cropped."""
    lg = settings.logo
    sx, sy, sw, sh = symbol
    cx, cy = sx + sw / 2, sy + sh / 2
    box = sw * lg.size_pct / 100.0                      # backing box side
    pad = box * lg.padding_pct / 100.0 if lg.backing != "none" else 0.0
    inner = box - 2 * pad
    aspect = logo.width / logo.height
    if lg.backing == "circle":                          # logo rectangle must sit inside the circle
        lw = inner / math.sqrt(1 + 1 / aspect ** 2)
        lh = lw / aspect
    elif aspect >= 1:
        lw, lh = inner, inner / aspect
    else:
        lw, lh = inner * aspect, inner
    logo_box = (cx - lw / 2, cy - lh / 2, lw, lh)
    bb = (cx - box / 2, cy - box / 2, box, box)
    backing = None
    area = lw * lh
    if lg.backing != "none":
        if lg.backing == "circle":
            shape = Shape("ellipse", *bb)
            area = math.pi * box * box / 4
        elif lg.backing == "rounded":
            shape = Shape("rrect", *bb, r=box * 0.22)
            area = box * box * (1 - (4 - math.pi) * 0.22 ** 2)
        else:
            shape = Shape("rrect", *bb)
            area = box * box
        backing = ShapeEl(shape, fill=lg.backing_color)
    return LogoPlan(backing, ImageEl(logo, *logo_box), bb, logo_box, area / (sw * sh))
