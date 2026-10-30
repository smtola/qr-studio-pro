"""Live preview.

Rendering is two-phase so dragging a slider never feels heavy:
  * DRAFT  - small, 2x supersampled, started ~25 ms after the last edit  (tens of ms)
  * FINAL  - display-sized and sharp, started when you pause (~240 ms)
Both run on a background thread from the same scene the exports use (preview == export). Only the latest edit is
rendered; older requests are dropped.
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ..core.export_manager import Prepared, prepare
from ..core.render_raster import render_raster
from ..core.scan_check import FAIL, OK, ScanResult, available as scan_available, check_scan
from ..utils.validation import ValidationError
from ..i18n import tr
from .icons import icon
from .state import AppState
from .theme import tokens

ZOOMS = (0.25, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
DRAFT_MS, FINAL_MS = 25, 240


class _Signals(QObject):
    done = Signal(int, int, object, object, str, str, object)   # job id, version, QImage|None, Prepared|None, error, kind, ScanResult|None


class _Job(QRunnable):
    def __init__(self, job_id: int, version: int, settings, width_px: int, ss: int, kind: str, sig: _Signals):
        super().__init__()
        self.a = (job_id, version, settings, width_px, ss, kind)
        self.sig = sig

    def _emit(self, *args) -> None:
        try:
            self.sig.done.emit(*args)
        except RuntimeError:        # window closed while the job was running
            pass

    def run(self) -> None:
        job_id, version, settings, width_px, ss, kind = self.a
        try:
            prep: Prepared = prepare(settings, strict=False)
            im: Image.Image = render_raster(prep.scene, width_px, ss=ss)
            qi = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888).copy()
            scan = check_scan(prep, im) if kind == "final" and scan_available() else None
        except ValidationError as e:
            self._emit(job_id, version, None, None, str(e), kind, None)
        except Exception as e:  # noqa: BLE001 - never let a render error kill the UI
            self._emit(job_id, version, None, None, f"The preview could not be drawn: {e}", kind, None)
        else:
            self._emit(job_id, version, qi, prep, "", kind, scan)


def _tile(kind: str, t: dict, dpr: float) -> QPixmap:
    if kind == "check":
        size = 16
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        h = size / 2
        p.fillRect(QRectF(0, 0, size, size), QColor(t["check_a"]))
        p.fillRect(QRectF(0, 0, h, h), QColor(t["check_b"]))
        p.fillRect(QRectF(h, h, h, h), QColor(t["check_b"]))
    else:
        size = 22
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(t["muted"])
        c.setAlpha(46)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(size / 2 - 1, size / 2 - 1, 2, 2))
    p.end()
    return pm


class _Canvas(QWidget):
    """Paints a soft-shadowed artwork on a dotted canvas. Tiles and the pixmap are cached; painting is a few calls."""

    def __init__(self, mode: str):
        super().__init__()
        self.pixmap: QPixmap | None = None
        self.target = QSize(400, 400)
        self.dim = False
        self.set_mode(mode)
        self.setAccessibleName("QR code preview")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        t = tokens(mode)
        dpr = self.devicePixelRatioF() or 1.0
        self._t = t
        self._check = QBrush(_tile("check", t, dpr))
        self._dots = QBrush(_tile("dots", t, dpr))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._t["canvas"]))
        p.fillRect(self.rect(), self._dots)
        if self.pixmap is None:
            return
        w, h = self.target.width(), self.target.height()
        r = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        dark = self.mode == "dark"
        for i in range(1, 9):                      # soft shadow: stacked translucent rounded rects
            c = QColor(0, 0, 0, (10 if dark else 5) + (0 if i > 4 else 2))
            p.setBrush(c)
            grow = i * 3.2
            p.drawRoundedRect(r.adjusted(-grow, -grow * 0.55 + 7, grow, grow * 1.1 + 7), 10 + grow, 10 + grow)
        p.fillRect(r, self._check)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(0.4 if self.dim else 1.0)
        p.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))


class PreviewPanel(QWidget):
    rendered = Signal(object, str)    # Prepared | None, error text

    def __init__(self, state: AppState, mode: str = "light"):
        super().__init__()
        self.state, self.mode = state, mode
        self.zoom: float | None = None            # None = fit
        self._scene_size = (600.0, 600.0)
        self._image: QImage | None = None
        self._job_id = 0
        self._version = 0                          # bumped by every edit
        self._emitted_version = -1
        self._busy = False
        self._pending: str | None = None
        self._sig = _Signals()
        self._sig.done.connect(self._on_done)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(DRAFT_MS)
        self._draft_timer.timeout.connect(lambda: self._kick("draft"))
        self._final_timer = QTimer(self)
        self._final_timer.setSingleShot(True)
        self._final_timer.setInterval(FINAL_MS)
        self._final_timer.timeout.connect(lambda: self._kick("final"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 0, 4, 0)
        bar.setSpacing(2)
        self.b_out, self.b_in, self.b_fit = QToolButton(), QToolButton(), QToolButton()
        for b, n, tip in ((self.b_out, "Zoom out", "Zoom out (Ctrl+-)"), (self.b_in, "Zoom in", "Zoom in (Ctrl++)"),
                          (self.b_fit, "Fit to window", "Fit to window (Ctrl+0)")):
            b.setAccessibleName(n)
            b.setToolTip(tip)
            b.setObjectName("iconButton")
            b.setAutoRaise(True)
        self.zoom_label = QLabel("Fit")
        self.zoom_label.setObjectName("pill")
        self.zoom_label.setAccessibleName("Zoom level")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_badge = QLabel()
        self.scan_badge.setObjectName("scanBadge")
        self.scan_badge.setAccessibleName("Scan check result")
        self.scan_badge.hide()
        title = QLabel("Live preview")
        title.setObjectName("h2")
        bar.addWidget(title)
        bar.addSpacing(8)
        bar.addWidget(self.scan_badge)
        bar.addStretch(1)
        for w in (self.b_out, self.zoom_label, self.b_in, self.b_fit):
            bar.addWidget(w)
        lay.addLayout(bar)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(12, 9, 12, 9)
        self.banner_icon = QLabel()
        self.banner_icon.setFixedSize(20, 20)
        self.banner_text = QLabel()
        self.banner_text.setWordWrap(True)
        self.banner_text.setAccessibleName("Preview message")
        bl.addWidget(self.banner_icon)
        bl.addWidget(self.banner_text, 1)
        self.banner.hide()
        lay.addWidget(self.banner)

        self.canvas = _Canvas(mode)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("canvasScroll")
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.scroll, 1)

        self.b_out.clicked.connect(lambda: self.step(-1))
        self.b_in.clicked.connect(lambda: self.step(1))
        self.b_fit.clicked.connect(self.fit)
        state.changed.connect(self.request)
        state.loaded.connect(self.request)
        self.last_scan: ScanResult | None = None
        self.set_theme(mode)

    # ------------------------------------------------------------------ public
    def set_theme(self, mode: str) -> None:
        self.mode = mode
        t = tokens(mode)
        self.canvas.set_mode(mode)
        for b, n in ((self.b_out, "zoom-out"), (self.b_in, "zoom-in"), (self.b_fit, "fit")):
            b.setIcon(icon(n, t["icon"]))
        self._banner_icon_name = "error"
        self._set_banner(self.banner_text.text())

    def request(self) -> None:
        self._version += 1
        self._draft_timer.start()
        self._final_timer.start()

    def render_now(self) -> None:
        self._version += 1
        self._draft_timer.stop()
        self._final_timer.stop()
        self._kick("final")

    def fit(self) -> None:
        self.zoom = None
        self._layout_canvas()
        self.request()

    def step(self, d: int) -> None:
        cur = self._current_zoom()
        if d > 0:
            nxt = next((z for z in ZOOMS if z > cur + 0.01), ZOOMS[-1])
        else:
            nxt = next((z for z in reversed(ZOOMS) if z < cur - 0.01), ZOOMS[0])
        self.zoom = nxt
        self._layout_canvas()
        self.request()

    def current_image(self) -> QImage | None:
        return self._image

    # ------------------------------------------------------------------ layout
    def _fit_zoom(self) -> float:
        vw, vh = max(self.scroll.viewport().width() - 56, 100), max(self.scroll.viewport().height() - 56, 100)
        sw, sh = self._scene_size
        return max(0.1, min(vw / sw, vh / sh, 3.0))

    def _current_zoom(self) -> float:
        return self.zoom if self.zoom is not None else self._fit_zoom()

    def _layout_canvas(self) -> None:
        z = self._current_zoom()
        sw, sh = self._scene_size
        self.canvas.target = QSize(max(int(sw * z), 50), max(int(sh * z), 50))
        vp = self.scroll.viewport().size()
        self.canvas.resize(max(self.canvas.target.width() + 56, vp.width()), max(self.canvas.target.height() + 56, vp.height()))
        self.zoom_label.setText("Fit" if self.zoom is None else f"{int(z * 100)}%")
        self.canvas.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout_canvas()
        if self.zoom is None:
            self.request()

    # ------------------------------------------------------------------ rendering
    def _kick(self, kind: str) -> None:
        if self._busy:
            if kind == "final" or self._pending is None:
                self._pending = kind
            return
        self._start(kind)

    def _start(self, kind: str) -> None:
        self._busy = True
        self._job_id += 1
        dpr = self.devicePixelRatioF() or 1.0
        display_px = self._scene_size[0] * self._current_zoom() * dpr
        if kind == "draft":
            width, ss = int(max(240, min(520, display_px))), 2
        else:
            width = int(max(300, min(1500, display_px)))
            ss = 3 if width <= 900 else 2
        self._pool.start(_Job(self._job_id, self._version, self.state.settings.clone(), width, ss, kind, self._sig))

    def _on_done(self, _job_id: int, version: int, qimg, prep, error: str, kind: str, scan=None) -> None:
        self._busy = False
        self.state.content_error = error
        if qimg is not None and prep is not None:
            self.state.last_prep = prep
            self._image = qimg
            self.canvas.pixmap = QPixmap.fromImage(qimg)
            self.canvas.dim = False
            self._scene_size = (prep.scene.width, prep.scene.height)
            self._set_banner("")
            self._layout_canvas()
        else:
            self.canvas.dim = True
            self._set_banner(error)
            self.canvas.update()
        if error:
            self._set_scan(None)
        elif scan is not None and version == self._version:
            self._set_scan(scan)
        elif kind == "draft" and self.scan_badge.property("status") not in (None, "busy"):
            self._set_scan("busy")
        if version != self._emitted_version or error:
            self._emitted_version = version
            self.rendered.emit(prep, error)
        if self._pending:
            kind_next, self._pending = self._pending, None
            self._start(kind_next)
        elif kind == "draft" and not self._final_timer.isActive() and version == self._version:
            self._start("final")

    def _set_scan(self, scan) -> None:
        """Show the self-test badge. `scan` is a ScanResult, "busy", or None (hide)."""
        b = self.scan_badge
        if scan is None or not scan_available():
            status, text, tip = "", "", ""
        elif scan == "busy":
            status, text, tip = "busy", tr("Checking scan…"), ""
        elif scan.status == OK:
            status, text, tip = "ok", tr("✓ Scans OK"), scan.message
        elif scan.status == FAIL:
            status, text, tip = "fail", tr("⚠ May not scan"), scan.message
        else:
            status, text, tip = "", "", ""
        b.setProperty("status", status or None)
        b.setText(text)
        b.setToolTip(tip)
        b.setVisible(bool(text))
        b.style().unpolish(b)
        b.style().polish(b)
        self.last_scan = scan if isinstance(scan, ScanResult) else None

    def _set_banner(self, text: str) -> None:
        self.banner_text.setText(text)
        self.banner.setVisible(bool(text))
        if text:
            self.banner_icon.setPixmap(icon("alert", tokens(self.mode)["err"], 20).pixmap(20, 20))
