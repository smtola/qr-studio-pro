from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..core.logo_composer import LogoError, load_logo, load_logo_cached, sha256_file
from ..services.app_prefs import AppPrefs
from .icons import icon
from .state import AppState
from .widgets import ColorField, SliderRow, combo, form, muted, set_combo, set_value

BACKINGS = [("Transparent (no backing)", "none"), ("White padding / square", "square"),
            ("Rounded square", "rounded"), ("Circle", "circle")]
IMAGE_FILTER = "Logo images (*.png *.jpg *.jpeg *.svg);;PNG (*.png);;JPEG (*.jpg *.jpeg);;SVG (*.svg)"


class LogoPanel(QWidget):
    def __init__(self, state: AppState, prefs: AppPrefs):
        super().__init__()
        self.state, self.prefs = state, prefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        row = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(64, 64)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setObjectName("card")
        self.thumb.setAccessibleName("Logo thumbnail")
        col = QVBoxLayout()
        self.upload = QPushButton("Upload Center Logo")
        self.upload.setProperty("primary", True)
        self.upload.setAccessibleName("Upload Center Logo")
        self.upload.setToolTip("Choose a PNG, JPG or SVG logo to place in the centre of the QR code")
        self.remove = QPushButton("Remove logo")
        self.remove.setAccessibleName("Remove logo")
        col.addWidget(self.upload)
        col.addWidget(self.remove)
        row.addWidget(self.thumb)
        row.addLayout(col, 1)
        lay.addLayout(row)
        self.file_label = muted("No logo selected. PNG (transparent OK), JPG or SVG.")
        lay.addWidget(self.file_label)
        self.relocate = QPushButton("Locate missing logo…")
        self.relocate.setProperty("flat", True)
        self.relocate.hide()
        lay.addWidget(self.relocate)

        self.enabled = QCheckBox("Show logo in the centre")
        lay.addWidget(self.enabled)
        f = form()
        self.size = SliderRow("Logo size", 10, 25, 20, "%")
        self.backing = combo("Logo backing shape", BACKINGS)
        self.backing_color = ColorField("Logo backing colour", "#FFFFFF")
        self.padding = SliderRow("Logo padding", 0, 30, 10, "%")
        f.addRow("Size", self.size)
        f.addRow("Backing", self.backing)
        f.addRow("Backing colour", self.backing_color)
        f.addRow("Padding", self.padding)
        lay.addLayout(f)
        self.auto_h = QCheckBox("Use error correction level H with a logo")
        lay.addWidget(self.auto_h)
        self.note = muted("The logo is a visual overlay only – it is never part of the encoded data.")
        lay.addWidget(self.note)

        self.upload.clicked.connect(self.choose_logo)
        self.relocate.clicked.connect(self.choose_logo)
        self.remove.clicked.connect(self.remove_logo)
        self.enabled.toggled.connect(lambda v: self._set("enabled", v))
        self.size.valueChanged.connect(lambda v: self._set("size_pct", float(v)))
        self.padding.valueChanged.connect(lambda v: self._set("padding_pct", float(v)))
        self.backing.currentIndexChanged.connect(lambda: self._set("backing", self.backing.currentData()))
        self.backing_color.changed.connect(lambda c: self._set("backing_color", c))
        self.auto_h.toggled.connect(lambda v: self._set("auto_high_ecc", v))
        state.loaded.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v) -> None:
        setattr(self.state.settings.logo, attr, v)
        self.state.edit()

    # ------------------------------------------------------------------ actions
    def choose_logo(self) -> None:
        start = self.prefs.last_logo_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Upload Center Logo", start, IMAGE_FILTER)
        if path:
            self.set_logo_file(path)

    def set_logo_file(self, path: str) -> bool:
        try:
            info = load_logo(path)
        except LogoError as e:
            QMessageBox.warning(self, "Logo not usable", str(e))
            return False
        lg = self.state.settings.logo
        lg.path, lg.sha256, lg.relative_path, lg.enabled = str(Path(path).resolve()), info.sha256, "", True
        self.prefs.last_logo_dir = str(Path(path).parent)
        self.state.edit(refresh=True)
        return True

    def remove_logo(self) -> None:
        lg = self.state.settings.logo
        lg.path = lg.sha256 = lg.relative_path = ""
        self.state.edit(refresh=True)

    # ------------------------------------------------------------------ view
    def refresh(self) -> None:
        lg = self.state.settings.logo
        set_value(self.enabled, lg.enabled)
        set_value(self.size.slider, int(lg.size_pct))
        self.size.set_value(int(lg.size_pct))
        self.padding.set_value(int(lg.padding_pct))
        set_combo(self.backing, lg.backing)
        self.backing_color.set_value(lg.backing_color)
        set_value(self.auto_h, lg.auto_high_ecc)
        has = bool(lg.path)
        self.remove.setEnabled(has)
        self.upload.setText("Upload Center Logo")
        self.relocate.hide()
        self.thumb.clear()
        if not has:
            self.file_label.setText("No logo selected. PNG (transparent OK), JPG or SVG.")
            return
        name = Path(lg.path).name
        try:
            info = load_logo_cached(lg.path)
            im = info.image.copy()
            im.thumbnail((56, 56))
            q = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888).copy()
            self.thumb.setPixmap(QPixmap.fromImage(q))
            self.file_label.setText(f"{name} · {info.image.width}×{info.image.height}px"
                                    f"{' · transparent' if info.has_alpha else ''}  (click “Upload Center Logo” to replace)")
        except LogoError as e:
            self.file_label.setText(f"⚠ {e}")
            self.relocate.show()
