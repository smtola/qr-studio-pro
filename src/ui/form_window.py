"""PDF to Form: make a normal PDF fillable, then fill forms by hand or from a CSV."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..convert.common import ConvertError
from ..convert import forms as F
from ..services.app_prefs import AppPrefs
from .convert_widgets import AsyncCall, FilesBox
from .convert_window import ToolsWindow
from .widgets import muted

SCALE = 1.15


class _StatusMixin:
    def _say(self, text: str, error: bool = False) -> None:
        self.info.setObjectName("error" if error else "muted")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)
        self.info.setText(text)


class MakeFillablePage(QWidget, _StatusMixin):
    COLS = ("Add", "Page", "Type", "Field name", "Label")

    def __init__(self, prefs: AppPrefs):
        super().__init__()
        self.prefs = prefs
        self.specs: list[F.FieldSpec] = []
        self.out_path: Path | None = None
        self._async = AsyncCall(self)
        self._pix: dict[int, QPixmap] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(10)
        h = QLabel("Make a PDF fillable")
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(muted("Open an ordinary PDF. TL Studio Pro finds the blanks (lines, boxes, check boxes), "
                            "you review them, and it adds real form fields you can type into in any PDF reader."))
        top = QHBoxLayout()
        self.files = FilesBox((".pdf",), "PDF file", multi=False, prefs=prefs)
        self.files.list.setMaximumHeight(70)
        self.files.list.setMinimumHeight(40)
        self.files.hint.hide()
        top.addWidget(self.files, 1)
        self.find_btn = QPushButton("Find fields")
        self.find_btn.setEnabled(False)
        top.addWidget(self.find_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        body = QHBoxLayout()
        self.preview = QLabel("Choose a PDF, then click Find fields.")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("muted")
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.preview)
        sc.setMinimumWidth(320)
        body.addWidget(sc, 2)
        right = QVBoxLayout()
        pr = QHBoxLayout()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setAccessibleName("Preview page")
        self.page_spin.setPrefix("Page ")
        pr.addWidget(self.page_spin)
        self.all_btn, self.none_btn = QPushButton("All"), QPushButton("None")
        pr.addWidget(self.all_btn)
        pr.addWidget(self.none_btn)
        pr.addStretch(1)
        right.addLayout(pr)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(list(self.COLS))
        self.table.setAccessibleName("Detected fields")
        self.table.verticalHeader().hide()
        hh = self.table.horizontalHeader()
        for c in (0, 1, 2):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        right.addWidget(self.table, 1)
        body.addLayout(right, 3)
        lay.addLayout(body, 1)

        orow = QHBoxLayout()
        self.out = QLineEdit()
        self.out.setPlaceholderText("Save next to the original file (or choose a folder…)")
        self.out.setAccessibleName("Output folder")
        ob = QPushButton("Browse…")
        orow.addWidget(self.out, 1)
        orow.addWidget(ob)
        lay.addLayout(orow)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        brow = QHBoxLayout()
        self.open_btn = QPushButton("Open PDF")
        self.open_btn.hide()
        self.make_btn = QPushButton("Create fillable PDF")
        self.make_btn.setProperty("primary", True)
        self.make_btn.setEnabled(False)
        brow.addWidget(self.open_btn)
        brow.addStretch(1)
        brow.addWidget(self.make_btn)
        lay.addLayout(brow)

        self.files.changed.connect(self._files_changed)
        self.find_btn.clicked.connect(self.find)
        self.make_btn.clicked.connect(self.create)
        self.page_spin.valueChanged.connect(self._draw)
        self.table.itemChanged.connect(self._edited)
        self.table.itemSelectionChanged.connect(self._draw)
        self.all_btn.clicked.connect(lambda: self._set_all(True))
        self.none_btn.clicked.connect(lambda: self._set_all(False))
        ob.clicked.connect(self._pick_out)
        self.open_btn.clicked.connect(lambda: self.out_path and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.out_path))))

    # ---- helpers
    def _pdf(self) -> Path | None:
        f = self.files.files()
        return f[0] if f else None

    def _files_changed(self) -> None:
        self.specs, self._pix = [], {}
        self.table.setRowCount(0)
        self.make_btn.setEnabled(False)
        self.find_btn.setEnabled(self._pdf() is not None)
        self.open_btn.hide()
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Click Find fields." if self._pdf() else "Choose a PDF, then click Find fields.")
        self._say("")

    def _pick_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out.text() or str(Path.home()))
        if d:
            self.out.setText(d)

    # ---- detect
    def find(self) -> None:
        pdf = self._pdf()
        if pdf is None or self._async.busy:
            return
        self._say("Looking for blanks…")
        self.find_btn.setEnabled(False)
        self._async.start(lambda: F.detect_fields(pdf), self._found)

    def _found(self, specs, err: str) -> None:
        self.find_btn.setEnabled(self._pdf() is not None)
        if err:
            self._say(err, error=True)
            return
        self.specs = specs
        self._fill_table()
        pages = max((s.page for s in specs), default=0) + 1
        self.page_spin.setMaximum(max(pages, self._page_count()))
        self._draw()
        n_cb = sum(s.kind == "checkbox" for s in specs)
        self._say(f"{len(specs)} field(s) found ({n_cb} check box(es)). Untick any that are wrong and rename them if you like."
                  if specs else "No blanks were found. This PDF may already be a form, or use a different layout.",
                  error=not specs)
        self.make_btn.setEnabled(bool(specs))

    def _page_count(self) -> int:
        try:
            import pypdfium2 as pdfium
            return len(pdfium.PdfDocument(str(self._pdf())))
        except Exception:  # noqa: BLE001
            return 1

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.specs))
        for r, s in enumerate(self.specs):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked if s.enabled else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, chk)
            for c, txt in ((1, str(s.page + 1)), (2, "Check box" if s.kind == "checkbox" else "Text")):
                it = QTableWidgetItem(txt)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(r, c, it)
            self.table.setItem(r, 3, QTableWidgetItem(s.name))
            self.table.setItem(r, 4, QTableWidgetItem(s.label))
        self.table.blockSignals(False)

    def _edited(self, it: QTableWidgetItem) -> None:
        r = it.row()
        if not 0 <= r < len(self.specs):
            return
        s = self.specs[r]
        if it.column() == 0:
            s.enabled = it.checkState() == Qt.CheckState.Checked
        elif it.column() == 3:
            s.name = it.text().strip() or s.name
        elif it.column() == 4:
            s.label = it.text()
        self.make_btn.setEnabled(any(x.enabled for x in self.specs))
        self._draw()

    def _set_all(self, on: bool) -> None:
        self.table.blockSignals(True)
        for r, s in enumerate(self.specs):
            s.enabled = on
            self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.make_btn.setEnabled(on and bool(self.specs))
        self._draw()

    # ---- preview
    def _page_pixmap(self, idx: int) -> QPixmap | None:
        if idx in self._pix:
            return self._pix[idx]
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(self._pdf()))
            im = doc[idx].render(scale=SCALE).to_pil().convert("RGBA")
        except Exception:  # noqa: BLE001
            return None
        from PySide6.QtGui import QImage
        qi = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888).copy()
        self._pix[idx] = QPixmap.fromImage(qi)
        return self._pix[idx]

    def _draw(self) -> None:
        if not self.specs or self._pdf() is None:
            return
        idx = self.page_spin.value() - 1
        base = self._page_pixmap(idx)
        if base is None:
            self.preview.setText("The page could not be previewed.")
            return
        pm = QPixmap(base)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sel = {i.row() for i in self.table.selectedItems()}
        for r, s in enumerate(self.specs):
            if s.page != idx:
                continue
            col = QColor("#4F46E5") if s.enabled else QColor("#999999")
            if r in sel:
                col = QColor("#E11D48")
            fill = QColor(col)
            fill.setAlpha(60)
            p.setPen(QPen(col, 1.6))
            p.setBrush(fill)
            p.drawRect(QRectF(s.x0 * SCALE, s.top * SCALE, (s.x1 - s.x0) * SCALE, (s.bottom - s.top) * SCALE))
        p.end()
        self.preview.setPixmap(pm)

    # ---- create
    def create(self) -> None:
        pdf = self._pdf()
        if pdf is None or self._async.busy:
            return
        out_dir = Path(self.out.text().strip()) if self.out.text().strip() else pdf.parent
        specs = list(self.specs)
        self.make_btn.setEnabled(False)
        self._say("Creating…")
        self._async.start(lambda: F.make_fillable(pdf, out_dir, specs), self._created)

    def _created(self, out, err: str) -> None:
        self.make_btn.setEnabled(True)
        if err:
            self._say(err, error=True)
            return
        self.out_path = Path(out)
        self._say(f"Created {self.out_path.name}. Open it in any PDF reader to fill it in, or use the 'Fill a form' tool.")
        self.open_btn.show()


class FillPage(QWidget, _StatusMixin):
    def __init__(self, prefs: AppPrefs):
        super().__init__()
        self.prefs = prefs
        self.editors: dict[str, QWidget] = {}
        self._async = AsyncCall(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(10)
        h = QLabel("Fill a form")
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(muted("Open a fillable PDF, type the values and save a filled copy. For many people at once, "
                            "use a CSV file (one row per form)."))
        self.files = FilesBox((".pdf",), "fillable PDF", multi=False, prefs=prefs)
        self.files.list.setMaximumHeight(70)
        self.files.list.setMinimumHeight(40)
        self.files.hint.hide()
        lay.addWidget(self.files)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.holder = QWidget()
        self.form_lay = QVBoxLayout(self.holder)
        self.form_lay.setSpacing(8)
        self.form_lay.addStretch(1)
        self.scroll.setWidget(self.holder)
        lay.addWidget(self.scroll, 1)
        self.flatten = QCheckBox("Flatten (make the values permanent text, no longer editable)")
        lay.addWidget(self.flatten)
        row = QHBoxLayout()
        self.tpl_btn = QPushButton("Save CSV template…")
        self.csv_btn = QPushButton("Fill from CSV…")
        row.addWidget(self.tpl_btn)
        row.addWidget(self.csv_btn)
        row.addStretch(1)
        lay.addLayout(row)
        orow = QHBoxLayout()
        self.out = QLineEdit()
        self.out.setPlaceholderText("Save next to the original file (or choose a folder…)")
        self.out.setAccessibleName("Output folder")
        ob = QPushButton("Browse…")
        orow.addWidget(self.out, 1)
        orow.addWidget(ob)
        lay.addLayout(orow)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        brow = QHBoxLayout()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.hide()
        self.save_btn = QPushButton("Save filled PDF")
        self.save_btn.setProperty("primary", True)
        self.save_btn.setEnabled(False)
        brow.addWidget(self.open_btn)
        brow.addStretch(1)
        brow.addWidget(self.save_btn)
        lay.addLayout(brow)
        self.results: list[Path] = []
        self.files.changed.connect(self.load_fields)
        self.save_btn.clicked.connect(self.save)
        self.tpl_btn.clicked.connect(self.save_template)
        self.csv_btn.clicked.connect(self.fill_csv)
        ob.clicked.connect(self._pick_out)
        self.open_btn.clicked.connect(lambda: self.results and QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.results[0].parent))))
        self.tpl_btn.setEnabled(False)
        self.csv_btn.setEnabled(False)

    def _pdf(self) -> Path | None:
        f = self.files.files()
        return f[0] if f else None

    def _pick_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out.text() or str(Path.home()))
        if d:
            self.out.setText(d)

    def _out_dir(self) -> Path:
        t = self.out.text().strip()
        return Path(t) if t else self._pdf().parent

    def load_fields(self) -> None:
        for w in self.editors.values():
            w.setParent(None)
        while self.form_lay.count() > 1:
            it = self.form_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.editors = {}
        self.open_btn.hide()
        pdf = self._pdf()
        self.save_btn.setEnabled(False)
        self.tpl_btn.setEnabled(False)
        self.csv_btn.setEnabled(False)
        if pdf is None:
            self._say("")
            return
        try:
            fields = F.list_form_fields(pdf)
        except ConvertError as e:
            self._say(str(e), error=True)
            return
        shown = [f for f in fields if f.kind in ("text", "checkbox", "choice")]
        if not shown:
            self._say("This PDF has no fillable fields. Use 'Make a PDF fillable' first.", error=True)
            return
        for f in shown:
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(f.label or f.name)
            lab.setMinimumWidth(170)
            lab.setToolTip(f.name)
            hl.addWidget(lab)
            if f.kind == "checkbox":
                ed: QWidget = QCheckBox()
                ed.setChecked(f.value.lower() in ("yes", "on", "true", "1"))
            elif f.kind == "choice" and f.options:
                ed = QComboBox()
                ed.addItems([""] + f.options)
                ed.setCurrentText(f.value)
            else:
                ed = QLineEdit(f.value)
            ed.setAccessibleName(f.label or f.name)
            hl.addWidget(ed, 1)
            self.form_lay.insertWidget(self.form_lay.count() - 1, row)
            self.editors[f.name] = ed
        self.save_btn.setEnabled(True)
        self.tpl_btn.setEnabled(True)
        self.csv_btn.setEnabled(True)
        self._say(f"{len(shown)} field(s). Fill them in and save.")

    def values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, ed in self.editors.items():
            if isinstance(ed, QCheckBox):
                out[name] = "yes" if ed.isChecked() else "no"
            elif isinstance(ed, QComboBox):
                if ed.currentText():
                    out[name] = ed.currentText()
            elif ed.text():
                out[name] = ed.text()
        return out

    def save(self) -> None:
        pdf = self._pdf()
        if pdf is None or self._async.busy:
            return
        vals, flat, out_dir = self.values(), self.flatten.isChecked(), self._out_dir()
        self._say("Saving…")
        self._async.start(lambda: [F.fill_form(pdf, out_dir, vals, flatten=flat)], self._saved)

    def save_template(self) -> None:
        pdf = self._pdf()
        if pdf is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save CSV template", str(pdf.with_suffix(".csv")), "CSV files (*.csv)")
        if p:
            try:
                F.fields_csv_template(pdf, p)
                self._say(f"Saved {Path(p).name}. Fill one row per form, then use 'Fill from CSV…'.")
            except ConvertError as e:
                self._say(str(e), error=True)

    def fill_csv(self) -> None:
        pdf = self._pdf()
        if pdf is None or self._async.busy:
            return
        p, _ = QFileDialog.getOpenFileName(self, "Choose CSV", str(Path.home()), "CSV files (*.csv *.txt)")
        if not p:
            return
        flat, out_dir = self.flatten.isChecked(), self._out_dir()
        first = next(iter(self.editors), "")
        self._say("Filling forms…")
        self._async.start(lambda: F.fill_from_csv(pdf, p, out_dir, flatten=flat, name_column=first), self._saved)

    def _saved(self, outs, err: str) -> None:
        if err:
            self._say(err, error=True)
            return
        self.results = [Path(o) for o in outs]
        self._say(f"Created {len(self.results)} file(s): " + ", ".join(p.name for p in self.results[:3])
                  + (" …" if len(self.results) > 3 else ""))
        self.open_btn.show()


def pdf_to_form(prefs: AppPrefs) -> ToolsWindow:
    w = ToolsWindow("PDF to Form", [("Make a PDF fillable", MakeFillablePage(prefs)), ("Fill a form", FillPage(prefs))])
    w.resize(1120, 760)
    return w
