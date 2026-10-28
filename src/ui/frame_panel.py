"""Frame Designer panel."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from ..core.fonts import system_font_available
from .state import AppState
from .widgets import ColorField, SliderRow, combo, form, muted, set_combo, set_value, spin

FRAMES = [("No frame", "none"), ("Simple rectangle", "simple"), ("Rounded rectangle", "rounded"),
          ("Rounded card", "card"), ("Circle / badge", "badge"), ("Double line", "double"),
          ("Corporate (header bar)", "corporate"), ("Call-to-action (button)", "cta")]
POS = [("Top", "top"), ("Bottom", "bottom")]
FONTS = ["Arial", "Helvetica", "Segoe UI", "Verdana", "Tahoma", "Georgia", "Times New Roman", "Courier New",
         "Noto Sans", "Noto Sans Khmer", "DejaVu Sans", "Liberation Sans"]


def _line(name: str, ph: str) -> QLineEdit:
    e = QLineEdit()
    e.setAccessibleName(name)
    e.setPlaceholderText(ph)
    e.setMaxLength(120)
    return e


class FramePanel(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        f = form()
        self.type = combo("Frame type", FRAMES)
        self.color = ColorField("Frame colour", "#111111")
        self.background = ColorField("Frame background", "#FFFFFF")
        self.outer = ColorField("Canvas colour outside the frame", "#FFFFFF")
        self.style = combo("Border style", [("Solid", "solid"), ("Dashed", "dashed")])
        self.thickness = SliderRow("Frame thickness", 0, 60, 12, " px")
        self.radius = SliderRow("Corner radius", 0, 200, 40, " px")
        self.padding = SliderRow("Inner padding", 0, 200, 40, " px")
        self.margin = SliderRow("Outer margin", 0, 200, 30, " px")
        self.width = spin("Minimum frame width (0 = automatic)", 0, 4000, " px", 10)
        self.height = spin("Minimum frame height (0 = automatic)", 0, 4000, " px", 10)
        for lab, w in (("Type", self.type), ("Frame colour", self.color), ("Background", self.background),
                       ("Canvas colour", self.outer), ("Border", self.style), ("Thickness", self.thickness),
                       ("Corner radius", self.radius), ("Inner padding", self.padding),
                       ("Outer margin", self.margin), ("Min. width", self.width), ("Min. height", self.height)):
            f.addRow(lab, w)
        lay.addLayout(f)
        lay.addWidget(muted("Text is placed outside the QR code and its quiet zone, so it never covers modules."))

        t = form()
        self.title = _line("Title text", "SCAN ME")
        self.title_pos = combo("Title position", POS)
        self.company = _line("Company name or message", "Your company")
        self.company_pos = combo("Company position", POS)
        self.caption = _line("Caption text", "Visit our website")
        self.caption_pos = combo("Caption position", POS)
        self.font = combo("Font family", [(n, n) for n in FONTS])
        self.font.setEditable(True)
        self.size = SliderRow("Font size", 12, 120, 44, " px")
        self.weight = combo("Font weight", [("Bold", "bold"), ("Regular", "normal")])
        self.text_color = ColorField("Text colour", "#111111")
        self.bar_color = ColorField("Text colour on bars", "#FFFFFF")
        self.gap = SliderRow("Gap between text and QR", 8, 120, 24, " px")
        for lab, w in (("Title", self.title), ("   position", self.title_pos), ("Company", self.company),
                       ("   position", self.company_pos), ("Caption", self.caption), ("   position", self.caption_pos),
                       ("Font", self.font), ("Font size", self.size), ("Weight", self.weight),
                       ("Text colour", self.text_color), ("Bar text", self.bar_color), ("Text gap", self.gap)):
            t.addRow(lab, w)
        lay.addLayout(t)
        self.font_note = muted("")
        lay.addWidget(self.font_note)

        def bind(widget, attr, sig="valueChanged", refresh=False):
            getattr(widget, sig).connect(lambda v: self._set(attr, v, refresh))
        self.type.currentIndexChanged.connect(lambda: self._set("type", self.type.currentData(), True))
        self.style.currentIndexChanged.connect(lambda: self._set("border_style", self.style.currentData()))
        for w, a in ((self.color, "color"), (self.background, "background"), (self.outer, "outer_color"),
                     (self.text_color, "text_color"), (self.bar_color, "bar_text_color")):
            bind(w, a, "changed")
        for w, a in ((self.thickness, "thickness"), (self.radius, "radius"), (self.padding, "padding"),
                     (self.margin, "margin"), (self.size, "font_size"), (self.gap, "text_gap")):
            bind(w, a)
        self.width.valueChanged.connect(lambda v: self._set("min_width", v))
        self.height.valueChanged.connect(lambda v: self._set("min_height", v))
        for w, a in ((self.title, "title"), (self.company, "company"), (self.caption, "caption")):
            w.textEdited.connect(lambda v, a=a: self._set(a, v))
        for w, a in ((self.title_pos, "title_position"), (self.company_pos, "company_position"),
                     (self.caption_pos, "caption_position"), (self.weight, "font_weight")):
            w.currentIndexChanged.connect(lambda _=0, w=w, a=a: self._set(a, w.currentData()))
        self.font.currentTextChanged.connect(lambda v: self._set("font_family", v.strip() or "Arial"))
        state.loaded.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v, refresh: bool = False) -> None:
        setattr(self.state.settings.frame, attr, v)
        if attr == "font_family":
            self._font_note()
        self.state.edit(refresh=refresh)

    def _font_note(self) -> None:
        fam = self.state.settings.frame.font_family
        ok = system_font_available(fam)
        self.font_note.setText("" if ok else f"“{fam}” is not installed here; a similar font is used instead.")

    def refresh(self) -> None:
        fr = self.state.settings.frame
        set_combo(self.type, fr.type)
        set_combo(self.style, fr.border_style)
        for w, v in ((self.color, fr.color), (self.background, fr.background), (self.outer, fr.outer_color),
                     (self.text_color, fr.text_color), (self.bar_color, fr.bar_text_color)):
            w.set_value(v)
        for w, v in ((self.thickness, fr.thickness), (self.radius, fr.radius), (self.padding, fr.padding),
                     (self.margin, fr.margin), (self.size, fr.font_size), (self.gap, fr.text_gap)):
            w.set_value(v)
        set_value(self.width, fr.min_width)
        set_value(self.height, fr.min_height)
        for w, v in ((self.title, fr.title), (self.company, fr.company), (self.caption, fr.caption)):
            set_value(w, v)
        for w, v in ((self.title_pos, fr.title_position), (self.company_pos, fr.company_position),
                     (self.caption_pos, fr.caption_position), (self.weight, fr.font_weight)):
            set_combo(w, v)
        self.font.blockSignals(True)
        self.font.setCurrentText(fr.font_family)
        self.font.blockSignals(False)
        self._font_note()
        on = fr.type != "none"
        for w in (self.color, self.background, self.outer, self.style, self.thickness, self.radius, self.padding,
                  self.margin, self.width, self.height):
            w.setEnabled(on)
