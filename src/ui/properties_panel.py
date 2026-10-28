"""Right-hand inspector: current values, scan-reliability advice and output facts."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..core.export_manager import Prepared
from .state import AppState
from .widgets import Swatch

LEVEL_MARK = {"error": ("✖", "error"), "warning": ("▲", "warn"), "info": ("ⓘ", "muted")}


class PropertiesPanel(QScrollArea):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("inspector")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Properties")
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(10, 10, 10, 10)
        self.lay.setSpacing(10)
        self.setWidget(body)
        self.cards: list[QFrame] = []
        self.show_prep(None, "")

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)
        h = QLabel(title)
        h.setObjectName("h2")
        v.addWidget(h)
        return card, v

    def _clear(self) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    @staticmethod
    def _grid(rows: list[tuple[str, str, str | None]]) -> QGridLayout:
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(5)
        for i, (k, v, color) in enumerate(rows):
            kl = QLabel(k)
            kl.setObjectName("muted")
            g.addWidget(kl, i, 0)
            if color:
                sw = Swatch(color, 16)
                sw.setEnabled(False)
                g.addWidget(sw, i, 1)
                g.addWidget(QLabel(v), i, 2)
            else:
                lb = QLabel(v)
                lb.setWordWrap(True)
                g.addWidget(lb, i, 1, 1, 2)
        g.setColumnStretch(2, 1)
        return g

    def show_prep(self, prep: Prepared | None, error: str) -> None:
        self._clear()
        if prep is None:
            card, v = self._card("Preview")
            lb = QLabel(error or "Enter the content to encode and the QR code will appear here.")
            lb.setObjectName("error" if error else "muted")
            lb.setWordWrap(True)
            v.addWidget(lb)
            self.lay.addWidget(card)
            self.lay.addStretch(1)
            return
        s = prep.settings
        w, h = prep.output_size()
        c, e, lg, fr = s.colors, s.eyes, s.logo, s.frame

        card, v = self._card("QR code")
        v.addLayout(self._grid([
            ("Modules", f"{prep.qrm.size} × {prep.qrm.size} (version {prep.qrm.version})", None),
            ("Error correction", f"{prep.ecc_used}" + (" (raised for logo)" if prep.ecc_used != s.content.ecc else ""), None),
            ("Quiet zone", f"{s.content.quiet_zone} modules", None),
            ("Output", f"{w} × {h} px  ·  {s.export.format.upper()}", None),
        ]))
        self.lay.addWidget(card)

        card, v = self._card("Colours")
        rows = [("Modules", c.foreground + (" → " + c.gradient_end if c.gradient else ""), c.foreground),
                ("Background", "transparent" if c.transparent else c.background, None if c.transparent else c.background)]
        if not e.follow_foreground:
            rows += [("Outer eye", e.outer_color, e.outer_color), ("Pupil", e.inner_color, e.inner_color)]
        rows.append(("Style", f"{c.module_style} modules, {e.outer_style} eyes", None))
        v.addLayout(self._grid(rows))
        self.lay.addWidget(card)

        card, v = self._card("Logo")
        if prep.logo is not None and lg.enabled:
            from ..core.logo_composer import plan_logo
            plan = plan_logo(s, prep.logo.image, prep.scene.symbol)
            v.addLayout(self._grid([("Size", f"{lg.size_pct:.0f}% of the code width", None),
                                    ("Backing", lg.backing, lg.backing_color if lg.backing != "none" else None),
                                    ("Modules hidden", f"≈ {plan.covered_fraction * 100:.0f}%", None)]))
        else:
            v.addWidget(self._muted("No centre logo." if not lg.path else "The logo is switched off or unavailable."))
        self.lay.addWidget(card)

        card, v = self._card("Frame")
        if fr.type == "none":
            v.addWidget(self._muted("No frame."))
        else:
            v.addLayout(self._grid([("Type", fr.type, None), ("Border", f"{fr.thickness}px, radius {fr.radius}px", fr.color),
                                    ("Padding / margin", f"{fr.padding}px / {fr.margin}px", None)]))
        self.lay.addWidget(card)

        card, v = self._card("Scan reliability")
        for a in prep.advice:
            mark, name = LEVEL_MARK.get(a.level, ("•", "muted"))
            lb = QLabel(f"{mark}  {a.message}")
            lb.setWordWrap(True)
            lb.setObjectName(name)
            lb.setAccessibleName(f"{a.level}: {a.message}")
            v.addWidget(lb)
        self.lay.addWidget(card)
        self.lay.addStretch(1)

    @staticmethod
    def _muted(t: str) -> QLabel:
        lb = QLabel(t)
        lb.setObjectName("muted")
        lb.setWordWrap(True)
        return lb
