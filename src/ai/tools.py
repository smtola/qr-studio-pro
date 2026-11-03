"""The tools the AI Agent may call. Every file path must stay inside the user's chosen work folder, and every action
that writes or downloads asks the user first (`confirm`). Results are short plain-text strings for the model."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from ..convert import documents as D
from ..convert import downloader as DL
from ..convert import forms as F
from ..convert import media as M
from ..convert import pdf_tools as P
from ..convert.common import ConvertError

MAX_RESULT = 3500
DOC_OPS = ("excel_to_pdf", "word_to_pdf", "pdf_to_word", "pdf_to_excel", "excel_to_csv", "csv_to_excel")
PDF_OPS = ("merge", "split_ranges", "split_every_page", "images_to_pdf", "pdf_to_images")
IMAGE_OPS = ("convert", "resize", "compress")
VIDEO_OPS = ("convert", "to_gif", "extract_audio", "trim")


class ToolError(Exception):
    """A tool failed for a reason the model can read and explain."""


def _schema(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required}}


S = {"type": "string"}
N = {"type": "number"}


class Toolbox:
    def __init__(self, root: str | Path, confirm: Callable[[str], bool], cancel: threading.Event | None = None):
        self.root = Path(root).resolve()
        self.confirm = confirm
        self.cancel = cancel or threading.Event()
        self.created: list[Path] = []
        self._fns = {"list_files": self.list_files, "make_qr": self.make_qr, "convert_document": self.convert_document,
                     "pdf_tool": self.pdf_tool, "image_tool": self.image_tool, "video_tool": self.video_tool,
                     "pdf_form": self.pdf_form, "download_media": self.download_media}

    # ---- schemas
    def schemas(self) -> list[dict]:
        return [
            _schema("list_files", "List files and folders inside the user's work folder (or a sub-folder of it).",
                    {"subfolder": {**S, "description": "Relative sub-folder, empty for the work folder itself"}}, []),
            _schema("make_qr", "Create a QR code image file. Types: url, text, wifi, email, phone.",
                    {"type": {"type": "string", "enum": ["url", "text", "wifi", "email", "phone"]},
                     "value": {**S, "description": "The link, text, email address or phone number (for wifi: the network name)"},
                     "wifi_password": S, "subject": {**S, "description": "Email subject"},
                     "filename": {**S, "description": "Output file name without folder, e.g. menu.png"},
                     "format": {"type": "string", "enum": ["png", "svg", "pdf", "jpg"]},
                     "foreground": {**S, "description": "Hex colour like #111111"}, "background": {**S, "description": "Hex colour like #FFFFFF"}},
                    ["type", "value"]),
            _schema("convert_document", "Convert a document. Operations: " + ", ".join(DOC_OPS) + ".",
                    {"operation": {"type": "string", "enum": list(DOC_OPS)}, "input": {**S, "description": "File path inside the work folder"}},
                    ["operation", "input"]),
            _schema("pdf_tool", "PDF utilities: merge (inputs=PDFs), split_ranges (input + ranges like '1-3,5'), "
                    "split_every_page, images_to_pdf (inputs=pictures), pdf_to_images.",
                    {"operation": {"type": "string", "enum": list(PDF_OPS)}, "inputs": {"type": "array", "items": S},
                     "ranges": S, "output_name": S}, ["operation", "inputs"]),
            _schema("image_tool", "Picture tools: convert (format png/jpg/webp/gif/bmp), resize (width in px), compress (quality 1-100).",
                    {"operation": {"type": "string", "enum": list(IMAGE_OPS)}, "input": S, "format": S, "width": N, "quality": N},
                    ["operation", "input"]),
            _schema("video_tool", "Video tools: convert (format mp4/webm/mkv), to_gif (start, duration seconds), extract_audio (format mp3/m4a/wav), trim (start, end seconds).",
                    {"operation": {"type": "string", "enum": list(VIDEO_OPS)}, "input": S, "format": S, "start": N, "end": N, "duration": N},
                    ["operation", "input"]),
            _schema("pdf_form", "Read or fill a fillable PDF form. list_fields shows field names; fill needs values {field: text}.",
                    {"operation": {"type": "string", "enum": ["list_fields", "fill"]}, "input": S,
                     "values": {"type": "object", "additionalProperties": S}, "flatten": {"type": "boolean"}}, ["operation", "input"]),
            _schema("download_media", "Download a video, audio track or picture from a public link (YouTube, TikTok, Facebook, "
                    "Instagram, X). Only for content the user owns or may keep.",
                    {"url": S, "kind": {"type": "string", "enum": ["video", "audio", "image"]},
                     "quality": {"type": "string", "enum": list(DL.QUALITIES)}}, ["url"]),
        ]

    # ---- dispatch
    def run(self, name: str, args: dict) -> str:
        fn = self._fns.get(name)
        if fn is None:
            return f"Error: unknown tool '{name}'."
        if self.cancel.is_set():
            return "Error: cancelled by the user."
        try:
            out = fn(**(args or {}))
        except ToolError as e:
            return f"Error: {e}"
        except ConvertError as e:
            return f"Error: {e}"
        except TypeError as e:
            return f"Error: bad arguments ({e})."
        except Exception as e:  # noqa: BLE001
            return f"Error: {type(e).__name__}: {str(e)[:200]}"
        return out[:MAX_RESULT]

    # ---- helpers
    def path(self, rel: str, must_exist: bool = True) -> Path:
        if not isinstance(rel, str) or not rel.strip():
            raise ToolError("A file path is required.")
        p = Path(rel)
        p = (p if p.is_absolute() else self.root / p).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ToolError("That path is outside the work folder. Only files inside the work folder can be used.") from None
        if must_exist and not p.exists():
            raise ToolError(f"'{rel}' was not found in the work folder.")
        return p

    def _ask(self, text: str) -> None:
        if not self.confirm(text):
            raise ToolError("The user declined this action.")

    def _rel(self, paths) -> str:
        paths = paths if isinstance(paths, list) else [paths]
        self.created += [Path(p) for p in paths]
        names = []
        for p in paths:
            try:
                names.append(str(Path(p).resolve().relative_to(self.root)))
            except ValueError:
                names.append(Path(p).name)
        return "Created: " + ", ".join(names[:20]) + (f" (+{len(names) - 20} more)" if len(names) > 20 else "")

    # ---- tools
    def list_files(self, subfolder: str = "") -> str:
        d = self.path(subfolder, must_exist=True) if subfolder else self.root
        if not d.is_dir():
            raise ToolError("That is not a folder.")
        items = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = [(p.name + "/") if p.is_dir() else f"{p.name} ({p.stat().st_size // 1024} KB)" for p in items if not p.name.startswith(".")]
        return "\n".join(lines[:200]) or "(empty folder)"

    def make_qr(self, type: str = "url", value: str = "", wifi_password: str = "", subject: str = "", filename: str = "",
                format: str = "png", foreground: str = "", background: str = "") -> str:
        from ..core.export_manager import ExportError, export_to_file
        from ..models.project_settings import ProjectSettings
        from ..utils.validation import ValidationError, slugify
        s = ProjectSettings()
        c = s.content
        c.type = type
        if type == "url":
            c.url = value
        elif type == "text":
            c.text = value
        elif type == "wifi":
            c.wifi_ssid, c.wifi_password = value, wifi_password
            c.wifi_security = "WPA" if wifi_password else "nopass"
        elif type == "email":
            c.email_to, c.email_subject = value, subject
        elif type == "phone":
            c.phone = value
        else:
            raise ToolError("Unsupported QR type.")
        if foreground:
            s.colors.foreground = foreground
        if background:
            s.colors.background = background
        s.sanitize()
        fmt = format if format in ("png", "svg", "pdf", "jpg") else "png"
        name = Path(filename).name if filename else slugify(value) + "." + fmt
        if "." not in name:
            name += "." + fmt
        out = self.path(name, must_exist=False)
        n = 2
        while out.exists():
            out = out.with_name(f"{Path(name).stem} ({n}){Path(name).suffix}")
            n += 1
        self._ask(f"Create QR code '{out.name}' ({type}: {value[:60]})")
        try:
            export_to_file(s, out, fmt=fmt)
        except (ValidationError, ExportError) as e:
            raise ToolError(str(e)) from None
        return self._rel(out)

    def convert_document(self, operation: str, input: str) -> str:
        if operation not in DOC_OPS:
            raise ToolError("Unknown operation.")
        src = self.path(input)
        self._ask(f"{operation.replace('_', ' ')}: {src.name}")
        out = self.root
        fn = {"excel_to_pdf": D.excel_to_pdf, "word_to_pdf": D.word_to_pdf, "pdf_to_word": D.pdf_to_word,
              "pdf_to_excel": D.pdf_to_excel, "excel_to_csv": D.excel_to_csv, "csv_to_excel": D.csv_to_excel}[operation]
        return self._rel(fn(src, src.parent if src.parent != self.root else out))

    def pdf_tool(self, operation: str, inputs: list[str], ranges: str = "", output_name: str = "") -> str:
        if operation not in PDF_OPS:
            raise ToolError("Unknown operation.")
        files = [self.path(i) for i in (inputs or [])]
        if not files:
            raise ToolError("At least one input file is required.")
        self._ask(f"PDF {operation.replace('_', ' ')}: " + ", ".join(f.name for f in files[:5]))
        out = self.root
        kw = {"name": output_name} if output_name else {}
        if operation == "merge":
            return self._rel(P.merge_pdfs(files, out, **kw))
        if operation == "images_to_pdf":
            return self._rel(P.images_to_pdf(files, out, **kw))
        if operation == "pdf_to_images":
            return self._rel(P.pdf_to_images(files[0], out))
        if operation == "split_every_page":
            return self._rel(P.split_pdf(files[0], out, every_page=True))
        if not ranges:
            raise ToolError("Page ranges are required, for example '1-3,5'.")
        return self._rel(P.split_pdf(files[0], out, ranges=ranges))

    def image_tool(self, operation: str, input: str, format: str = "png", width: float = 0, quality: float = 80) -> str:
        if operation not in IMAGE_OPS:
            raise ToolError("Unknown operation.")
        src = self.path(input)
        self._ask(f"Picture {operation}: {src.name}")
        if operation == "convert":
            return self._rel(M.convert_image(src, self.root, fmt=format))
        if operation == "resize":
            if width <= 0:
                raise ToolError("A width in pixels is required.")
            return self._rel(M.resize_image(src, self.root, width=int(width)))
        return self._rel(M.compress_image(src, self.root, quality=int(quality)))

    def video_tool(self, operation: str, input: str, format: str = "", start: float = 0, end: float = 0, duration: float = 5) -> str:
        if operation not in VIDEO_OPS:
            raise ToolError("Unknown operation.")
        src = self.path(input)
        self._ask(f"Video {operation.replace('_', ' ')}: {src.name}")
        c = self.cancel
        if operation == "convert":
            return self._rel(M.convert_video(src, self.root, fmt=format or "mp4", cancel=c))
        if operation == "to_gif":
            return self._rel(M.video_to_gif(src, self.root, start=start, duration=duration or 5, cancel=c))
        if operation == "extract_audio":
            return self._rel(M.extract_audio(src, self.root, fmt=format or "mp3", cancel=c))
        return self._rel(M.trim_video(src, self.root, start=start, end=end, cancel=c))

    def pdf_form(self, operation: str, input: str, values: dict | None = None, flatten: bool = False) -> str:
        src = self.path(input)
        if operation == "list_fields":
            fields = F.list_form_fields(src)
            if not fields:
                return "This PDF has no fillable fields."
            return "\n".join(f"{f.name} [{f.kind}]" + (f" label={f.label}" if f.label else "") + (f" value={f.value}" if f.value else "")
                             for f in fields[:150])
        if operation != "fill":
            raise ToolError("Unknown operation.")
        if not values:
            raise ToolError("Values are required to fill the form.")
        self._ask(f"Fill {len(values)} field(s) in {src.name}" + (" and flatten" if flatten else ""))
        return self._rel(F.fill_form(src, self.root, {str(k): str(v) for k, v in values.items()}, flatten=bool(flatten)))

    def download_media(self, url: str, kind: str = "video", quality: str = "best") -> str:
        u = DL.clean_url(url)
        self._ask(f"Download {kind} from {DL.detect_platform(u)}:\n{u}\n\n{DL.RIGHTS_NOTICE}")
        return self._rel(DL.download(u, self.root, kind, quality, cancel=self.cancel))
