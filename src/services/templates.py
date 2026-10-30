"""Built-in design templates: a complete look (colours, eyes, frame, text) the user can start from.
Applying a template keeps the encoded content (except Wi-Fi poster, which switches to the Wi-Fi type)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.project_settings import ProjectSettings


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    colors: dict = field(default_factory=dict)
    eyes: dict = field(default_factory=dict)
    frame: dict = field(default_factory=dict)
    content_type: str = ""          # switch the content type when applying ("" = keep)
    sample: dict = field(default_factory=dict)   # content used only for the gallery thumbnail


def _c(fg, bg="#FFFFFF", **kw):
    return dict(foreground=fg, background=bg, preset="Custom Brand Colors", **kw)


def _e(outer, inner=None, os="rounded", is_="rounded"):
    return dict(follow_foreground=False, outer_color=outer, inner_color=inner or outer, outer_style=os, inner_style=is_)


TEMPLATES: tuple[Template, ...] = (
    Template("Clean Minimal", "Plain black and white, no frame. Maximum compatibility.",
             colors=_c("#111111"), eyes=dict(follow_foreground=True, outer_style="square", inner_style="square"),
             frame=dict(type="none")),
    Template("Restaurant Menu", "Warm red on cream with a 'scan for menu' button.",
             colors=_c("#9F1D1D", "#FFF8EE", module_style="rounded"), eyes=_e("#9F1D1D", "#C2410C"),
             frame=dict(type="cta", title="SCAN FOR MENU", color="#9F1D1D", background="#FFF8EE",
                        outer_color="#FFF8EE", text_color="#9F1D1D", bar_text_color="#FFFFFF", caption="")),
    Template("Business Card", "Navy corporate frame with your company name.",
             colors=_c("#0B2A5B", module_style="rounded"), eyes=_e("#0B2A5B", "#1D4ED8"),
             frame=dict(type="corporate", company="YOUR COMPANY", title="", color="#0B2A5B", text_color="#0B2A5B",
                        bar_text_color="#FFFFFF", caption="Scan to connect")),
    Template("Wi-Fi Poster", "Teal card for a café or office. Switches to the Wi-Fi content type.",
             colors=_c("#0F5E5A", module_style="rounded"), eyes=_e("#0F5E5A", "#0F766E"),
             frame=dict(type="card", title="FREE WI-FI", caption="Scan to connect", color="#0F5E5A",
                        text_color="#0F5E5A", outer_color="#FFFFFF"),
             content_type="wifi", sample=dict(wifi_ssid="Guest", wifi_password="welcome123", wifi_security="WPA")),
    Template("Event Ticket", "Bold badge frame for tickets and passes.",
             colors=_c("#1F1147", module_style="gapped"), eyes=_e("#1F1147", "#6D28D9", "rounded", "rounded"),
             frame=dict(type="badge", title="ADMIT ONE", caption="Show at the entrance", color="#1F1147",
                        text_color="#1F1147", bar_text_color="#FFFFFF")),
    Template("Social Follow", "Purple-to-pink gradient with a follow button.",
             colors=_c("#6D28D9", gradient=True, gradient_end="#BE185D", gradient_angle=45, module_style="dots"),
             eyes=_e("#6D28D9", "#BE185D", "rounded", "circle"),
             frame=dict(type="cta", title="FOLLOW US", color="#6D28D9", text_color="#6D28D9",
                        bar_text_color="#FFFFFF")),
    Template("Ocean Gradient", "Blue gradient with soft rounded modules.",
             colors=_c("#0B3D91", gradient=True, gradient_end="#0891B2", gradient_angle=90, module_style="rounded"),
             eyes=_e("#0B3D91", "#0891B2"), frame=dict(type="rounded", title="", color="#0B3D91")),
    Template("Fresh Green", "Natural green with circular eyes and a double border.",
             colors=_c("#14532D", "#F1FAF3", module_style="gapped"), eyes=_e("#14532D", "#15803D", "rounded", "circle"),
             frame=dict(type="double", title="SCAN ME", color="#14532D", background="#F1FAF3",
                        outer_color="#F1FAF3", text_color="#14532D")),
    Template("Sunset", "Orange-to-crimson gradient on warm paper.",
             colors=_c("#C2410C", "#FFF7ED", gradient=True, gradient_end="#9D174D", gradient_angle=135,
                       module_style="bars"), eyes=_e("#C2410C", "#9D174D"),
             frame=dict(type="rounded", color="#C2410C", background="#FFF7ED", outer_color="#FFF7ED")),
    Template("Bold Sticker", "Thick black border for stickers and packaging.",
             colors=_c("#000000", module_style="square"), eyes=dict(follow_foreground=True),
             frame=dict(type="simple", thickness=22, title="SCAN ME", color="#000000", text_color="#000000")),
)

NAMES = tuple(t.name for t in TEMPLATES)


def get_template(name: str) -> Template:
    for t in TEMPLATES:
        if t.name == name:
            return t
    raise KeyError(name)


def apply_template(settings: ProjectSettings, tpl: Template, *, with_sample: bool = False) -> ProjectSettings:
    """Return new settings: the template's style on top of `settings` (logo and export size are kept)."""
    merged = settings.to_dict()
    merged["colors"] = {**ProjectSettings().to_dict()["colors"], **tpl.colors}
    merged["eyes"] = {**ProjectSettings().to_dict()["eyes"], **tpl.eyes}
    merged["frame"] = {**ProjectSettings().to_dict()["frame"], **tpl.frame}
    if tpl.content_type:
        merged["content"] = {**merged["content"], "type": tpl.content_type}
        if with_sample:
            merged["content"].update(tpl.sample)
    return ProjectSettings.from_dict(merged)
