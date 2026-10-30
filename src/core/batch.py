"""Batch generation: one QR code per CSV row, using the current design. Pure Python, no Qt."""
from __future__ import annotations

import csv
import io
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..models.project_settings import ProjectSettings
from ..utils.validation import ValidationError, normalize_url, slugify
from .export_manager import ExportError, export_to_file

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024
VALUE_COLS = ("content", "url", "text", "data", "value", "link")
FILE_COLS = ("filename", "file", "name")
TEMPLATE_CSV = ("content,filename,title,caption,company\n"
                "https://example.com/menu,menu,SCAN FOR MENU,example.com,Example Cafe\n"
                "https://example.com/wifi,wifi,FREE WI-FI,Scan to connect,Example Cafe\n")


@dataclass
class BatchRow:
    line: int
    value: str
    filename: str = ""
    title: str | None = None
    caption: str | None = None
    company: str | None = None


@dataclass
class RowResult:
    line: int
    value: str
    ok: bool
    detail: str          # output path or error message


@dataclass
class BatchReport:
    results: list[RowResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok_count(self) -> int:
        return sum(r.ok for r in self.results)

    @property
    def failed(self) -> list[RowResult]:
        return [r for r in self.results if not r.ok]


def parse_csv_text(text: str) -> list[BatchRow]:
    text = text.lstrip("﻿")
    if not text.strip():
        raise ValidationError("The CSV file is empty.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows, lines = [], []
    for r in reader:
        if any(c.strip() for c in r):
            rows.append(r)
            lines.append(reader.line_num)
    if not rows:
        raise ValidationError("The CSV file has no rows.")
    head = [c.strip().lower() for c in rows[0]]
    known = set(VALUE_COLS) | set(FILE_COLS) | {"title", "caption", "company"}
    has_header = any(h in known for h in head)
    idx: dict[str, int] = {}
    if has_header:
        for i, h in enumerate(head):
            idx.setdefault(h, i)
        body, blines = rows[1:], lines[1:]
        vcol = next((idx[c] for c in VALUE_COLS if c in idx), 0)
    else:
        body, blines, vcol = rows, lines, 0

    def cell(r: list[str], key: str | tuple[str, ...]) -> str | None:
        keys = (key,) if isinstance(key, str) else key
        for k in keys:
            if k in idx and idx[k] < len(r):
                return r[idx[k]].strip() or None
        return None

    out: list[BatchRow] = []
    for r, ln in zip(body, blines):
        if vcol >= len(r) or not r[vcol].strip():
            continue
        out.append(BatchRow(ln, r[vcol].strip(), cell(r, FILE_COLS) or "", cell(r, "title"),
                            cell(r, "caption"), cell(r, "company")))
    if not out:
        raise ValidationError("No rows with content were found in the CSV file.")
    if len(out) > MAX_ROWS:
        raise ValidationError(f"The CSV has {len(out)} rows; the limit is {MAX_ROWS} per batch.")
    return out


def read_csv(path: str | Path) -> list[BatchRow]:
    p = Path(path)
    try:
        if p.stat().st_size > MAX_BYTES:
            raise ValidationError("This CSV file is too large (limit 5 MB).")
        raw = p.read_bytes()
    except OSError:
        raise ValidationError(f"The file '{p.name}' could not be opened.") from None
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return parse_csv_text(raw.decode(enc))
        except UnicodeError:
            continue
    raise ValidationError("The CSV file encoding is not supported. Save it as UTF-8.")


def settings_for_row(base: ProjectSettings, row: BatchRow, kind: str = "auto") -> ProjectSettings:
    s = base.clone()
    c = s.content
    as_url = kind == "url"
    if kind == "auto":
        try:
            normalize_url(row.value)
            as_url = "://" in row.value or "." in row.value
        except ValidationError:
            as_url = False
    if as_url:
        c.type, c.url = "url", row.value
    else:
        c.type, c.text = "text", row.value
    for attr in ("title", "caption", "company"):
        v = getattr(row, attr)
        if v is not None:
            setattr(s.frame, attr, v)
    return s.sanitize()


def safe_name(name: str, fallback: str) -> str:
    n = re.sub(r"\.(png|jpe?g|svg|pdf)$", "", name.strip(), flags=re.I)
    return slugify(n, fallback) if n else fallback


def run_batch(base: ProjectSettings, rows: list[BatchRow], out_dir: str | Path, *, kind: str = "auto",
              progress: Callable[[int, int, RowResult], None] | None = None,
              cancel: threading.Event | None = None, write_report: bool = True) -> BatchReport:
    out = Path(out_dir)
    if not out.is_dir():
        raise ValidationError(f"The folder '{out}' does not exist.")
    report, used = BatchReport(), set()
    for i, row in enumerate(rows):
        if cancel is not None and cancel.is_set():
            report.cancelled = True
            break
        stem = safe_name(row.filename, "") or slugify(row.value, f"qr-{i + 1}")
        name, k = stem, 2
        while name.lower() in used:
            name, k = f"{stem}-{k}", k + 1
        used.add(name.lower())
        try:
            res = export_to_file(settings_for_row(base, row, kind), out / name, overwrite=True,
                                 fmt=base.export.format)
            rr = RowResult(row.line, row.value, True, res.path.name)
        except (ValidationError, ExportError, OSError) as e:
            rr = RowResult(row.line, row.value, False, str(e))
        except Exception as e:  # noqa: BLE001 - one bad row must never stop the batch
            rr = RowResult(row.line, row.value, False, f"Unexpected error: {e}")
        report.results.append(rr)
        if progress:
            progress(i + 1, len(rows), rr)
    if write_report and report.results:
        try:
            with open(out / "batch-report.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["line", "content", "status", "file_or_error"])
                for r in report.results:
                    w.writerow([r.line, r.value, "ok" if r.ok else "failed", r.detail])
        except OSError:
            pass
    return report
