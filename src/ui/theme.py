"""Light / dark themes as design tokens + one QSS template."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

LIGHT = dict(bg="#F3F4F8", panel="#FFFFFF", panel2="#F8F9FC", border="#E3E6EE", text="#1B2033", muted="#6B7285",
             accent="#4F46E5", accent_hover="#4338CA", accent_text="#FFFFFF", input="#FFFFFF", hover="#EEF0F7",
             canvas="#E9ECF3", ok="#15803D", warn="#B45309", err="#B91C1C", icon="#3B4256", focus="#818CF8",
             check_a="#FFFFFF", check_b="#E4E7EE")
DARK = dict(bg="#12141C", panel="#1A1D29", panel2="#202434", border="#2B3042", text="#E7E9F2", muted="#98A0B8",
            accent="#7C83FF", accent_hover="#9AA0FF", accent_text="#0E1020", input="#141722", hover="#262B3D",
            canvas="#0E1017", ok="#4ADE80", warn="#FBBF24", err="#F87171", icon="#C5CADB", focus="#7C83FF",
            check_a="#2A2E3D", check_b="#222635")

_QSS = """
* { font-size: 13px; }
QMainWindow, QDialog { background: %(bg)s; color: %(text)s; }
QWidget { color: %(text)s; }
QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(border)s; padding: 4px 8px; }
QToolBar { background: %(panel)s; border: none; border-bottom: 1px solid %(border)s; spacing: 4px; padding: 6px 10px; }
QToolBar::separator { background: %(border)s; width: 1px; margin: 4px 6px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 6px 10px; color: %(text)s; }
QToolButton:hover { background: %(hover)s; }
QToolButton:pressed, QToolButton:checked { background: %(border)s; }
QToolButton:focus { border-color: %(focus)s; }
QToolButton:disabled { color: %(muted)s; }
QToolButton#exportButton { background: %(accent)s; color: %(accent_text)s; font-weight: 600; padding: 6px 14px; }
QToolButton#exportButton:hover { background: %(accent_hover)s; }
QMenuBar { background: %(panel)s; border-bottom: 1px solid %(border)s; }
QMenuBar::item { padding: 5px 10px; background: transparent; border-radius: 6px; }
QMenuBar::item:selected { background: %(hover)s; }
QMenu { background: %(panel)s; border: 1px solid %(border)s; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 6px; }
QMenu::item:selected { background: %(hover)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 4px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(muted)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(border)s; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QFrame#card { background: %(panel)s; border: 1px solid %(border)s; border-radius: 12px; }
QFrame#sidebar { background: %(bg)s; }
QFrame#inspector { background: %(bg)s; }
QPushButton#sectionHeader { text-align: left; background: transparent; border: none; border-radius: 12px;
    padding: 11px 14px; font-weight: 600; font-size: 13px; }
QPushButton#sectionHeader:hover { background: %(hover)s; }
QPushButton#sectionHeader:focus { border: 1px solid %(focus)s; }
QLabel#muted { color: %(muted)s; font-size: 12px; }
QLabel#h2 { font-weight: 600; font-size: 13px; }
QLabel#error { color: %(err)s; }
QLabel#ok { color: %(ok)s; }
QLabel#warn { color: %(warn)s; }
QLabel#valueLabel { color: %(muted)s; min-width: 44px; }
QLabel#emptyTitle { font-size: 18px; font-weight: 600; }
QPushButton { background: %(panel2)s; border: 1px solid %(border)s; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: %(hover)s; }
QPushButton:focus { border-color: %(focus)s; }
QPushButton:disabled { color: %(muted)s; }
QPushButton[primary="true"] { background: %(accent)s; color: %(accent_text)s; border: none; font-weight: 600; }
QPushButton[primary="true"]:hover { background: %(accent_hover)s; }
QPushButton[flat="true"] { background: transparent; border: none; color: %(accent)s; padding: 4px 6px; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QFontComboBox { background: %(input)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 6px 8px; selection-background-color: %(accent)s; selection-color: %(accent_text)s; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid %(focus)s; }
QLineEdit[invalid="true"] { border: 1px solid %(err)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: %(panel)s; border: 1px solid %(border)s; selection-background-color: %(hover)s;
    selection-color: %(text)s; outline: none; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid %(muted)s; background: %(input)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url(%(check_icon)s); }
QCheckBox::indicator:focus { border-color: %(focus)s; }
QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { background: %(panel)s; border: 2px solid %(accent)s; width: 14px; height: 14px;
    margin: -7px 0; border-radius: 9px; }
QSlider::handle:horizontal:focus { background: %(accent)s; }
QSplitter::handle { background: transparent; width: 6px; }
QProgressBar { background: %(border)s; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
QStatusBar { background: %(panel)s; border-top: 1px solid %(border)s; color: %(muted)s; }
QMessageBox { background: %(panel)s; }
"""


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
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["input"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["panel2"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["panel2"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t["accent_text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["panel"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["muted"]))
    app.setPalette(pal)
    f = app.font()
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(f)
    t["check_icon"] = check_icon_path or ""
    app.setStyleSheet(_QSS % t)
    return t
