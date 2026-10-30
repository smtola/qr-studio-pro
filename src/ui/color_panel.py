"""QR colour panel and finder-eye panel."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core.color_manager import PRESET_NAMES, PRESETS, apply_preset, contrast_ratio, effective_background
from ..models.project_settings import ProjectSettings
from .state import AppState
from .widgets import ColorField, SliderRow, combo, form, muted, set_combo, set_value

CUSTOM = "Custom Brand Colors"
MODULES = [("Square", "square"), ("Rounded", "rounded"), ("Dots", "dots"), ("Small dots", "small-dots"),
           ("Gapped squares", "gapped"), ("Vertical bars", "bars")]
EYES = [("Square", "square"), ("Rounded", "rounded"), ("Circle", "circle")]


class ColorPanel(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        f = form()
        self.preset = combo("Colour preset", [(n, n) for n in PRESET_NAMES])
        self.fg = ColorField("Foreground", "#111111")
        self.bg = ColorField("Background", "#FFFFFF")
        self.transparent = QCheckBox("Transparent background (PNG / SVG / PDF)")
        self.module = combo("Module style", MODULES)
        self.gradient = QCheckBox("Gradient foreground")
        self.g_end = ColorField("Gradient end", "#2563EB")
        self.g_angle = SliderRow("Gradient angle", 0, 360, 45, "°")
        f.addRow("Preset", self.preset)
        f.addRow("Foreground", self.fg)
        f.addRow("Background", self.bg)
        f.addRow(self.transparent)
        f.addRow("Module style", self.module)
        f.addRow(self.gradient)
        f.addRow("Gradient end", self.g_end)
        f.addRow("Angle", self.g_angle)
        lay.addLayout(f)
        self.contrast = QLabel()
        self.contrast.setWordWrap(True)
        self.contrast.setAccessibleName("Contrast check")
        lay.addWidget(self.contrast)
        lay.addWidget(muted("Gradients and light-on-dark colours can hurt scan reliability. Keep strong contrast."))

        self.preset.currentIndexChanged.connect(self._preset)
        self.fg.changed.connect(lambda c: self._set("foreground", c))
        self.bg.changed.connect(lambda c: self._set("background", c))
        self.g_end.changed.connect(lambda c: self._set("gradient_end", c))
        self.g_angle.valueChanged.connect(lambda v: self._set("gradient_angle", v, custom=False))
        self.transparent.toggled.connect(lambda v: self._set("transparent", v, True))
        self.gradient.toggled.connect(lambda v: self._set("gradient", v, True))
        self.module.currentIndexChanged.connect(lambda: self._set("module_style", self.module.currentData(), custom=False))
        state.loaded.connect(self.refresh)
        state.changed.connect(self._contrast)
        self.refresh()

    def _set(self, attr: str, v, refresh: bool = False, custom: bool = True) -> None:
        c = self.state.settings.colors
        setattr(c, attr, v)
        if custom and c.preset != CUSTOM:
            c.preset = CUSTOM
            set_combo(self.preset, CUSTOM)
        self.state.edit(refresh=refresh)

    def _preset(self) -> None:
        apply_preset(self.state.settings, self.preset.currentData())
        self.state.edit(refresh=True)

    def refresh(self) -> None:
        c = self.state.settings.colors
        set_combo(self.preset, c.preset if c.preset in PRESET_NAMES else CUSTOM)
        self.fg.set_value(c.foreground)
        self.bg.set_value(c.background)
        self.g_end.set_value(c.gradient_end)
        self.g_angle.set_value(c.gradient_angle)
        set_value(self.transparent, c.transparent)
        set_value(self.gradient, c.gradient)
        set_combo(self.module, c.module_style)
        self.bg.setEnabled(not c.transparent)
        self.g_end.setEnabled(c.gradient)
        self.g_angle.setEnabled(c.gradient)
        self._contrast()

    def _contrast(self) -> None:
        s = self.state.settings
        r = contrast_ratio(s.colors.foreground, effective_background(s))
        if r < 3:
            txt, name = f"Contrast {r:.1f}:1 – too low, this code will probably not scan.", "error"
        elif r < 4.5:
            txt, name = f"Contrast {r:.1f}:1 – marginal. Darker modules scan better.", "muted"
        else:
            txt, name = f"Contrast {r:.1f}:1 – good.", "ok"
        self.contrast.setObjectName(name)
        self.contrast.setText(txt)
        self.contrast.style().unpolish(self.contrast)
        self.contrast.style().polish(self.contrast)


class EyePanel(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.follow = QCheckBox("Use the foreground colour for the eyes")
        lay.addWidget(self.follow)
        f = form()
        self.outer = ColorField("Outer eye", "#111111")
        self.inner = ColorField("Inner pupil", "#111111")
        self.outer_style = combo("Outer eye style", EYES)
        self.inner_style = combo("Inner pupil style", EYES)
        f.addRow("Outer colour", self.outer)
        f.addRow("Pupil colour", self.inner)
        f.addRow("Outer style", self.outer_style)
        f.addRow("Pupil style", self.inner_style)
        lay.addLayout(f)
        row = QHBoxLayout()
        self.b_square = QPushButton("Classic square")
        self.b_round = QPushButton("Rounded")
        self.b_square.setAccessibleName("Eye preset: classic square")
        self.b_round.setAccessibleName("Eye preset: rounded")
        row.addWidget(self.b_square)
        row.addWidget(self.b_round)
        lay.addLayout(row)
        lay.addWidget(muted("The three large corner markers are used by scanners to find the code. "
                            "Square or rounded eyes are the safest."))
        self.follow.toggled.connect(lambda v: self._set("follow_foreground", v, True))
        self.outer.changed.connect(lambda c: self._set("outer_color", c))
        self.inner.changed.connect(lambda c: self._set("inner_color", c))
        self.outer_style.currentIndexChanged.connect(lambda: self._set("outer_style", self.outer_style.currentData()))
        self.inner_style.currentIndexChanged.connect(lambda: self._set("inner_style", self.inner_style.currentData()))
        self.b_square.clicked.connect(lambda: self._style("square", "square"))
        self.b_round.clicked.connect(lambda: self._style("rounded", "rounded"))
        state.loaded.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v, refresh: bool = False) -> None:
        e = self.state.settings.eyes
        if attr in ("outer_color", "inner_color") and e.follow_foreground:
            e.follow_foreground = False
            refresh = True
        setattr(e, attr, v)
        self.state.edit(refresh=refresh)

    def _style(self, outer: str, inner: str) -> None:
        e = self.state.settings.eyes
        e.outer_style, e.inner_style = outer, inner
        self.state.edit(refresh=True)

    def refresh(self) -> None:
        e = self.state.settings.eyes
        set_value(self.follow, e.follow_foreground)
        self.outer.set_value(e.outer_color)
        self.inner.set_value(e.inner_color)
        set_combo(self.outer_style, e.outer_style)
        set_combo(self.inner_style, e.inner_style)
        self.outer.setEnabled(not e.follow_foreground)
        self.inner.setEnabled(not e.follow_foreground)
