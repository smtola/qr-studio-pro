"""QR matrix generation and conversion of the matrix into drawable geometry layers."""
from __future__ import annotations

from dataclasses import dataclass

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from qrcode.exceptions import DataOverflowError

from ..models.project_settings import ProjectSettings
from ..utils.validation import ValidationError
from .scene import Gradient, Layer, Shape

_ECC = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}


@dataclass(frozen=True)
class QRMatrix:
    modules: tuple[tuple[bool, ...], ...]
    version: int
    ecc: str
    payload: str

    @property
    def size(self) -> int:
        return len(self.modules)


def effective_ecc(settings: ProjectSettings, logo_active: bool) -> str:
    """Chosen level, raised to H when a centre logo covers modules (if auto-raise is on)."""
    if logo_active and settings.logo.auto_high_ecc:
        return "H"
    return settings.content.ecc


def generate_matrix(payload: str, ecc: str = "M") -> QRMatrix:
    if not payload:
        raise ValidationError("There is nothing to encode yet.")
    if ecc not in _ECC:
        raise ValidationError(f"Unknown error-correction level '{ecc}'.")
    qr = qrcode.QRCode(version=None, error_correction=_ECC[ecc], box_size=1, border=0)
    try:
        qr.add_data(payload)
        qr.make(fit=True)
    except (DataOverflowError, ValueError):
        raise ValidationError("The content is too long to fit in a QR code at this error-correction "
                              "level. Shorten it or choose a lower level (L or M).") from None
    mods = tuple(tuple(bool(c) for c in row) for row in qr.get_matrix())
    return QRMatrix(mods, qr.version, ecc, payload)


def _in_finder(r: int, c: int, n: int) -> bool:
    return (r < 7 and c < 7) or (r < 7 and c >= n - 7) or (r >= n - 7 and c < 7)


def _gradient(settings: ProjectSettings, x: float, y: float, w: float, h: float) -> Gradient:
    import math
    ang = math.radians(settings.colors.gradient_angle)
    dx, dy = math.cos(ang), math.sin(ang)
    half = (abs(w * dx) + abs(h * dy)) / 2
    cx, cy = x + w / 2, y + h / 2
    return Gradient(settings.colors.foreground, settings.colors.gradient_end,
                    cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half)


def build_qr_layers(settings: ProjectSettings, qrm: QRMatrix, bx: float, by: float,
                    block: float) -> tuple[list[Layer], tuple[float, float, float, float]]:
    """Return drawable layers and the symbol rect (x, y, w, h) for a QR block placed at (bx, by)."""
    n, q = qrm.size, settings.content.quiet_zone
    m = block / (n + 2 * q)
    ox, oy = bx + q * m, by + q * m
    sym = (ox, oy, n * m, n * m)
    co, ey = settings.colors, settings.eyes
    module_fill = _gradient(settings, *sym) if co.gradient else co.foreground
    eye_outer = module_fill if ey.follow_foreground else ey.outer_color
    eye_inner = module_fill if ey.follow_foreground else ey.inner_color

    dark = [[qrm.modules[r][c] and not _in_finder(r, c, n) for c in range(n)] for r in range(n)]

    def at(r: int, c: int) -> bool:
        return 0 <= r < n and 0 <= c < n and dark[r][c]

    shapes: list[Shape] = []
    for r in range(n):
        for c in range(n):
            if not dark[r][c]:
                continue
            x, y = ox + c * m, oy + r * m
            if co.module_style == "dots":
                d = m * 0.86
                shapes.append(Shape("ellipse", x + (m - d) / 2, y + (m - d) / 2, d, d))
            elif co.module_style == "small-dots":
                d = m * 0.62
                shapes.append(Shape("ellipse", x + (m - d) / 2, y + (m - d) / 2, d, d))
            elif co.module_style == "gapped":
                d = m * 0.84
                shapes.append(Shape("rrect", x + (m - d) / 2, y + (m - d) / 2, d, d, d * 0.22))
            elif co.module_style == "bars":
                up, dn = at(r - 1, c), at(r + 1, c)
                w = m * 0.8
                corners = (not up, not up, not dn, not dn)
                shapes.append(Shape("rrect", x + (m - w) / 2, y, w, m, w * 0.5, corners) if any(corners)
                              else Shape("rrect", x + (m - w) / 2, y, w, m))
            elif co.module_style == "rounded":
                up, dn, lf, rt = at(r - 1, c), at(r + 1, c), at(r, c - 1), at(r, c + 1)
                corners = (not up and not lf, not up and not rt, not dn and not rt, not dn and not lf)
                shapes.append(Shape("rrect", x, y, m, m, m * 0.5, corners) if any(corners)
                              else Shape("rrect", x, y, m, m))
            else:
                shapes.append(Shape("rrect", x, y, m, m))

    def eye_shape(style: str, x: float, y: float, size: float, outer: bool) -> Shape:
        if style == "square":
            return Shape("rrect", x, y, size, size)
        if style == "circle":
            return Shape("ellipse", x, y, size, size)
        return Shape("rrect", x, y, size, size, size * (0.16 if outer else 0.2))

    rings_add, rings_cut, pupils = [], [], []
    for er, ec in ((0, 0), (0, n - 7), (n - 7, 0)):
        x, y = ox + ec * m, oy + er * m
        rings_add.append(eye_shape(ey.outer_style, x, y, 7 * m, True))
        rings_cut.append(eye_shape(ey.outer_style, x + m, y + m, 5 * m, True))
        pupils.append(eye_shape(ey.inner_style, x + 2 * m, y + 2 * m, 3 * m, False))
    layers = [Layer(shapes, [], module_fill), Layer(rings_add, rings_cut, eye_outer), Layer(pupils, [], eye_inner)]
    return layers, sym
