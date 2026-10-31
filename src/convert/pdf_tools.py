"""PDF utilities: images <-> PDF, merge, split."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .common import ConvertError, require_file, unique_path

Progress = Callable[[int, int], None] | None
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def images_to_pdf(files: list[str | Path], out_dir: str | Path, *, name: str = "images", page: str = "fit",
                  progress: Progress = None) -> Path:
    """One page per image. page = 'fit' (page = image size) or 'a4' (image scaled to fit an A4 page)."""
    from PIL import Image, ImageOps
    if not files:
        raise ConvertError("Add at least one image.")
    pages = []
    for i, f in enumerate(files):
        p = require_file(f, IMAGE_EXTS)
        try:
            im = ImageOps.exif_transpose(Image.open(p))
            if im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").getchannel("A"))
                im = bg
            else:
                im = im.convert("RGB")
        except Exception:  # noqa: BLE001
            raise ConvertError(f"'{p.name}' is not a readable image.") from None
        if page == "a4":
            w, h = (1240, 1754) if im.width <= im.height else (1754, 1240)           # A4 at 150 dpi
            canvas = Image.new("RGB", (w, h), "white")
            im.thumbnail((w - 100, h - 100))
            canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            im = canvas
        pages.append(im)
        if progress:
            progress(i + 1, len(files))
    out = unique_path(out_dir, name, ".pdf")
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return out


def pdf_to_images(src: str | Path, out_dir: str | Path, *, fmt: str = "png", dpi: int = 150,
                  progress: Progress = None) -> list[Path]:
    import pypdfium2 as pdfium
    s = require_file(src, (".pdf",))
    fmt = fmt.lower().replace("jpeg", "jpg")
    if fmt not in ("png", "jpg"):
        raise ConvertError("Choose PNG or JPG.")
    dpi = max(36, min(int(dpi), 600))
    try:
        doc = pdfium.PdfDocument(str(s))
    except Exception:  # noqa: BLE001
        raise ConvertError("This PDF could not be opened (damaged or password protected).") from None
    outs: list[Path] = []
    n = len(doc)
    width = max(len(str(n)), 2)
    for i in range(n):
        im = doc[i].render(scale=dpi / 72).to_pil().convert("RGB")
        p = unique_path(out_dir, f"{s.stem}-p{str(i + 1).zfill(width)}", f".{fmt}")
        im.save(p, "PNG" if fmt == "png" else "JPEG", **({} if fmt == "png" else {"quality": 92}))
        outs.append(p)
        if progress:
            progress(i + 1, n)
    return outs


def merge_pdfs(files: list[str | Path], out_dir: str | Path, *, name: str = "merged", progress: Progress = None) -> Path:
    from pypdf import PdfWriter
    if len(files) < 2:
        raise ConvertError("Add at least two PDF files to merge.")
    w = PdfWriter()
    for i, f in enumerate(files):
        p = require_file(f, (".pdf",))
        try:
            w.append(str(p))
        except Exception:  # noqa: BLE001
            raise ConvertError(f"'{p.name}' could not be read (damaged or password protected).") from None
        if progress:
            progress(i + 1, len(files))
    out = unique_path(out_dir, name, ".pdf")
    with open(out, "wb") as fh:
        w.write(fh)
    return out


def parse_ranges(text: str, n_pages: int) -> list[int]:
    """'1-3, 5, 8-' -> zero-based page indexes in the given order."""
    pages: list[int] = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)?-(\d+)?|(\d+)", part)
        if not m:
            raise ConvertError(f"'{part}' is not a valid page range. Use e.g. 1-3, 5, 8-")
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a, b = int(m.group(1) or 1), int(m.group(2) or n_pages)
            if m.group(1) is None and m.group(2) is None:
                raise ConvertError("A range needs at least one number.")
        if a < 1 or b < 1 or a > n_pages or b > n_pages or a > b:
            raise ConvertError(f"Pages must be between 1 and {n_pages} (got '{part}').")
        pages += list(range(a - 1, b))
    if not pages:
        raise ConvertError("Enter the pages to keep, e.g. 1-3, 5")
    return pages


def split_pdf(src: str | Path, out_dir: str | Path, *, ranges: str = "", every_page: bool = False,
              progress: Progress = None) -> list[Path]:
    """`ranges` -> one PDF with those pages; `every_page` -> one PDF per page."""
    from pypdf import PdfReader, PdfWriter
    s = require_file(src, (".pdf",))
    try:
        r = PdfReader(str(s))
        n = len(r.pages)
    except Exception:  # noqa: BLE001
        raise ConvertError("This PDF could not be opened (damaged or password protected).") from None
    jobs: list[tuple[str, list[int]]]
    if every_page:
        width = max(len(str(n)), 2)
        jobs = [(f"{s.stem}-p{str(i + 1).zfill(width)}", [i]) for i in range(n)]
    else:
        jobs = [(f"{s.stem}-pages", parse_ranges(ranges, n))]
    outs = []
    for k, (stem, idx) in enumerate(jobs):
        w = PdfWriter()
        for i in idx:
            w.add_page(r.pages[i])
        out = unique_path(out_dir, stem, ".pdf")
        with open(out, "wb") as fh:
            w.write(fh)
        outs.append(out)
        if progress:
            progress(k + 1, len(jobs))
    return outs
