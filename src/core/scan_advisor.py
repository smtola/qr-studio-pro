"""Scan-reliability advice. Never promises a code will scan; only flags known risk factors."""
from __future__ import annotations

from dataclasses import dataclass

from ..models.project_settings import ProjectSettings
from .color_manager import contrast_ratio, effective_background, relative_luminance


@dataclass(frozen=True)
class Advice:
    level: str      # "info" | "warning" | "error"
    code: str
    message: str


def advise(settings: ProjectSettings, *, version: int | None = None, logo_loaded: bool = False,
           logo_error: str | None = None, covered_fraction: float = 0.0,
           module_px: float | None = None, ecc_used: str | None = None) -> list[Advice]:
    out: list[Advice] = []
    co, ey, lg, fr = settings.colors, settings.eyes, settings.logo, settings.frame
    bg = effective_background(settings)

    def check(color: str, what: str) -> None:
        ratio = contrast_ratio(color, bg)
        if ratio < 3.0:
            out.append(Advice("error", "contrast", f"{what} has very low contrast against the background "
                              f"({ratio:.1f}:1). Phone cameras will probably fail to read this code."))
        elif ratio < 4.5:
            out.append(Advice("warning", "contrast", f"{what} contrast is marginal ({ratio:.1f}:1). "
                              "Darker modules on a lighter background scan more reliably."))
        if relative_luminance(color) > relative_luminance(bg) and ratio >= 3.0:
            out.append(Advice("warning", "inverted", f"{what} is lighter than the background (inverted code). "
                              "Many scanner apps cannot read inverted QR codes."))

    check(co.foreground, "Module colour")
    if co.gradient:
        check(co.gradient_end, "Gradient end colour")
    if not ey.follow_foreground:
        check(ey.outer_color, "Outer eye colour")
        check(ey.inner_color, "Inner eye colour")

    if co.transparent:
        out.append(Advice("info", "transparent", "Transparent background: scanning depends on what the code "
                          "is placed on. Keep the area behind it plain and light."))
    if co.module_style == "dots":
        out.append(Advice("warning", "dots", "Dot modules are less tolerant of blur and glare than squares."))
    if ey.outer_style == "circle":
        out.append(Advice("warning", "circle-eyes", "Circular outer finder eyes are not recognised by some scanner "
                          "apps. Prefer square or rounded eyes, and test with several phones."))
    elif ey.outer_style == "rounded" or ey.inner_style == "circle":
        out.append(Advice("info", "rounded-eyes", "Stylised finder eyes are readable by most phones but are "
                          "slightly less robust than square ones."))
    if settings.content.quiet_zone < 4:
        out.append(Advice("warning", "quiet", "A quiet zone smaller than 4 modules can stop some scanners."))

    if logo_error:
        out.append(Advice("error", "logo-missing", logo_error))
    elif lg.enabled and logo_loaded:
        if ecc_used != "H":
            out.append(Advice("warning", "ecc", "A centre logo hides modules; use error correction level H."))
        if covered_fraction > 0.09 or lg.size_pct > 20:
            out.append(Advice("warning", "logo-size", f"The logo hides about {covered_fraction * 100:.0f}% of the "
                              "code. Keep it at 20% size or below for the most reliable scanning."))
        if lg.backing == "none":
            out.append(Advice("info", "logo-backing", "Without a backing, QR modules show through the logo; "
                              "add a backing for a cleaner, more reliable result."))
        else:
            ratio = contrast_ratio(lg.backing_color, bg)
            if ratio > 1.0 and ratio < 1.15 or lg.backing_color == bg:
                pass  # blends in with the background: ideal
    if version and version >= 15:
        out.append(Advice("info", "dense", f"This is a dense code (version {version}). Shorter content makes "
                          "bigger, easier-to-scan modules."))
    if module_px is not None and module_px < 4:
        out.append(Advice("warning", "resolution", f"Each module will be only {module_px:.1f} px wide at this "
                          "export size. Increase the export width or print size."))
    if fr.type != "none":
        for txt, col, bgc, what in ((fr.title or fr.caption or fr.company, fr.text_color, fr.background, "Frame text"),):
            if txt and contrast_ratio(col, bgc) < 3:
                out.append(Advice("warning", "text-contrast", f"{what} has low contrast against the frame background."))
        if (fr.type in ("corporate", "cta")) and (fr.title or fr.company) and \
                contrast_ratio(fr.bar_text_color, fr.color) < 3:
            out.append(Advice("warning", "text-contrast", "Text on the frame bar has low contrast."))
    out.append(Advice("info", "disclaimer", "No QR code is guaranteed to scan in every situation. Always test the "
                      "final design with several phones, at the real print size, before distributing it."))
    return out
