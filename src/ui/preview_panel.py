"""Live preview. Renders the same scene that exports use, on a background thread (latest request wins)."""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ..core.export_manager import Prepared, prepare, render_image
from ..utils.validation import ValidationError
from .icons import icon
from .state import AppState
from .theme import tokens

ZOOMS = (0.25, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)


class _Signals(QObject):
    done = Signal(int, object, object, str)   # job id, QImage|None, Prepared|None, error


class _Job(QRunnable):
    def __init__(self, job_id: int, settings, width_px: int, sig: _Signals):
        super().__init__()
        self.job_id, self.settings, self.width_px, self.sig = job_id, settings, width_px, sig

    def run(self) -> None:
        try:
            prep: Prepared = prepare(self.settings, strict=False)
            im: Image.Image = render_image(prep, self.width_px)
            qi = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888).copy()
            self.sig.done.emit(self.job_id, qi, prep, "")
        except ValidationError as e:
            self.sig.done.emit(self.job_id, None, None, str(e))
        except Exception as e:  # noqa: BLE001 - never let a render error kill the UI
            self.sig.done.emit(self.job_id, None, None, f"The preview could not be drawn: {e}")


class _Canvas(QWidget):
    def __init__(self, mode: str):
        super().__init__()
        self.image: QImage | None = None
        self.target = QSize(400, 400)
        self.dim = False
        self.mode = mode
        self.setAccessibleName("QR code preview")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        t = tokens(self.mode)
        p.fillRect(self.rect(), QColor(t["canvas"]))
        if self.image is None:
            return
        w, h = self.target.width(), self.target.height()
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        r = QRectF(x, y, w, h)
        p.save()
        p.setClipRect(r)
        step = 12
        a, b = QColor(t["check_a"]), QColor(t["check_b"])
        for j in range(int(h // step) + 1):
            for i in range(int(w // step) + 1):
                p.fillRect(QRectF(x + i * step, y + j * step, step, step), a if (i + j) % 2 == 0 else b)
        p.restore()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(0.45 if self.dim else 1.0)
        p.drawImage(r, self.image)
        p.setOpacity(1.0)
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawRect(r)


class PreviewPanel(QWidget):
    rendered = Signal(object, str)    # Prepared | None, error text

    def __init__(self, state: AppState, mode: str = "light"):
        super().__init__()
        self.state, self.mode = state, mode
        self.zoom: float | None = None            # None = fit
        self._scene_size = (600.0, 600.0)
        self._job_id = 0
        self._pending = False
        self._busy = False
        self._sig = _Signals()
        self._sig.done.connect(self._on_done)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._start)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        bar = QHBoxLayout()
        self.b_out, self.b_fit, self.b_in = QToolButton(), QToolButton(), QToolButton()
        for b, n, tip in ((self.b_out, "Zoom out", "Zoom out (Ctrl+-)"), (self.b_fit, "Fit to window", "Fit to window (Ctrl+0)"),
                          (self.b_in, "Zoom in", "Zoom in (Ctrl++)")):
            b.setAccessibleName(n)
            b.setToolTip(tip)
        self.zoom_label = QLabel("Fit")
        self.zoom_label.setObjectName("muted")
        self.zoom_label.setAccessibleName("Zoom level")
        self.status = QLabel("")
        self.status.setObjectName("muted")
        bar.addWidget(self.b_out)
        bar.addWidget(self.b_fit)
        bar.addWidget(self.b_in)
        bar.addWidget(self.zoom_label)
        bar.addStretch(1)
        bar.addWidget(self.status)
        lay.addLayout(bar)

        self.canvas = _Canvas(mode)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.scroll, 1)
        self.empty = QLabel()
        self.empty.setObjectName("error")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setAccessibleName("Preview message")
        self.empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(self.empty)
        self.empty.hide()

        self.b_out.clicked.connect(lambda: self.step(-1))
        self.b_in.clicked.connect(lambda: self.step(1))
        self.b_fit.clicked.connect(self.fit)
        state.changed.connect(self.request)
        state.loaded.connect(self.request)
        self.set_theme(mode)

    # ------------------------------------------------------------------ public
    def set_theme(self, mode: str) -> None:
        self.mode = mode
        self.canvas.mode = mode
        c = tokens(mode)["icon"]
        self.b_out.setIcon(icon("zoom-out", c))
        self.b_in.setIcon(icon("zoom-in", c))
        self.b_fit.setIcon(icon("fit", c))
        self.canvas.update()

    def request(self) -> None:
        self._timer.start()

    def render_now(self) -> None:
        self._timer.stop()
        self._start()

    def fit(self) -> None:
        self.zoom = None
        self._layout_canvas()
        self.request()

    def step(self, d: int) -> None:
        cur = self._current_zoom()
        steps = list(ZOOMS)
        if d > 0:
            nxt = next((z for z in steps if z > cur + 0.01), steps[-1])
        else:
            nxt = next((z for z in reversed(steps) if z < cur - 0.01), steps[0])
        self.zoom = nxt
        self._layout_canvas()
        self.request()

    def current_image(self) -> QImage | None:
        return self.canvas.image

    # ------------------------------------------------------------------ internals
    def _fit_zoom(self) -> float:
        vw, vh = max(self.scroll.viewport().width() - 24, 100), max(self.scroll.viewport().height() - 24, 100)
        sw, sh = self._scene_size
        return max(0.1, min(vw / sw, vh / sh, 3.0))

    def _current_zoom(self) -> float:
        return self.zoom if self.zoom is not None else self._fit_zoom()

    def _layout_canvas(self) -> None:
        z = self._current_zoom()
        sw, sh = self._scene_size
        self.canvas.target = QSize(max(int(sw * z), 50), max(int(sh * z), 50))
        vp = self.scroll.viewport().size()
        self.canvas.resize(max(self.canvas.target.width() + 24, vp.width()), max(self.canvas.target.height() + 24, vp.height()))
        self.zoom_label.setText("Fit" if self.zoom is None else f"{int(z * 100)}%")
        self.canvas.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout_canvas()
        if self.zoom is None:
            self.request()

    def _start(self) -> None:
        if self._busy:
            self._pending = True
            return
        self._busy = True
        self._pending = False
        self._job_id += 1
        dpr = self.devicePixelRatioF() or 1.0
        z = self._current_zoom()
        width = int(max(300, min(2600, self._scene_size[0] * z * dpr)))
        self._pool.start(_Job(self._job_id, self.state.settings.clone(), width, self._sig))

    def _on_done(self, job_id: int, qimg, prep, error: str) -> None:
        self._busy = False
        if self._pending:
            self._start()
            return
        self.state.content_error = error
        self.state.last_prep = prep
        if qimg is not None and prep is not None:
            self.canvas.image = qimg
            self.canvas.dim = False
            self._scene_size = (prep.scene.width, prep.scene.height)
            self.empty.hide()
            self.status.setText("")
            self._layout_canvas()
        else:
            self.canvas.dim = True
            self.empty.setText(error)
            self.empty.show()
            self.canvas.update()
        self.rendered.emit(prep, error)
