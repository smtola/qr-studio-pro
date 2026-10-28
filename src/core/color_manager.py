"""Colour maths (WCAG contrast) and the built-in colour presets."""
from __future__ import annotations

from dataclasses import dataclass

from ..models.project_settings import ProjectSettings
from ..utils.validation import normalize_hex


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = normalize_hex(value)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def relative_luminance(value: str) -> float:
    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(round(x + (y - x) * t) for x, y in zip(ra, rb)))  # type: ignore[arg-type]


@dataclass(frozen=True)
class ColorPreset:
    name: str
    foreground: str
    background: str
    eye_outer: str
    eye_inner: str


CUSTOM_PRESET = "Custom Brand Colors"

PRESETS: tuple[ColorPreset, ...] = (
    ColorPreset("Classic Black & White", "#000000", "#FFFFFF", "#000000", "#000000"),
    ColorPreset("Corporate Blue", "#0B3D91", "#FFFFFF", "#0B3D91", "#1D6FE0"),
    ColorPreset("Emerald Green", "#064E3B", "#FFFFFF", "#047857", "#059669"),
    ColorPreset("Crimson Red", "#7F1D1D", "#FFFFFF", "#B91C1C", "#7F1D1D"),
    ColorPreset("Purple Modern", "#3B0764", "#FFFFFF", "#6D28D9", "#4C1D95"),
    # Deliberately dark modules on a warm light ground: inverted (light-on-dark) codes fail on many scanners.
    ColorPreset("Dark Premium", "#1C1917", "#F6F0E2", "#A16207", "#1C1917"),
)

PRESET_NAMES = tuple(p.name for p in PRESETS) + (CUSTOM_PRESET,)


def apply_preset(settings: ProjectSettings, name: str) -> ProjectSettings:
    """Apply a named preset in place. 'Custom Brand Colors' keeps the current colours."""
    settings.colors.preset = name
    for p in PRESETS:
        if p.name == name:
            c, e = settings.colors, settings.eyes
            c.foreground, c.background, c.transparent, c.gradient = p.foreground, p.background, False, False
            e.follow_foreground = False
            e.outer_color, e.inner_color = p.eye_outer, p.eye_inner
            break
    return settings


def effective_background(settings: ProjectSettings) -> str:
    """Colour the QR will realistically sit on (used for contrast checks)."""
    if not settings.colors.transparent:
        return settings.colors.background
    return settings.frame.background if settings.frame.type != "none" else "#FFFFFF"
