"""Dialogs for the productivity tools: CSV batch, print sheet, template gallery, recent projects."""
from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..core.batch import TEMPLATE_CSV, BatchRow, read_csv, run_batch, settings_for_row
from ..core.export_manager import prepare
from ..core.print_sheet import PAGES, build_print_sheet
from ..core.render_raster import render_raster
from ..models.project_settings import ProjectSettings
from ..services.app_prefs import AppPrefs
from ..services.project_service import load_project
from ..services.templates import TEMPLATES, Template, apply_template
from ..utils.logging_config import get_logger
from ..utils.validation import ValidationError
from .state import AppState
from .widgets import combo, form, muted, spin

log = get_logger("tools-ui")


# ---------------------------------------------------------------------------------------------- helpers
class _Sig(QObject):
    progress = Signal(int, int)
    done = Signal(object, str)          # result, error message


class _Task(QRunnable):
    def __init__(self, fn, sig: _Sig):
        super().__init__()
        self.fn, self.sig = fn, sig

    def run(self) -> None:
        try:
            self.sig.done.emit(self.fn(self.sig.progress.emit), "")
        except ValidationError as e:
            self.sig.done.emit(None, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("task failed")
            self.sig.done.emit(None, f"Something went wrong: {e}")


def _path_row(placeholder: str, name: str) -> tuple[QHBoxLayout, QLineEdit, QPushButton]:
    row = QHBoxLayout()
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setAccessibleName(name)
    btn = QPushButton("Browse…")
    btn.setAccessibleName(f"Browse for {name}")
    row.addWidget(edit, 1)
    row.addWidget(btn)
    return row, edit, btn


def _thumb(img: Image.Image, size: int) -> QPixmap:
    flat = Image.new("RGBA", img.size, "#FFFFFF")
    flat.alpha_composite(img.convert("RGBA"))
    qi = QImage(flat.tobytes("raw", "RGBA"), flat.width, flat.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qi).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)


# ---------------------------------------------------------------------------------------------- batch
class BatchDialog(QDialog):
    def __init__(self, parent, state: AppState, prefs: AppPrefs):
        super().__init__(parent)
        self.state, self.prefs = state, prefs
        self.rows: list[BatchRow] = []
        self._cancel = threading.Event()
        self._busy = False
        self.setWindowTitle("Batch generate from CSV")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(muted("Create one QR code per CSV row, using the current design (colours, logo, frame, size and "
                            "format). Columns: content (URL or text), and optionally filename, title, caption, company."))
        r1, self.csv, b1 = _path_row("Choose a CSV file…", "CSV file")
        r2, self.out, b2 = _path_row("Choose an output folder…", "output folder")
        lay.addLayout(r1)
        t = QPushButton("Save example CSV…")
        t.setProperty("flat", True)
        t.setAccessibleName("Save an example CSV file")
        lay.addWidget(t, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(r2)
        f = form()
        self.kind = combo("Treat content as", [("Automatic (URL if it looks like one)", "auto"),
                                               ("Always a web URL", "url"), ("Always plain text", "text")])
        f.addRow("Content", self.kind)
        lay.addLayout(f)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setAccessibleName("Batch status")
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        btns = QHBoxLayout()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.hide()
        self.start = QPushButton("Generate")
        self.start.setProperty("primary", True)
        self.start.setEnabled(False)
        self.close_btn = QPushButton("Close")
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(self.close_btn)
        btns.addWidget(self.start)
        lay.addLayout(btns)

        b1.clicked.connect(self._pick_csv)
        b2.clicked.connect(self._pick_out)
        t.clicked.connect(self._save_template)
        self.csv.editingFinished.connect(lambda: self.load_csv(self.csv.text()))
        self.out.textChanged.connect(self._update)
        self.start.clicked.connect(self._go)
        self.close_btn.clicked.connect(self._close)
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.out.text())))
        self.out.setText(prefs.last_export_dir)

    # ---- inputs
    def _pick_csv(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Choose CSV file", self.prefs.last_project_dir or str(Path.home()),
                                           "CSV files (*.csv *.txt);;All files (*)")
        if p:
            self.csv.setText(p)
            self.load_csv(p)

    def _pick_out(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Output folder", self.out.text() or str(Path.home()))
        if p:
            self.out.setText(p)

    def _save_template(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Save example CSV", str(Path.home() / "qr-batch-example.csv"),
                                           "CSV files (*.csv)")
        if p:
            Path(p).write_text(TEMPLATE_CSV, encoding="utf-8-sig")

    def load_csv(self, path: str) -> None:
        self.rows = []
        if path.strip():
            try:
                self.rows = read_csv(path.strip())
            except ValidationError as e:
                self._say(str(e), error=True)
                self._update()
                return
            self._say(f"{len(self.rows)} row(s) found. First: {self.rows[0].value[:60]}")
        self._update()

    def _say(self, text: str, error: bool = False) -> None:
        self.info.setObjectName("error" if error else "muted")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)
        self.info.setText(text)

    def _update(self) -> None:
        self.start.setEnabled(bool(self.rows) and Path(self.out.text()).is_dir() and not self._busy)

    # ---- run
    def _go(self) -> None:
        self.state.flush()
        base = self.state.settings.clone()
        rows, out, kind = list(self.rows), self.out.text(), self.kind.currentData()
        try:                                  # fail fast on a broken design instead of on every row
            prepare(settings_for_row(base, rows[0], kind), strict=True)
        except ValidationError as e:
            QMessageBox.warning(self, "Design problem", str(e))
            return
        self.prefs.last_export_dir = out
        self._cancel.clear()
        self._busy = True
        self.start.setEnabled(False)
        self.open_btn.hide()
        self.bar.setRange(0, len(rows))
        self.bar.setValue(0)
        self.bar.show()
        self.close_btn.setText("Cancel")
        sig = _Sig()
        self._sig = sig

        def work(emit):
            return run_batch(base, rows, out, kind=kind, cancel=self._cancel,
                             progress=lambda i, n, r: emit(i, n))

        sig.progress.connect(lambda i, n: (self.bar.setValue(i), self._say(f"Creating {i} of {n}…")))
        sig.done.connect(self._finished)
        QThreadPool.globalInstance().start(_Task(work, sig))

    def _finished(self, report, error: str) -> None:
        self._busy = False
        self.close_btn.setText("Close")
        self.bar.hide()
        self._update()
        if error or report is None:
            self._say(error or "The batch failed.", error=True)
            return
        n_bad = len(report.failed)
        msg = f"Created {report.ok_count} file(s)" + (" (cancelled)" if report.cancelled else "") + \
              (f"; {n_bad} row(s) failed – see batch-report.csv in the folder." if n_bad else ".")
        self._say(msg, error=bool(n_bad))
        self.open_btn.show()
        self.result_report = report

    def _close(self) -> None:
        if self._busy:
            self._cancel.set()
        else:
            self.accept()

    def closeEvent(self, e) -> None:
        self._cancel.set()
        super().closeEvent(e)


# ---------------------------------------------------------------------------------------------- print sheet
class PrintSheetDialog(QDialog):
    def __init__(self, parent, state: AppState, prefs: AppPrefs):
        super().__init__(parent)
        self.state, self.prefs = state, prefs
        self.rows: list[BatchRow] = []
        self.setWindowTitle("Create print sheet")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(muted("Arrange QR codes on a printable A4 / Letter PDF with cut guides - handy for stickers, "
                            "table tents and labels."))
        self.r_same = QRadioButton("Repeat the current design")
        self.copies = spin("Number of copies", 1, 500, " copies")
        self.copies.setValue(12)
        self.r_csv = QRadioButton("One code per CSV row (uses the current design)")
        row, self.csv, b = _path_row("Choose a CSV file…", "CSV file")
        self.r_same.setChecked(True)
        lay.addWidget(self.r_same)
        lay.addWidget(self.copies)
        lay.addWidget(self.r_csv)
        lay.addLayout(row)
        f = form()
        self.page = combo("Paper size", [("A4 (210 × 297 mm)", "A4"), ("US Letter (8.5 × 11 in)", "Letter")])
        self.size = spin("Sticker size", 15, 150, " mm", 5)
        self.size.setValue(40)
        self.margin = spin("Page margin", 0, 40, " mm", 1)
        self.margin.setValue(10)
        self.gap = spin("Gap between stickers", 0, 40, " mm", 1)
        self.gap.setValue(6)
        self.guides = QCheckBox("Draw cut guides")
        self.guides.setChecked(True)
        f.addRow("Paper", self.page)
        f.addRow("Sticker size", self.size)
        f.addRow("Margin", self.margin)
        f.addRow("Gap", self.gap)
        f.addRow(self.guides)
        lay.addLayout(f)
        self.info = muted("")
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        bb = QHBoxLayout()
        self.close_btn = QPushButton("Close")
        self.make = QPushButton("Create PDF…")
        self.make.setProperty("primary", True)
        bb.addStretch(1)
        bb.addWidget(self.close_btn)
        bb.addWidget(self.make)
        lay.addLayout(bb)
        b.clicked.connect(self._pick_csv)
        self.csv.editingFinished.connect(lambda: self._load(self.csv.text()))
        for w in (self.page, self.size, self.margin, self.gap):
            (w.currentIndexChanged if hasattr(w, "currentIndexChanged") else w.valueChanged).connect(self._hint)
        self.make.clicked.connect(self._create)
        self.close_btn.clicked.connect(self.accept)
        self._hint()

    def _hint(self, *_a) -> None:
        from ..core.print_sheet import compute_layout
        try:
            lay = compute_layout(self.page.currentData(), self.size.value(), self.margin.value(), self.gap.value())
            self.info.setText(f"{lay.cols} × {lay.rows} = {lay.per_page} stickers per page.")
        except ValidationError as e:
            self.info.setText(str(e))

    def _pick_csv(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Choose CSV file", str(Path.home()), "CSV files (*.csv *.txt);;All files (*)")
        if p:
            self.csv.setText(p)
            self._load(p)

    def _load(self, path: str) -> None:
        try:
            self.rows = read_csv(path.strip()) if path.strip() else []
            if self.rows:
                self.r_csv.setChecked(True)
                self.info.setText(f"{len(self.rows)} row(s) found.")
        except ValidationError as e:
            self.rows = []
            self.info.setText(str(e))

    def build_items(self) -> list[ProjectSettings]:
        self.state.flush()
        base = self.state.settings.clone()
        if self.r_csv.isChecked():
            if not self.rows:
                raise ValidationError("Choose a CSV file with at least one row.")
            return [settings_for_row(base, r) for r in self.rows]
        return [base.clone() for _ in range(self.copies.value())]

    def _create(self) -> None:
        try:
            items = self.build_items()
            prepare(items[0], strict=True)
        except ValidationError as e:
            QMessageBox.warning(self, "Cannot create the sheet", str(e))
            return
        start = str(Path(self.prefs.last_export_dir or Path.home()) / "qr-print-sheet.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Save print sheet", start, "PDF document (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        args = dict(page=self.page.currentData(), cell_mm=self.size.value(), margin_mm=self.margin.value(),
                    gap_mm=self.gap.value(), guides=self.guides.isChecked())
        self.make.setEnabled(False)
        self.bar.setRange(0, len(items))
        self.bar.setValue(0)
        self.bar.show()
        sig = _Sig()
        self._sig = sig
        sig.progress.connect(lambda i, n: self.bar.setValue(i))
        sig.done.connect(lambda res, err, p=path: self._finished(res, err, p))
        QThreadPool.globalInstance().start(_Task(
            lambda emit: build_print_sheet(items, path, progress=lambda i, n: emit(i, n), **args), sig))

    def _finished(self, res, err: str, path: str) -> None:
        self.make.setEnabled(True)
        self.bar.hide()
        if err or res is None:
            QMessageBox.warning(self, "Print sheet failed", err or "The sheet could not be created.")
            return
        self.info.setText(f"Saved {Path(path).name} ({res[1]} page(s)). Print at 100% / 'Actual size'.")
        self.result_path = path
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ---------------------------------------------------------------------------------------------- thumbnails
class _ThumbSig(QObject):
    ready = Signal(int, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, idx: int, make_settings, sig: _ThumbSig, size: int):
        super().__init__()
        self.idx, self.make, self.sig, self.size = idx, make_settings, sig, size

    def run(self) -> None:
        try:
            s = self.make()
            s.logo.enabled = s.logo.enabled and bool(s.logo.path)
            prep = prepare(s, strict=False)
            im = render_raster(prep.scene, self.size * 2, ss=2).convert("RGBA")
            flat = Image.new("RGBA", im.size, "#FFFFFF")
            flat.alpha_composite(im)
            self.sig.ready.emit(self.idx, QImage(flat.tobytes("raw", "RGBA"), flat.width, flat.height,
                                                 QImage.Format.Format_RGBA8888).copy())
        except Exception:  # noqa: BLE001 - a thumbnail must never break the dialog
            log.debug("thumbnail failed", exc_info=True)


class TemplateGallery(QDialog):
    """Pick a built-in design. `selected` holds the chosen Template after accept()."""

    def __init__(self, parent, base: ProjectSettings):
        super().__init__(parent)
        self.setWindowTitle("Design templates")
        self.resize(640, 560)
        self.selected: Template | None = None
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(2)
        self._sig = _ThumbSig()
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Pick a starting look. Your content and logo are kept; you can fine-tune everything afterwards "
                            "and undo with Ctrl+Z."))
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(150, 150))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(8)
        self.list.setWordWrap(True)
        self.list.setGridSize(QSize(176, 206))
        self.list.setAccessibleName("Template list")
        lay.addWidget(self.list, 1)
        self.desc = muted("")
        lay.addWidget(self.desc)
        bb = QDialogButtonBox()
        self.apply_btn = bb.addButton("Use template", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_btn.setProperty("primary", True)
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        lay.addWidget(bb)
        sample = base.clone()
        sample.logo.enabled = False
        sample.content.type, sample.content.url = "url", "https://example.com"
        for i, t in enumerate(TEMPLATES):
            it = QListWidgetItem(t.name)
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setToolTip(t.description)
            self.list.addItem(it)
            self._pool.start(_ThumbJob(i, lambda t=t: apply_template(sample, t, with_sample=True), self._sig, 150))
        self._sig.ready.connect(self._thumb)
        self.list.currentRowChanged.connect(self._sel)
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        self.list.setCurrentRow(0)

    def _thumb(self, idx: int, img: QImage) -> None:
        if 0 <= idx < self.list.count():
            self.list.item(idx).setIcon(QIcon(QPixmap.fromImage(img).scaled(
                150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))

    def _sel(self, row: int) -> None:
        self.desc.setText(TEMPLATES[row].description if 0 <= row < len(TEMPLATES) else "")

    def _accept(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.selected = TEMPLATES[row]
            self.accept()

    def done(self, r: int) -> None:
        self._pool.clear()
        self._pool.waitForDone(2000)
        super().done(r)


class RecentProjectsDialog(QDialog):
    """Thumbnails of recently used projects. `chosen` holds the path after accept()."""

    def __init__(self, parent, prefs: AppPrefs):
        super().__init__(parent)
        self.setWindowTitle("Recent projects")
        self.resize(640, 480)
        self.chosen = ""
        self.prefs = prefs
        prefs.prune_recent()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(2)
        self._sig = _ThumbSig()
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(130, 130))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(8)
        self.list.setWordWrap(True)
        self.list.setGridSize(QSize(160, 190))
        self.list.setAccessibleName("Recent projects")
        lay.addWidget(self.list, 1)
        self.empty = muted("No recent projects yet. Save a project and it will appear here.")
        lay.addWidget(self.empty)
        bb = QDialogButtonBox()
        self.open_btn = bb.addButton("Open", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_btn.setProperty("primary", True)
        bb.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        lay.addWidget(bb)
        for i, p in enumerate(prefs.recent_projects):
            it = QListWidgetItem(Path(p).stem)
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.list.addItem(it)
            self._pool.start(_ThumbJob(i, lambda p=p: load_project(p).settings, self._sig, 130))
        self.empty.setVisible(self.list.count() == 0)
        self.open_btn.setEnabled(self.list.count() > 0)
        self._sig.ready.connect(self._thumb)
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _thumb(self, idx: int, img: QImage) -> None:
        if 0 <= idx < self.list.count():
            self.list.item(idx).setIcon(QIcon(QPixmap.fromImage(img).scaled(
                130, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))

    def _accept(self) -> None:
        it = self.list.currentItem()
        if it:
            self.chosen = it.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def done(self, r: int) -> None:
        self._pool.clear()
        self._pool.waitForDone(2000)
        super().done(r)
