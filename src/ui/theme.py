"""Design tokens (light / dark), bundled Inter typeface and one QSS template."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from ..utils.paths import resource_path

LIGHT = dict(bg="#F4F5F9", panel="#FFFFFF", panel2="#F7F8FC", border="#E4E7EF", border2="#D5D9E5", text="#141826",
             muted="#68708A", accent="#4F46E5", accent2="#7C3AED", accent_hover="#4338CA", accent_text="#FFFFFF",
             accent_soft="#EEF0FF", input="#FFFFFF", hover="#EEF0F7", canvas="#ECEEF5", ok="#15803D", warn="#B45309",
             err="#B91C1C", err_bg="#FDECEC", warn_bg="#FEF3E2", info_bg="#EEF1F8", icon="#3B4256", focus="#818CF8",
             check_a="#FFFFFF", check_b="#E6E9F1")
DARK = dict(bg="#0E1016", panel="#161922", panel2="#1B1F2A", border="#262B39", border2="#343A4D", text="#ECEEF6",
            muted="#8E96AD", accent="#8B8DFF", accent2="#B38BFF", accent_hover="#A3A5FF", accent_text="#0E1020",
            accent_soft="#232749", input="#12151D", hover="#222736", canvas="#0B0D12", ok="#4ADE80", warn="#FBBF24",
            err="#F87171", err_bg="#3A1D22", warn_bg="#3A2E17", info_bg="#1E2331", icon="#C5CADB", focus="#8B8DFF",
            check_a="#252A38", check_b="#1D212D")

FONT_FILES = ("Inter-Regular.otf", "Inter-Medium.otf", "Inter-SemiBold.otf")
FONT_STACK = ("Inter", "SF Pro Text", "Segoe UI Variable", "Segoe UI", "Helvetica Neue", "Arial")

_QSS = """
QMainWindow, QDialog { background: %(bg)s; color: %(text)s; }
QWidget { color: %(text)s; }
QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(border2)s; border-radius: 8px; padding: 6px 9px; }

/* ---- toolbar ---- */
QToolBar { background: %(panel)s; border: none; border-bottom: 1px solid %(border)s; spacing: 2px; padding: 7px 12px; }
QToolBar::separator { background: %(border)s; width: 1px; margin: 6px 8px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 6px 11px; color: %(text)s; font-weight: 500; }
QToolButton:hover { background: %(hover)s; }
QToolButton:pressed, QToolButton:checked { background: %(border)s; }
QToolButton:focus { border-color: %(focus)s; }
QToolButton:disabled { color: %(muted)s; }
QToolButton#iconButton { padding: 5px; border-radius: 8px; min-width: 22px; min-height: 22px; }
QToolButton#exportButton { color: %(accent_text)s; font-weight: 600; padding: 7px 16px; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(accent)s, stop:1 %(accent2)s); }
QToolButton#exportButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(accent_hover)s, stop:1 %(accent2)s); }
QMenuBar { background: %(panel)s; border-bottom: 1px solid %(border)s; }
QMenuBar::item { padding: 5px 10px; background: transparent; border-radius: 6px; }
QMenuBar::item:selected { background: %(hover)s; }
QMenu { background: %(panel)s; border: 1px solid %(border)s; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 24px 7px 14px; border-radius: 7px; }
QMenu::item:selected { background: %(hover)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 4px; }

/* ---- scrolling ---- */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 3px 2px; }
QScrollBar::handle:vertical { background: %(border2)s; border-radius: 3px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: %(muted)s; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px 3px; }
QScrollBar::handle:horizontal { background: %(border2)s; border-radius: 3px; min-width: 36px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- surfaces ---- */
QFrame#card { background: %(panel)s; border: 1px solid %(border)s; border-radius: 14px; }
QFrame#sidebar, QFrame#inspector { background: %(bg)s; }
QFrame#banner { background: %(err_bg)s; border: 1px solid %(err)s; border-radius: 10px; }
QFrame#advice { border-radius: 9px; border: none; border-left: 3px solid %(muted)s; background: %(info_bg)s; }
QFrame#advice[level="error"] { border-left-color: %(err)s; background: %(err_bg)s; }
QFrame#advice[level="warning"] { border-left-color: %(warn)s; background: %(warn_bg)s; }
QPushButton#sectionHeader { text-align: left; background: transparent; border: none; border-radius: 12px; padding: 0; }
QPushButton#sectionHeader:hover { background: %(hover)s; }
QPushButton#sectionHeader:focus { border: 1px solid %(focus)s; }
QFrame#segFrame { background: %(panel2)s; border: 1px solid %(border)s; border-radius: 10px; }
QPushButton#seg { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px 10px; color: %(muted)s; font-weight: 500; }
QPushButton#seg:hover { color: %(text)s; }
QPushButton#seg:checked { background: %(panel)s; border: 1px solid %(border2)s; color: %(accent)s; font-weight: 600; }
QPushButton#seg:focus { border: 1px solid %(focus)s; }

/* ---- text ---- */
QLabel#muted { color: %(muted)s; font-size: 12px; }
QLabel#h2 { font-weight: 600; font-size: 13px; }
QLabel#error { color: %(err)s; }
QLabel#ok { color: %(ok)s; }
QLabel#warn { color: %(warn)s; }
QLabel#valueLabel { color: %(muted)s; min-width: 44px; font-weight: 500; }
QLabel#pill { background: %(panel)s; border: 1px solid %(border)s; border-radius: 10px; padding: 3px 9px; color: %(muted)s; font-weight: 500; font-size: 12px; }
QLabel#emptyTitle { font-size: 18px; font-weight: 600; }

/* ---- buttons & inputs ---- */
QPushButton { background: %(panel)s; border: 1px solid %(border2)s; border-radius: 9px; padding: 8px 14px; font-weight: 500; }
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: %(border)s; }
QPushButton:focus { border-color: %(focus)s; }
QPushButton:disabled { color: %(muted)s; background: %(panel2)s; border-color: %(border)s; }
QPushButton[primary="true"] { color: %(accent_text)s; border: none; font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(accent)s, stop:1 %(accent2)s); }
QPushButton[primary="true"]:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(accent_hover)s, stop:1 %(accent2)s); }
QPushButton[flat="true"] { background: transparent; border: none; color: %(accent)s; padding: 4px 6px; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QFontComboBox { background: %(input)s; border: 1px solid %(border2)s;
    border-radius: 9px; padding: 7px 10px; selection-background-color: %(accent)s; selection-color: %(accent_text)s; }
QLineEdit:hover, QSpinBox:hover, QComboBox:hover, QPlainTextEdit:hover { border-color: %(muted)s; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid %(focus)s; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: %(muted)s; background: %(panel2)s; }
QLineEdit[invalid="true"] { border: 1px solid %(err)s; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: %(panel)s; border: 1px solid %(border)s; border-radius: 8px; padding: 4px;
    selection-background-color: %(accent_soft)s; selection-color: %(text)s; outline: none; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 1px solid %(border2)s; background: %(input)s; }
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url(%(check_icon)s); }
QCheckBox::indicator:focus { border-color: %(focus)s; }
QSlider { min-height: 22px; }
QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { background: %(panel)s; border: 2px solid %(accent)s; width: 14px; height: 14px; margin: -7px 0; border-radius: 9px; }
QSlider::handle:horizontal:hover { background: %(accent_soft)s; }
QSlider::handle:horizontal:focus { background: %(accent)s; }
QSplitter::handle { background: transparent; width: 6px; }
QProgressBar { background: %(border)s; border: none; border-radius: 4px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
QStatusBar { background: %(panel)s; border-top: 1px solid %(border)s; color: %(muted)s; }
QStatusBar::item { border: none; }
QMessageBox, QProgressDialog { background: %(panel)s; }
QTextBrowser { background: %(input)s; border: 1px solid %(border)s; border-radius: 10px; padding: 8px; }
"""


def setup_fonts(app: QApplication) -> str:
    """Load the bundled Inter typeface; fall back to the platform UI font. Returns the family used."""
    family = ""
    for name in FONT_FILES:
        fid = QFontDatabase.addApplicationFont(str(resource_path("assets", "fonts", name)))
        if fid >= 0 and not family:
            families = QFontDatabase.applicationFontFamilies(fid)
            family = families[0] if families else ""
    f = QFont(family) if family else QFont()
    if not family:
        f.setFamilies(list(FONT_STACK))
    f.setPixelSize(13)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(f)
    return family or f.family()


def resolve_mode(mode: str) -> str:
    if mode in ("light", "dark"):
        return mode
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:  # noqa: BLE001
        return "light"


def tokens(mode: str) -> dict[str, str]:
    return DARK if resolve_mode(mode) == "dark" else LIGHT


def apply_theme(app: QApplication, mode: str, check_icon_path: str = "") -> dict[str, str]:
    t = dict(tokens(mode))
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Base, "input"), (QPalette.ColorRole.AlternateBase, "panel2"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "panel2"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "accent_text"), (QPalette.ColorRole.ToolTipBase, "panel"),
                      (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted")):
        pal.setColor(role, QColor(t[key]))
    app.setPalette(pal)
    t["check_icon"] = check_icon_path or ""
    app.setStyleSheet(_QSS % t)
    return t
