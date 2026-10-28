"""System font discovery and text measurement shared by the raster, SVG and PDF renderers."""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

from PIL import ImageFont

FONT_FAMILIES = ("Arial", "Helvetica", "Segoe UI", "Verdana", "Tahoma", "Georgia", "Times New Roman",
                 "Courier New", "DejaVu Sans", "Noto Sans", "Leelawadee UI", "Khmer UI")

_SEARCH_DIRS = {
    "win32": [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
              Path.home() / "AppData/Local/Microsoft/Windows/Fonts"],
    "darwin": [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
               Path("/Library/Fonts"), Path.home() / "Library/Fonts"],
}
_DEFAULT_DIRS = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
                 Path.home() / ".local/share/fonts"]

_SANS_FALLBACK = ("arial", "helvetica", "segoeui", "dejavusans", "liberationsans", "notosans", "freesans")
_KHMER_FALLBACK = ("leelawadeeui", "leelawadee", "khmerui", "khmersangammn", "khmermn", "notosanskhmer",
                   "notoserifkhmer", "khmerossystem", "khmeros", "battambang", "hanuman")
_ALIASES = {"helvetica": ("helvetica", "arial", "liberationsans"), "arial": ("arial", "liberationsans", "arimo"),
            "timesnewroman": ("timesnewroman", "times", "liberationserif"),
            "couriernew": ("couriernew", "cour", "liberationmono"), "segoeui": ("segoeui",)}


def _key(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


@functools.lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    idx: dict[str, str] = {}
    dirs = _SEARCH_DIRS.get(sys.platform, _DEFAULT_DIRS)
    for d in dirs:
        if not d.is_dir():
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    idx.setdefault(_key(Path(f).stem), str(Path(root) / f))
    return idx


def has_khmer(text: str) -> bool:
    return any("\u1780" <= ch <= "\u17ff" or "\u19e0" <= ch <= "\u19ff" for ch in text)


def _lookup(fam: str, bold: bool) -> tuple[str | None, bool]:
    """Return (path, is_really_bold)."""
    idx = _index()
    names = _ALIASES.get(fam, (fam,))
    if bold:
        for n in names:
            for suffix in ("bold", "bd", "b", "boldmt", "-bold"):
                p = idx.get(n + suffix.replace("-", ""))
                if p:
                    return p, True
    for n in names:
        for suffix in ("", "regular", "book", "mt"):
            p = idx.get(n + suffix)
            if p:
                return p, False
    return None, False


@functools.lru_cache(maxsize=256)
def resolve_font(family: str, bold: bool, khmer: bool = False) -> tuple[str | None, bool]:
    """Pick a font file. Returns (path or None, synthetic_bold_needed)."""
    candidates: list[str] = []
    fam = _key(family)
    if khmer and fam not in _KHMER_FALLBACK:
        candidates += list(_KHMER_FALLBACK)
    candidates += [fam] + [f for f in _SANS_FALLBACK if f != fam]
    for cand in candidates:
        path, real_bold = _lookup(cand, bold)
        if path:
            return path, bold and not real_bold
    return None, bold


def system_font_available(family: str) -> bool:
    return _lookup(_key(family), False)[0] is not None


@functools.lru_cache(maxsize=512)
def load_font(path: str | None, px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    px = max(int(px), 4)
    if path:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            pass
    return ImageFont.load_default(px)


@functools.lru_cache(maxsize=1024)
def measure(text: str, family: str, bold: bool, size: float) -> tuple[float, float, float]:
    """Return (width, ascent, descent) for the text at `size` logical units."""
    probe = 10  # measure at 10x for sub-unit accuracy
    path, synth = resolve_font(family, bold, has_khmer(text))
    font = load_font(path, round(size * probe))
    width = font.getlength(text) / probe
    try:
        asc, desc = font.getmetrics()
    except AttributeError:
        asc, desc = size * 0.9 * probe, size * 0.25 * probe
    if synth:
        width += size * 0.03
    return width, asc / probe, desc / probe
