"""PDF to Form: find the blanks in an ordinary PDF and turn them into fillable fields; list / fill existing forms."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import ConvertError, require_file, unique_path

MAX_PAGES = 200


@dataclass
class FieldSpec:
    page: int                  # zero-based
    x0: float
    top: float                 # pdfplumber coordinates (origin top-left, points)
    x1: float
    bottom: float
    kind: str = "text"         # text | checkbox
    name: str = ""
    label: str = ""
    enabled: bool = True

    @property
    def size(self) -> tuple[float, float]:
        return self.x1 - self.x0, self.bottom - self.top


def _slug(text: str) -> str:
    t = re.sub(r"[^\w]+", "_", text.strip().lower(), flags=re.UNICODE).strip("_")
    return t[:40] or "field"


def _label_for(words: list[dict], x0: float, top: float, bottom: float, page_top_limit: float = 0.0) -> str:
    """Text to the left on the same line, else the line of text just above the blank."""
    mid = (top + bottom) / 2
    left = [w for w in words if w["x1"] <= x0 + 2 and abs(((w["top"] + w["bottom"]) / 2) - mid) < 8]
    if left:
        left.sort(key=lambda w: w["x0"])
        near = [left[-1]]
        for w in reversed(left[:-1]):
            if near[0]["x0"] - w["x1"] < 14 and len(near) < 6:
                near.insert(0, w)
            else:
                break
        return " ".join(w["text"] for w in near).strip(" :")
    above = [w for w in words if w["bottom"] <= top + 1 and top - w["bottom"] < 18 and w["x0"] < x0 + 40 and w["x1"] > x0 - 40]
    if above:
        above.sort(key=lambda w: (-w["bottom"], w["x0"]))
        row = [w for w in above if abs(w["bottom"] - above[0]["bottom"]) < 3]
        return " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"])).strip(" :")
    return ""


def detect_fields(src: str | Path, *, min_width: float = 40.0) -> list[FieldSpec]:
    """Heuristics: ruled lines, text like '____', empty boxes (text fields) and tiny squares (checkboxes)."""
    import pdfplumber
    s = require_file(src, (".pdf",))
    try:
        pdf = pdfplumber.open(str(s))
    except Exception:  # noqa: BLE001
        raise ConvertError("This PDF could not be opened (damaged or password protected).") from None
    specs: list[FieldSpec] = []
    with pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise ConvertError(f"This PDF has more than {MAX_PAGES} pages.")
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words(keep_blank_chars=False)
            text_boxes = [(w["x0"], w["top"], w["x1"], w["bottom"]) for w in words]

            def has_text(x0, t, x1, b):
                return any(a0 < x1 - 1 and a1 > x0 + 1 and a2 > t + 1 and a3 < b + 1 and a1 > x0 for a0, a1, a2, a3 in
                           [(w[0], w[2], w[1], w[3]) for w in text_boxes])

            cands: list[FieldSpec] = []
            # 1) horizontal rules
            for ln in page.lines + [r for r in page.rects if r["height"] < 1.6]:
                w = ln["x1"] - ln["x0"]
                if w >= min_width and abs(ln.get("y1", ln["bottom"]) - ln.get("y0", ln["top"])) < 1.6 and w < page.width * 0.9:
                    y = ln["top"] if "top" in ln else page.height - ln["y0"]
                    cands.append(FieldSpec(pi, ln["x0"], y - 16, ln["x1"], y - 1))
            # 2) underscore / dot leaders in text
            for w in words:
                if re.fullmatch(r"[_.\-–—]{4,}", w["text"]) and w["x1"] - w["x0"] >= min_width * 0.6:
                    cands.append(FieldSpec(pi, w["x0"], w["top"] - 2, w["x1"], w["bottom"] + 1))
            # 3) boxes
            for r in page.rects:
                w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
                if r.get("fill") and r.get("non_stroking_color") not in (None, (1,), (1, 1, 1), 1, [1, 1, 1]):
                    continue
                if 7 <= w <= 18 and 7 <= h <= 18 and abs(w - h) < 3 and not has_text(r["x0"], r["top"], r["x1"], r["bottom"]):
                    cands.append(FieldSpec(pi, r["x0"], r["top"], r["x1"], r["bottom"], kind="checkbox"))
                elif w >= min_width and 12 <= h <= 60 and w < page.width * 0.95 and not has_text(r["x0"], r["top"], r["x1"], r["bottom"]):
                    cands.append(FieldSpec(pi, r["x0"], r["top"], r["x1"], r["bottom"]))
            # de-duplicate overlapping candidates
            cands.sort(key=lambda c: (round(c.top / 4), c.x0))
            kept: list[FieldSpec] = []
            for c in cands:
                if any(k.kind == c.kind and abs(k.x0 - c.x0) < 6 and abs(k.bottom - c.bottom) < 10 for k in kept):
                    continue
                kept.append(c)
            for c in kept:
                c.label = _label_for(words, c.x0, c.top, c.bottom)
            specs += kept
    used: dict[str, int] = {}
    for sp in specs:
        base = _slug(sp.label) if sp.label else ("checkbox" if sp.kind == "checkbox" else "field")
        used[base] = used.get(base, 0) + 1
        sp.name = base if used[base] == 1 else f"{base}_{used[base]}"
    return specs


# ------------------------------------------------------------------------------------------ writing widgets
def _checkbox_stream(writer, w: float, h: float, on: bool):
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject
    st = DecodedStreamObject()
    body = f"q 0.2 w 0 G 0 0 {w:.2f} {h:.2f} re S"
    if on:
        body += f" 0.8 w 2 {h * 0.5:.2f} m {w * 0.42:.2f} 2 l {w - 2:.2f} {h - 2:.2f} l S"
    st.set_data((body + " Q").encode())
    st.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
               NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)]),
               NameObject("/Resources"): DictionaryObject()})
    return writer._add_object(st)


def make_fillable(src: str | Path, out_dir: str | Path, fields: list[FieldSpec], *, font_size: float = 0) -> Path:
    """Add AcroForm fields at the given positions. font_size 0 = auto."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, BooleanObject, DictionaryObject, FloatObject, NameObject, NumberObject,
                               TextStringObject)
    s = require_file(src, (".pdf",))
    chosen = [f for f in fields if f.enabled]
    if not chosen:
        raise ConvertError("There are no fields to add.")
    try:
        reader = PdfReader(str(s))
        if reader.is_encrypted:
            raise ConvertError("This PDF is password protected.")
        writer = PdfWriter(clone_from=reader)
    except ConvertError:
        raise
    except Exception:  # noqa: BLE001
        raise ConvertError("This PDF could not be opened (damaged or password protected).") from None
    names: set[str] = set()
    helv = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    helv_ref = writer._add_object(helv)
    existing = writer._root_object.get("/AcroForm")
    acro = existing.get_object() if existing is not None else DictionaryObject()
    fields_arr = acro.get("/Fields", ArrayObject())
    if not isinstance(fields_arr, ArrayObject):
        fields_arr = ArrayObject(fields_arr)
    dr = acro.get("/DR", DictionaryObject())
    dr_fonts = dr.get("/Font", DictionaryObject())
    dr_fonts[NameObject("/Helv")] = helv_ref
    dr[NameObject("/Font")] = dr_fonts
    for f in chosen:
        if not 0 <= f.page < len(writer.pages):
            raise ConvertError(f"Page {f.page + 1} does not exist.")
        page = writer.pages[f.page]
        ll, ur = page.mediabox.lower_left, page.mediabox.upper_right
        ph = float(ur[1]) - float(ll[1])
        name = re.sub(r"[^\w.\-]", "_", f.name or "field") or "field"
        base, k = name, 2
        while name in names:
            name, k = f"{base}_{k}", k + 1
        names.add(name)
        x0, x1 = float(ll[0]) + f.x0, float(ll[0]) + f.x1
        y0, y1 = float(ll[1]) + ph - f.bottom, float(ll[1]) + ph - f.top
        w, h = x1 - x0, y1 - y0
        annot = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/T"): TextStringObject(name), NameObject("/F"): NumberObject(4),
            NameObject("/Rect"): ArrayObject([FloatObject(round(v, 2)) for v in (x0, y0, x1, y1)]),
            NameObject("/P"): page.indirect_reference,
        })
        if f.label:
            annot[NameObject("/TU")] = TextStringObject(f.label)
        if f.kind == "checkbox":
            annot[NameObject("/FT")] = NameObject("/Btn")
            annot[NameObject("/V")] = NameObject("/Off")
            annot[NameObject("/AS")] = NameObject("/Off")
            annot[NameObject("/MK")] = DictionaryObject()
            annot[NameObject("/AP")] = DictionaryObject({NameObject("/N"): DictionaryObject({
                NameObject("/Yes"): _checkbox_stream(writer, w, h, True),
                NameObject("/Off"): _checkbox_stream(writer, w, h, False)})})
        else:
            fs = font_size or max(7.0, min(12.0, h * 0.62))
            annot[NameObject("/FT")] = NameObject("/Tx")
            annot[NameObject("/Ff")] = NumberObject(0)
            annot[NameObject("/DA")] = TextStringObject(f"/Helv {fs:.1f} Tf 0 0 0.6 rg")
            annot[NameObject("/MK")] = DictionaryObject({
                NameObject("/BG"): ArrayObject([FloatObject(0.93), FloatObject(0.95), FloatObject(1.0)])})
        ref = writer._add_object(annot)
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.get_object().append(ref)
        fields_arr.append(ref)
    acro[NameObject("/Fields")] = fields_arr
    acro[NameObject("/DR")] = dr
    acro[NameObject("/DA")] = TextStringObject("/Helv 0 Tf 0 g")
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)
    writer._root_object[NameObject("/AcroForm")] = acro
    out = unique_path(out_dir, f"{s.stem}-fillable", ".pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    return out


# ------------------------------------------------------------------------------------------ existing forms
@dataclass
class FormField:
    name: str
    kind: str                  # text | checkbox | choice | other
    value: str = ""
    options: list[str] = field(default_factory=list)
    label: str = ""


def list_form_fields(src: str | Path) -> list[FormField]:
    from pypdf import PdfReader
    s = require_file(src, (".pdf",))
    try:
        r = PdfReader(str(s))
        raw = r.get_fields() or {}
    except Exception:  # noqa: BLE001
        raise ConvertError("This PDF could not be opened (damaged or password protected).") from None
    out = []
    for name, f in raw.items():
        ft = str(f.get("/FT", ""))
        v = f.get("/V")
        kind = {"/Tx": "text", "/Btn": "checkbox", "/Ch": "choice"}.get(ft, "other")
        if kind == "checkbox" and f.get("/Ff", 0) & (1 << 16):          # push button
            kind = "other"
        opts = [str(o[1] if isinstance(o, list) and len(o) > 1 else o) for o in f.get("/Opt", [])] if kind == "choice" else []
        out.append(FormField(name, kind, "" if v is None else str(v).lstrip("/"), opts, str(f.get("/TU", ""))))
    return out


def fill_form(src: str | Path, out_dir: str | Path, values: dict[str, str], *, flatten: bool = False,
              suffix: str = "-filled") -> Path:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject
    s = require_file(src, (".pdf",))
    fields = {f.name: f for f in list_form_fields(s)}
    if not fields:
        raise ConvertError("This PDF has no fillable fields. Use 'Make fillable' first.")
    unknown = [k for k in values if k not in fields]
    if unknown:
        raise ConvertError(f"Unknown field(s): {', '.join(unknown[:5])}")
    prepared: dict[str, str] = {}
    for k, v in values.items():
        f = fields[k]
        if f.kind == "checkbox":
            prepared[k] = "/Yes" if str(v).strip().lower() in ("1", "yes", "true", "x", "on", "/yes") else "/Off"
        else:
            prepared[k] = str(v)
    try:
        writer = PdfWriter(clone_from=PdfReader(str(s)))
        for page in writer.pages:
            writer.update_page_form_field_values(page, prepared, auto_regenerate=False, flatten=flatten)
        if not flatten:
            writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
    except Exception as e:  # noqa: BLE001
        raise ConvertError(f"The form could not be filled: {e}") from None
    out = unique_path(out_dir, f"{s.stem}{suffix}", ".pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    return out


def fields_csv_template(src: str | Path, out_path: str | Path) -> Path:
    names = [f.name for f in list_form_fields(src) if f.kind in ("text", "checkbox", "choice")]
    if not names:
        raise ConvertError("This PDF has no fillable fields.")
    p = Path(out_path)
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerow(names)
    return p


def fill_from_csv(src: str | Path, csv_path: str | Path, out_dir: str | Path, *, flatten: bool = False,
                  name_column: str = "") -> list[Path]:
    """One filled PDF per CSV row (the header row holds the field names)."""
    c = require_file(csv_path, (".csv", ".txt"))
    with open(c, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ConvertError("The CSV file has no data rows (the first row must be the field names).")
    if len(rows) > 1000:
        raise ConvertError("A CSV can fill at most 1000 forms at once.")
    outs = []
    for i, row in enumerate(rows, 1):
        vals = {k: v for k, v in row.items() if k and k.strip()}
        stem = Path(src).stem
        suffix = f"-{_slug(row.get(name_column, ''))}" if name_column and row.get(name_column) else f"-{i:03d}"
        outs.append(fill_form(src, out_dir, vals, flatten=flatten, suffix=suffix))
    return outs
