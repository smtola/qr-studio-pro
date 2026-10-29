"""Small reusable controls with accessible names."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from ..utils.validation import is_valid_hex, normalize_hex


class Swatch(QWidget):
    clicked = Signal()

    def __init__(self, color: str = "#000000", size: int = 30, parent=None):
        super().__init__(parent)
        self._c = QColor(color)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_color(self, c: str) -> None:
        self._c = QColor(c)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setBrush(self._c)
        p.setPen(QPen(QColor(128, 128, 140, 140), 1.2 if not self.hasFocus() else 2.2))
        p.drawRoundedRect(r, 8, 8)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(e)


class ColorField(QWidget):
    """Swatch + HEX input + picker dialog. Emits `changed(hex)` only for valid colours."""
    changed = Signal(str)

    def __init__(self, name: str, color: str = "#000000", parent=None):
        super().__init__(parent)
        self._name = name
        self._value = normalize_hex(color)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.swatch = Swatch(self._value)
        self.swatch.setAccessibleName(f"{name} colour swatch (opens colour picker)")
        self.edit = QLineEdit(self._value)
        self.edit.setMaxLength(7)
        self.edit.setAccessibleName(f"{name} HEX value")
        self.edit.setPlaceholderText("#111111")
        self.edit.setFixedWidth(92)
        lay.addWidget(self.swatch)
        lay.addWidget(self.edit)
        lay.addStretch(1)
        self.swatch.clicked.connect(self._pick)
        self.edit.textEdited.connect(self._typed)
        self.edit.editingFinished.connect(self._finish)
        self.setFocusProxy(self.edit)

    def value(self) -> str:
        return self._value

    def set_value(self, c: str) -> None:
        with QSignalBlocker(self.edit):
            self._value = normalize_hex(c)
            self.edit.setText(self._value)
            self.edit.setProperty("invalid", False)
            self.edit.style().unpolish(self.edit)
            self.edit.style().polish(self.edit)
        self.swatch.set_color(self._value)

    def _typed(self, text: str) -> None:
        ok = is_valid_hex(text) and len(text.lstrip("#")) in (3, 6)
        self.edit.setProperty("invalid", not ok and bool(text))
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        if ok:
            self._value = normalize_hex(text)
            self.swatch.set_color(self._value)
            self.changed.emit(self._value)

    def _finish(self) -> None:
        self.edit.setText(self._value)  # snap invalid text back to the last good value
        self.edit.setProperty("invalid", False)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._value), self, f"Choose {self._name}")
        if c.isValid():
            self.set_value(c.name())
            self.changed.emit(self._value)


class SliderRow(QWidget):
    valueChanged = Signal(int)

    def __init__(self, name: str, lo: int, hi: int, value: int, suffix: str = "", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.slider.setAccessibleName(name)
        self.label = QLabel()
        self.label.setObjectName("valueLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)
        self.slider.valueChanged.connect(self._on)
        self._on(value, emit=False)

    def _on(self, v: int, emit: bool = True) -> None:
        self.label.setText(f"{v}{self._suffix}")
        if emit:
            self.valueChanged.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, v: int) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(int(v))
        self._on(int(v), emit=False)


class CollapsibleSection(QFrame):
    """Card with an icon + title header and a chevron; body is shown/hidden."""
    toggled = Signal(bool)

    def __init__(self, title: str, body: QWidget, expanded: bool = True, icon_name: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._title = title
        self._icon_name = icon_name
        self._expanded = expanded
        self._color = "#68708A"
        self.header = QPushButton()
        self.header.setObjectName("sectionHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setAccessibleName(f"{title} section")
        self.header.setMinimumHeight(46)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)
        self._ic = QLabel()
        self._ic.setFixedSize(20, 20)
        self._lbl = QLabel(title)
        self._lbl.setObjectName("h2")
        self._chev = QLabel()
        self._chev.setFixedSize(18, 18)
        for w in (self._ic, self._lbl, self._chev):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ic.setVisible(bool(icon_name))
        hl.addWidget(self._ic)
        hl.addWidget(self._lbl, 1)
        hl.addWidget(self._chev)
        self.body = body
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(14, 2, 14, 14)
        wl.addWidget(body)
        self._wrap = wrap
        lay.addWidget(wrap)
        self.header.clicked.connect(lambda: self.set_expanded(not self._expanded))
        self.retint(self._color)
        self.set_expanded(expanded, emit=False)

    def retint(self, color: str) -> None:
        """Recolour the header icons for the active theme."""
        from .icons import icon
        self._color = color
        if self._icon_name:
            self._ic.setPixmap(icon(self._icon_name, color, 18).pixmap(18, 18))
        self._chev.setPixmap(icon("chevron-down" if self._expanded else "chevron-right", color, 16).pixmap(16, 16))

    def title(self) -> str:
        return self._title

    def set_expanded(self, on: bool, emit: bool = True) -> None:
        self._expanded = on
        self._wrap.setVisible(on)
        self.retint(self._color)
        self.header.setAccessibleDescription("expanded" if on else "collapsed")
        if emit:
            self.toggled.emit(on)

    def is_expanded(self) -> bool:
        return self._expanded


def form() -> QFormLayout:
    f = QFormLayout()
    f.setContentsMargins(0, 4, 0, 0)
    f.setHorizontalSpacing(12)
    f.setVerticalSpacing(10)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return f


def muted(text: str, wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("muted")
    lb.setWordWrap(wrap)
    return lb


def combo(name: str, items: list[tuple[str, str]]) -> QComboBox:
    c = QComboBox()
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(12)
    c.setAccessibleName(name)
    for label, data in items:
        c.addItem(label, data)
    return c


def set_combo(c: QComboBox, data: str) -> None:
    with QSignalBlocker(c):
        i = c.findData(data)
        c.setCurrentIndex(max(i, 0))


def spin(name: str, lo: int, hi: int, suffix: str = "", step: int = 1) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    s.setSingleStep(step)
    s.setAccessibleName(name)
    s.setKeyboardTracking(False)
    return s


def set_value(w, v) -> None:
    with QSignalBlocker(w):
        if isinstance(w, QCheckBox):
            w.setChecked(bool(v))
        elif isinstance(w, QLineEdit):
            if w.text() != v:
                w.setText(v)
        else:
            w.setValue(v)
