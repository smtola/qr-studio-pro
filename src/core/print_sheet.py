"""Print sheets: many QR codes on A4 / Letter pages with optional cut guides (PDF, 300 dpi images)."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..models.project_settings import ProjectSettings
from ..utils.validation import ValidationError
from .export_manager import prepare
from .render_raster import render_raster

PAGES = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4)}
MM = 72.0 / 25.4
DPI = 300


@dataclass(frozen=True)
class SheetLayout:
    cols: int
    rows: int
    x0: float
    y0: float
    cell: float
    gap: float

    @property
    def per_page(self) -> int:
        return self.cols * self.rows


def compute_layout(page: str, cell_mm: float, margin_mm: float, gap_mm: float) -> SheetLayout:
    if page not in PAGES:
        raise ValidationError("Choose A4 or Letter.")
    pw, ph = PAGES[page]
    if not 15 <= cell_mm <= 150:
        raise ValidationError("The sticker size must be between 15 and 150 mm.")
    if not 0 <= margin_mm <= 40 or not 0 <= gap_mm <= 40:
        raise ValidationError("Margin and gap must be between 0 and 40 mm.")
    cols = int((pw - 2 * margin_mm + gap_mm) // (cell_mm + gap_mm))
    rows = int((ph - 2 * margin_mm + gap_mm) // (cell_mm + gap_mm))
    if cols < 1 or rows < 1:
        raise ValidationError("The sticker size does not fit on the page. Reduce the size or the margin.")
    used_w, used_h = cols * cell_mm + (cols - 1) * gap_mm, rows * cell_mm + (rows - 1) * gap_mm
    return SheetLayout(cols, rows, (pw - used_w) / 2, (ph - used_h) / 2, cell_mm, gap_mm)


def build_print_sheet(items: list[ProjectSettings], out_path: str | os.PathLike, *, page: str = "A4",
                      cell_mm: float = 40, margin_mm: float = 10, gap_mm: float = 6, guides: bool = True,
                      progress: Callable[[int, int], None] | None = None) -> tuple[Path, int]:
    """Write a multi-page PDF; returns (path, page_count). Each item is drawn at its own aspect ratio inside
    a square cell. Raises ValidationError for an invalid design or layout."""
    if not items:
        raise ValidationError("There is nothing to put on the sheet.")
    lay = compute_layout(page, cell_mm, margin_mm, gap_mm)
    pw, ph = PAGES[page]
    out = Path(out_path)
    if not out.parent.is_dir():
        raise ValidationError(f"The folder '{out.parent}' does not exist.")
    fd, tmp = tempfile.mkstemp(prefix=".qrstudio-", suffix=".tmp", dir=str(out.parent))
    os.close(fd)
    pages = 0
    try:
        c = canvas.Canvas(tmp, pagesize=(pw * MM, ph * MM))
        c.setTitle("QR Studio Pro print sheet")
        px = int(cell_mm / 25.4 * DPI)
        for i, s in enumerate(items):
            slot = i % lay.per_page
            if slot == 0 and i:
                c.showPage()
            if slot == 0:
                pages += 1
            col, row = slot % lay.cols, slot // lay.cols
            x = lay.x0 + col * (cell_mm + gap_mm)
            y_top = ph - (lay.y0 + row * (cell_mm + gap_mm))        # top edge of the cell, PDF origin bottom-left
            prep = prepare(s, strict=True)
            sw, sh = prep.scene.width, prep.scene.height
            k = cell_mm / max(sw, sh)
            w_mm, h_mm = sw * k, sh * k
            img = render_raster(prep.scene, max(int(w_mm / 25.4 * DPI), 100))
            c.drawImage(ImageReader(img), (x + (cell_mm - w_mm) / 2) * MM, (y_top - (cell_mm + h_mm) / 2) * MM,
                        w_mm * MM, h_mm * MM, mask="auto")
            if guides:
                c.setStrokeColorRGB(0.72, 0.72, 0.72)
                c.setLineWidth(0.4)
                c.setDash(2, 2)
                c.rect(x * MM, (y_top - cell_mm) * MM, cell_mm * MM, cell_mm * MM, stroke=1, fill=0)
                c.setDash()
            if progress:
                progress(i + 1, len(items))
        c.save()
        os.replace(tmp, out)
        tmp = ""
    except PermissionError:
        raise ValidationError(f"No permission to write to '{out.parent}'.") from None
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return out, pages
