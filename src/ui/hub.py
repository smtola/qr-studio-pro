"""TL Studio Pro home screen: a grid of tool tiles that open each tool in its own window."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QGridLayout, QLabel, QMainWindow, QMessageBox,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import i18n
from ..services.app_prefs import AppPrefs
from ..utils.paths import resource_path
from ..version import APP_NAME, VERSION
from .icons import icon
from .theme import apply_theme, resolve_mode, tokens
from .update_dialog import UpdateController

TILE = 168


@dataclass(frozen=True)
class ToolDef:
    key: str
    title: str
    blurb: str
    icon: str
    hue: tuple[str, str]            # gradient top / bottom
    available: bool = True


TOOLS: tuple[ToolDef, ...] = (
    ToolDef("qr", "QR STUDIO PRO", "Design QR codes with logo, colours and frames", "qr", ("#3E6A93", "#2F5578")),
    ToolDef("download", "Download Image & Video", "Save pictures and videos you have the right to keep", "download",
            ("#3E6A93", "#2F5578"), available=False),
    ToolDef("convert", "Convert Studio", "Excel, Word and PDF conversions, merge and split", "convert", ("#3E6A93", "#2F5578")),
    ToolDef("media", "Convert Media", "Images, GIFs and videos: convert, resize, trim", "film", ("#3E6A93", "#2F5578")),
    ToolDef("form", "PDF to Form", "Turn a PDF into a fillable form and fill it", "form", ("#3E6A93", "#2F5578")),
    ToolDef("ai", "AI Agent", "Ask in plain words and let the agent run the tools", "sparkles", ("#3E6A93", "#2F5578"), available=False),
)


class Tile(QAbstractButton):
    """Rounded gradient square with a glow at the bottom, a white icon and a caption below (like the app icons)."""

    def __init__(self, tool: ToolDef, prefs: AppPrefs, soon: bool = False):
        super().__init__()
        self.tool, self.prefs, self.soon = tool, prefs, soon
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(tool.title + (" (coming soon)" if soon else ""))
        self.setToolTip(tool.blurb)
        self.setFixedSize(TILE + 36, TILE + 78)
        self._hover = False
        self._icons: dict[str, QIcon] = {}

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.click()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _e) -> None:
        t = tokens(self.prefs.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        lift = 4 if self._hover else 0
        r = QRectF(18, 12 - lift, TILE, TILE)
        # soft shadow
        for i, a in enumerate((14, 10, 6)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(r.adjusted(-i, 6 + i * 2 + lift, i, 6 + i * 2 + lift), 38 + i, 38 + i)
        path = QPainterPath()
        path.addRoundedRect(r, 38, 38)
        p.save()
        p.setClipPath(path)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(self.tool.hue[0]))
        g.setColorAt(1, QColor(self.tool.hue[1]))
        p.fillPath(path, QBrush(g))
        glow = QRadialGradient(QPointF(r.center().x(), r.bottom() + 6), TILE * 0.62)
        glow.setColorAt(0, QColor(190, 220, 235, 235))
        glow.setColorAt(0.55, QColor(120, 165, 195, 90))
        glow.setColorAt(1, QColor(62, 106, 147, 0))
        p.fillPath(path, QBrush(glow))
        p.restore()
        if self.hasFocus():
            p.setPen(QPen(QColor(t["focus"]), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 41, 41)
        ic = icon(self.tool.icon, "#FFFFFF", 58)
        pm = ic.pixmap(58, 58)
        p.setOpacity(0.55 if self.soon else 1.0)
        p.drawPixmap(int(r.center().x() - 29), int(r.top() + TILE * 0.30), pm)
        p.setOpacity(1.0)
        if self.soon:
            f = QFont(self.font())
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            txt = i18n.tr("Coming soon")
            w = p.fontMetrics().horizontalAdvance(txt) + 18
            pill = QRectF(r.center().x() - w / 2, r.top() + 14, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 215))
            p.drawRoundedRect(pill, 10, 10)
            p.setPen(QColor("#2F5578"))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, txt)
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(QColor(t["text"] if not self.soon else t["muted"]))
        label = QRectF(0, r.bottom() + 12, self.width(), 54)
        p.drawText(label, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   i18n.tr(self.tool.title))


class HubWindow(QMainWindow):
    def __init__(self, prefs: AppPrefs | None = None) -> None:
        super().__init__()
        self.prefs = prefs or AppPrefs.load()
        i18n.install(QApplication.instance(), self.prefs.language)
        self.mode = resolve_mode(self.prefs.theme)
        self.windows: dict[str, QWidget] = {}
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setMinimumSize(760, 560)
        self.resize(940, 640)
        self.setWindowIcon(self._app_icon())

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(32, 28, 32, 16)
        lay.setSpacing(6)
        self.title = QLabel(APP_NAME)
        self.title.setObjectName("hubTitle")
        self.subtitle = QLabel("Your all-in-one toolbox. Everything runs on your computer.")
        self.subtitle.setObjectName("muted")
        lay.addWidget(self.title)
        lay.addWidget(self.subtitle)
        lay.addSpacing(18)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        self.tiles: dict[str, Tile] = {}
        for i, tool in enumerate(TOOLS):
            tile = Tile(tool, self.prefs, soon=not tool.available)
            tile.clicked.connect(lambda _=False, k=tool.key: self.open_tool(k))
            self.grid.addWidget(tile, i // 3, i % 3, Qt.AlignmentFlag.AlignHCenter)
            self.tiles[tool.key] = tile
        lay.addLayout(self.grid)
        lay.addStretch(1)
        self.setCentralWidget(root)
        self.version_label = QLabel(f"v{VERSION}")
        self.version_label.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.version_label)
        self.statusBar().showMessage("Ready – everything runs offline on your computer.")
        self._build_menus()
        self.updates = UpdateController(self, self.prefs)
        if self.updates.auto_check_due():
            QTimer.singleShot(4000, lambda: self.updates.check(manual=False))

    # ---- availability (phase 2 tools plug in here)
    def set_available(self, key: str, available: bool) -> None:
        t = self.tiles[key]
        t.soon = not available
        t.setAccessibleName(t.tool.title + ("" if available else " (coming soon)"))
        t.update()

    # ---- menus
    def _build_menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("File")
        self.a_quit = QAction("Quit", self)
        self.a_quit.setShortcut("Ctrl+Q")
        self.a_quit.setMenuRole(QAction.MenuRole.QuitRole)
        self.a_quit.triggered.connect(QApplication.instance().closeAllWindows)
        f.addAction(self.a_quit)
        v = mb.addMenu("View")
        self.a_theme = QAction("Dark mode", self)
        self.a_theme.triggered.connect(self.toggle_theme)
        v.addAction(self.a_theme)
        lm = v.addMenu("Language")
        grp = QActionGroup(self)
        self.lang_actions: dict[str, QAction] = {}
        for code, label in i18n.LANGUAGES:
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(code == self.prefs.language)
            a.triggered.connect(lambda _=False, c=code: self.set_language(c))
            grp.addAction(a)
            lm.addAction(a)
            self.lang_actions[code] = a
        h = mb.addMenu("Help")
        a_up = QAction("Check for Updates…", self)
        a_up.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        a_up.triggered.connect(lambda: self.updates.check(manual=True))
        self.a_auto = QAction("Check for updates automatically", self)
        self.a_auto.setCheckable(True)
        self.a_auto.setChecked(self.prefs.auto_check_updates)
        self.a_auto.triggered.connect(self._toggle_auto)
        a_about = QAction("About", self)
        a_about.triggered.connect(self.about)
        h.addActions([a_up, self.a_auto])
        h.addSeparator()
        h.addAction(a_about)
        self._sync_theme_action()

    def _sync_theme_action(self) -> None:
        self.a_theme.setText("Light mode" if self.mode == "dark" else "Dark mode")

    def toggle_theme(self) -> None:
        from .main_window import check_icon_path
        self.mode = "dark" if self.mode == "light" else "light"
        self.prefs.theme = self.mode
        self.prefs.save()
        apply_theme(QApplication.instance(), self.mode, check_icon_path())
        self._sync_theme_action()
        for w in self.windows.values():
            if hasattr(w, "mode") and hasattr(w, "preview"):
                w.mode = self.mode
                w.preview.set_theme(self.mode)
                w._apply_icons()
        i18n.retranslate(self)
        for t in self.tiles.values():
            t.update()

    def set_language(self, code: str) -> None:
        self.prefs.language = code
        self.prefs.save()
        i18n.set_language(code)
        self.lang_actions[code].setChecked(True)
        i18n.retranslate(self)
        for w in self.windows.values():
            i18n.retranslate(w)
        for t in self.tiles.values():
            t.update()

    def _toggle_auto(self) -> None:
        self.prefs.auto_check_updates = self.a_auto.isChecked()
        self.prefs.save()

    def about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME}</b><br>Version {VERSION}<br><br>QR codes, file converters, PDF forms and more "
                          "in one offline toolbox.")

    @staticmethod
    def _app_icon() -> QIcon:
        p = resource_path("assets", "icons", "app.png")
        return QIcon(str(p)) if p.exists() else QIcon()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowActivate:
            new = resolve_mode(self.prefs.theme)
            if new != self.mode:
                self.mode = new
                self._sync_theme_action()
            for t in self.tiles.values():
                t.update()
        return super().event(e)

    # ---- tools
    def open_tool(self, key: str, *args) -> QWidget | None:
        tool = next(t for t in TOOLS if t.key == key)
        if self.tiles[key].soon:
            QMessageBox.information(self, i18n.tr(tool.title), i18n.tr("This tool is coming in the next update."))
            return None
        w = self.windows.get(key)
        if w is not None and not _alive(w):
            w = None
        if w is None:
            w = self._make(key)
            if w is None:
                return None
            self.windows[key] = w
            i18n.retranslate(w)
        if key == "qr" and args:
            w.open_project(args[0])
        w.show()
        w.raise_()
        w.activateWindow()
        return w

    def _make(self, key: str) -> QWidget | None:
        if key == "qr":
            from .main_window import MainWindow
            return MainWindow(self.prefs, auto_update=False)
        if key == "convert":
            from .convert_window import convert_studio
            return convert_studio(self.prefs)
        if key == "media":
            from .convert_window import convert_media
            return convert_media(self.prefs)
        if key == "form":
            from .form_window import pdf_to_form
            return pdf_to_form(self.prefs)
        factory = getattr(self, "factories", {}).get(key)
        return factory(self.prefs) if factory else None

    def closeEvent(self, e) -> None:
        for w in list(self.windows.values()):
            if _alive(w) and w.isVisible() and not w.close():
                e.ignore()
                return
        super().closeEvent(e)


def _alive(w: QWidget) -> bool:
    try:
        w.isVisible()
        return True
    except RuntimeError:
        return False
