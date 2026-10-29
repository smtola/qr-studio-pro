"""Export section (format / size controls) and the native Save flow."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (QMessageBox, QProgressDialog, QPushButton, QFileDialog, QVBoxLayout, QWidget)

from ..core.export_manager import EXT, ExportError, export_to_file, prepare
from ..models.project_settings import EXPORT_FORMATS
from ..services.app_prefs import AppPrefs
from ..utils.logging_config import get_logger
from ..utils.validation import ValidationError, slugify
from .state import AppState
from .widgets import SliderRow, combo, form, muted, set_combo, set_value, spin

log = get_logger("export-ui")
FORMATS = [("PNG – best quality, supports transparency", "png"), ("JPG – small files for sharing", "jpg"),
           ("SVG – vector (scales without blur)", "svg"), ("PDF – print ready", "pdf")]
FILTERS = {"png": "PNG image (*.png)", "jpg": "JPEG image (*.jpg *.jpeg)", "svg": "SVG vector (*.svg)",
           "pdf": "PDF document (*.pdf)"}


def default_filename(state: AppState, fmt: str) -> str:
    s = state.settings
    c = s.content
    base = {"url": c.url, "text": c.text, "email": c.email_to, "phone": c.phone, "sms": c.sms_number,
            "wifi": c.wifi_ssid, "vcard": c.vcard_name}.get(c.type, "")
    return f"qr-code-{slugify(base, 'design')}{EXT[fmt]}"


class _ExportSig(QObject):
    done = Signal(object, str)


class _ExportJob(QRunnable):
    def __init__(self, settings, target: Path, overwrite: bool, fmt: str, sig: _ExportSig):
        super().__init__()
        self.a, self.sig = (settings, target, overwrite, fmt), sig

    def run(self) -> None:
        settings, target, overwrite, fmt = self.a
        try:
            self.sig.done.emit(export_to_file(settings, target, overwrite=overwrite, fmt=fmt), "")
        except (ValidationError, ExportError, FileExistsError, OSError) as e:
            log.warning("export failed: %s", e)
            self.sig.done.emit(None, str(e) or "The file could not be saved.")
        except Exception as e:  # noqa: BLE001
            log.exception("export crashed")
            self.sig.done.emit(None, f"Export failed: {e}")


class ExportSection(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        f = form()
        self.format = combo("Export format", FORMATS)
        self.width = spin("Export width in pixels", 200, 6000, " px", 100)
        self.dpi = spin("Print resolution", 72, 1200, " dpi", 50)
        self.quality = SliderRow("JPEG quality", 60, 100, 95, "")
        self.qr_size = spin("QR block size in the layout", 200, 2000, " px", 50)
        f.addRow("Format", self.format)
        f.addRow("Width", self.width)
        f.addRow("Resolution", self.dpi)
        f.addRow("JPEG quality", self.quality)
        f.addRow("QR size in layout", self.qr_size)
        lay.addLayout(f)
        self.info = muted("")
        lay.addWidget(self.info)
        self.button = QPushButton("Export…")
        self.button.setProperty("primary", True)
        self.button.setAccessibleName("Export")
        lay.addWidget(self.button)
        self.format.currentIndexChanged.connect(lambda: self._set("format", self.format.currentData()))
        self.width.valueChanged.connect(lambda v: self._set("width_px", v))
        self.dpi.valueChanged.connect(lambda v: self._set("dpi", v))
        self.quality.valueChanged.connect(lambda v: self._set("jpeg_quality", v))
        self.qr_size.valueChanged.connect(lambda v: self._set("qr_size", v))
        state.loaded.connect(self.refresh)
        state.changed.connect(self._info)
        self.refresh()

    def _set(self, attr: str, v) -> None:
        setattr(self.state.settings.export, attr, v)
        if attr == "format":
            self._enable()
        self.state.edit()

    def _enable(self) -> None:
        fmt = self.state.settings.export.format
        self.quality.setEnabled(fmt == "jpg")
        self.dpi.setEnabled(fmt in ("png", "jpg", "pdf"))

    def refresh(self) -> None:
        e = self.state.settings.export
        set_combo(self.format, e.format)
        set_value(self.width, e.width_px)
        set_value(self.dpi, e.dpi)
        self.quality.set_value(e.jpeg_quality)
        set_value(self.qr_size, e.qr_size)
        self._enable()
        self._info()

    def _info(self) -> None:
        p = self.state.last_prep
        if p is None:
            self.info.setText("")
            return
        w, h = p.output_size()
        e = self.state.settings.export
        self.info.setText(f"Output: {w} × {h} px  ·  {w / e.dpi * 2.54:.1f} × {h / e.dpi * 2.54:.1f} cm at {e.dpi} dpi")


def run_export(parent: QWidget, state: AppState, prefs: AppPrefs) -> bool:
    """Validate, ask for a location (native dialog), warn before overwriting, export, report."""
    state.flush()
    s = state.settings
    try:
        prepare(s, strict=True)
    except ValidationError as e:
        QMessageBox.warning(parent, "Cannot export yet", str(e))
        return False
    fmt = s.export.format if s.export.format in EXPORT_FORMATS else "png"
    start = str(Path(prefs.last_export_dir or Path.home()) / default_filename(state, fmt))
    filters = ";;".join(FILTERS[k] for k in (fmt, *[x for x in EXPORT_FORMATS if x != fmt]))
    path, chosen = QFileDialog.getSaveFileName(parent, "Export QR code", start, filters,
                                               options=QFileDialog.Option.DontConfirmOverwrite)
    if not path:
        return False
    out_fmt = next((k for k, v in FILTERS.items() if v == chosen), fmt)
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in ("png", "jpg", "jpeg", "svg", "pdf"):
        out_fmt = "jpg" if suffix == "jpeg" else suffix
    target = Path(path)
    if target.suffix.lower() not in (EXT[out_fmt], ".jpeg"):
        target = target.with_name(target.name + EXT[out_fmt])
    overwrite = False
    if target.exists():
        r = QMessageBox.question(parent, "Replace file?", f"“{target.name}” already exists. Replace it?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return False
        overwrite = True
    # Run the export on a worker thread; the dialog keeps the window responsive (no frozen UI).
    sig, box = _ExportSig(), {}
    loop = QEventLoop()
    sig.done.connect(lambda r, e: (box.update(res=r, err=e), loop.quit()))
    dlg = QProgressDialog(f"Exporting {target.name}…", None, 0, 0, parent)
    dlg.setWindowTitle("Exporting")
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.show()
    QThreadPool.globalInstance().start(_ExportJob(s.clone(), target, overwrite, out_fmt, sig))
    loop.exec()
    dlg.close()
    dlg.deleteLater()
    res = box.get("res")
    if res is None:
        QMessageBox.critical(parent, "Export failed", box.get("err") or "The file could not be saved.")
        return False
    prefs.last_export_dir = str(res.path.parent)
    prefs.save()
    msg = f"Saved {res.path.name}  ({res.width} × {res.height} px, {res.size_bytes / 1024:.0f} KB)"
    state.toast.emit(msg)
    notes = "\n".join(res.notes)
    QMessageBox.information(parent, "Export complete", f"{msg}\n\n{res.path.parent}" + (f"\n\n{notes}" if notes else "") +
                            "\n\nTip: test the exported code with a few phones before printing.")
    return True
