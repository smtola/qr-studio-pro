"""Renderer-independent scene description. One scene feeds the PNG/JPG, SVG and PDF back-ends,
so preview and every export share the same geometry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from PIL import Image

Corners = tuple[bool, bool, bool, bool]  # top-left, top-right, bottom-right, bottom-left
ALL = (True, True, True, True)


@dataclass(frozen=True)
class Shape:
    kind: str  # "rrect" | "ellipse"
    x: float
    y: float
    w: float
    h: float
    r: float = 0.0
    corners: Corners = ALL

    def inset(self, d: float) -> "Shape":
        return Shape(self.kind, self.x + d, self.y + d, max(self.w - 2 * d, 0.0), max(self.h - 2 * d, 0.0),
                     max(self.r - d, 0.0), self.corners)


@dataclass(frozen=True)
class Gradient:
    c0: str
    c1: str
    x1: float
    y1: float
    x2: float
    y2: float


Fill = Union[str, Gradient]


@dataclass
class ShapeEl:
    shape: Shape
    fill: str | None = None
    stroke: str | None = None
    stroke_w: float = 0.0
    dashed: bool = False


@dataclass
class Layer:
    """Many shapes painted with one fill; `cuts` are holes (e.g. the inside of a finder ring)."""
    adds: list[Shape]
    cuts: list[Shape]
    fill: Fill


@dataclass
class TextEl:
    cx: float
    baseline: float
    text: str
    family: str
    size: float
    bold: bool
    color: str


@dataclass
class ImageEl:
    image: Image.Image
    x: float
    y: float
    w: float
    h: float


@dataclass
class Scene:
    width: float
    height: float
    canvas_fill: str | None
    elements: list = field(default_factory=list)
    # layout facts, used by tests and the property inspector
    qr_block: tuple[float, float, float, float] = (0, 0, 0, 0)
    symbol: tuple[float, float, float, float] = (0, 0, 0, 0)
    text_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    frame_box: tuple[float, float, float, float] = (0, 0, 0, 0)
    logo_box: tuple[float, float, float, float] | None = None
    backing_box: tuple[float, float, float, float] | None = None
