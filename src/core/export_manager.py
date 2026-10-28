"""High-level pipeline: settings -> scene -> preview image / exported file."""
from __future__ import annotations

import functools
import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ..models.project_settings import EXPORT_FORMATS, ProjectSettings
from ..utils.logging_config import get_logger
from ..utils.validation import ValidationError
from .logo_composer import LogoError, LogoInfo, load_logo_cached
from .qr_generator import QRMatrix, effective_ecc, generate_matrix
from .render_pdf import render_pdf
from .render_raster import flatten, render_raster
from .render_svg import render_svg
from .scan_advisor import Advice, advise
from .frame_renderer import build_scene
from .scene import Scene

log = get_logger("export")
MAX_PIXELS_OUT = 80_000_000
EXT = {"png": ".png", "jpg": ".jpg", "svg": ".svg", "pdf": ".pdf"}


class ExportError(RuntimeError):
    """Export failed; message is user-facing."""


@dataclass
class Prepared:
    settings: ProjectSettings
    scene: Scene
    qrm: QRMatrix
    logo: LogoInfo | None
    logo_error: str | None
    ecc_used: str
    advice: list[Advice] = field(default_factory=list)

    def output_size(self, width_px: int | None = None) -> tuple[int, int]:
        w = width_px or self.settings.export.width_px
        return w, round(w * self.scene.height / self.scene.width)


@functools.lru_cache(maxsize=32)
def _matrix(payload: str, ecc: str) -> QRMatrix:
    return generate_matrix(payload, ecc)


def prepare(settings: ProjectSettings, *, strict: bool = False) -> Prepared:
    """Validate and lay out. strict=True (exports) raises when a requested logo cannot be loaded;
    strict=False (live preview) records the problem and renders without it."""
    s = settings.clone().sanitize()
    payload = s.content.payload()           # may raise ValidationError
    logo: LogoInfo | None = None
    logo_error: str | None = None
    if s.logo.enabled and s.logo.path:
        try:
            logo = load_logo_cached(s.logo.path)
        except LogoError as e:
            if strict:
                raise
            logo_error = str(e)
    ecc = effective_ecc(s, logo is not None)
    qrm = _matrix(payload, ecc)
    scene = build_scene(s, qrm, logo.image if logo else None)
    covered = 0.0
    if logo is not None and scene.backing_box is not None:
        from .logo_composer import plan_logo
        covered = plan_logo(s, logo.image, scene.symbol).covered_fraction
    n_total = qrm.size + 2 * s.content.quiet_zone
    module_px = (s.export.qr_size / n_total) * s.export.width_px / scene.width
    adv = advise(s, version=qrm.version, logo_loaded=logo is not None, logo_error=logo_error,
                 covered_fraction=covered, module_px=module_px, ecc_used=ecc)
    return Prepared(s, scene, qrm, logo, logo_error, ecc, adv)


def render_image(prep: Prepared, width_px: int) -> Image.Image:
    return render_raster(prep.scene, width_px)


def render_preview(settings: ProjectSettings, width_px: int) -> tuple[Image.Image, Prepared]:
    prep = prepare(settings, strict=False)
    return render_image(prep, width_px), prep


@dataclass
class ExportResult:
    path: Path
    format: str
    width: int
    height: int
    size_bytes: int
    notes: list[str] = field(default_factory=list)


def encode(prep: Prepared, fmt: str | None = None) -> tuple[bytes, ExportResult]:
    """Render the design to bytes in the requested format."""
    s = prep.settings
    ex = s.export
    fmt = (fmt or ex.format).lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in EXPORT_FORMATS:
        raise ExportError(f"Unsupported export format '{fmt}'.")
    w, h = prep.output_size()
    notes: list[str] = []
    if w * h > MAX_PIXELS_OUT:
        raise ExportError(f"The export would be {w}×{h} px, which is too large. Reduce the width or use SVG/PDF.")
    if fmt in ("png", "jpg"):
        img = render_image(prep, w)
        buf = io.BytesIO()
        if fmt == "png":
            if img.getchannel("A").getextrema()[0] == 255:
                img = img.convert("RGB")
            img.save(buf, "PNG", dpi=(ex.dpi, ex.dpi), optimize=True)
        else:
            if s.colors.transparent:
                notes.append("JPEG has no transparency; the transparent background was filled with white.")
            flat = flatten(img, s.frame.outer_color if not s.colors.transparent else "#FFFFFF")
            flat.save(buf, "JPEG", quality=ex.jpeg_quality, subsampling=0, optimize=True, dpi=(ex.dpi, ex.dpi))
        data = buf.getvalue()
    elif fmt == "svg":
        data = render_svg(prep.scene, w).encode("utf-8")
        if prep.logo is not None:
            notes.append("The centre logo is embedded as a PNG image inside the SVG.")
    else:
        data = render_pdf(prep.scene, w, ex.dpi)
    return data, ExportResult(Path(), fmt, w, h, len(data), notes)


def export_to_file(settings: ProjectSettings, path: str | os.PathLike, *, overwrite: bool = False,
                   fmt: str | None = None) -> ExportResult:
    p = Path(path)
    fmt = (fmt or "").lower() or p.suffix.lower().lstrip(".").replace("jpeg", "jpg") or settings.export.format
    if fmt not in EXPORT_FORMATS:
        fmt = settings.export.format
    if p.suffix.lower() not in (EXT[fmt], ".jpeg" if fmt == "jpg" else EXT[fmt]):
        p = p.with_name(p.name + EXT[fmt])
    if not p.parent.is_dir():
        raise ExportError(f"The folder '{p.parent}' does not exist.")
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    try:
        prep = prepare(settings, strict=True)
        data, res = encode(prep, fmt)
    except (ValidationError, ExportError):
        raise
    except MemoryError:
        raise ExportError("Not enough memory for this export size. Try a smaller width or use SVG/PDF.") from None
    except Exception as e:  # noqa: BLE001
        log.exception("export render failed")
        raise ExportError(f"Rendering failed: {e}") from e
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".qrstudio-", suffix=".tmp", dir=str(p.parent))
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, p)
        tmp_name = None
    except PermissionError:
        raise ExportError(f"No permission to write to '{p.parent}'. Choose another folder.") from None
    except OSError as e:
        raise ExportError(f"The file could not be saved: {e.strerror or e}") from None
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    res.path = p
    log.info("exported", extra={"ctx": {"format": res.format, "w": res.width, "h": res.height, "bytes": res.size_bytes}})
    return res
