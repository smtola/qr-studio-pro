"""Serializable project model. All sizes are in 'logical pixels' where the QR block == qr_size."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any

from ..utils.validation import ValidationError, build_email, build_event, build_geo, build_phone, build_sms, \
    build_telegram, build_vcard, build_whatsapp, build_wifi, check_payload_length, is_valid_hex, normalize_hex, normalize_url
from ..version import VERSION

SCHEMA_VERSION = 1

CONTENT_TYPES = ("url", "text", "email", "phone", "sms", "wifi", "vcard", "geo", "event", "whatsapp", "telegram")
ECC_LEVELS = ("L", "M", "Q", "H")
MODULE_STYLES = ("square", "rounded", "dots", "small-dots", "gapped", "bars")
EYE_STYLES = ("square", "rounded", "circle")
BACKING_SHAPES = ("none", "square", "rounded", "circle")
FRAME_TYPES = ("none", "simple", "rounded", "card", "badge", "double", "corporate", "cta")
TEXT_POSITIONS = ("top", "bottom")
EXPORT_FORMATS = ("png", "jpg", "svg", "pdf")


@dataclass
class ContentSettings:
    type: str = "url"
    url: str = "https://example.com"
    text: str = ""
    email_to: str = ""
    email_subject: str = ""
    email_body: str = ""
    phone: str = ""
    sms_number: str = ""
    sms_message: str = ""
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_security: str = "WPA"
    wifi_hidden: bool = False
    vcard_name: str = ""
    vcard_org: str = ""
    vcard_phone: str = ""
    vcard_email: str = ""
    vcard_url: str = ""
    geo_lat: str = ""
    geo_lng: str = ""
    event_title: str = ""
    event_start: str = ""
    event_end: str = ""
    event_location: str = ""
    event_description: str = ""
    wa_number: str = ""
    wa_message: str = ""
    telegram_user: str = ""
    ecc: str = "M"
    quiet_zone: int = 4

    def payload(self) -> str:
        """Build the string to encode, or raise ValidationError with a user-facing message."""
        t = self.type
        if t == "url":
            p = normalize_url(self.url)
        elif t == "text":
            if not self.text.strip():
                raise ValidationError("Enter the text to encode.")
            p = self.text
        elif t == "email":
            p = build_email(self.email_to, self.email_subject, self.email_body)
        elif t == "phone":
            p = build_phone(self.phone)
        elif t == "sms":
            p = build_sms(self.sms_number, self.sms_message)
        elif t == "wifi":
            p = build_wifi(self.wifi_ssid, self.wifi_password, self.wifi_security, self.wifi_hidden)
        elif t == "vcard":
            p = build_vcard(self.vcard_name, self.vcard_org, self.vcard_phone,
                            self.vcard_email, self.vcard_url)
        elif t == "geo":
            p = build_geo(self.geo_lat, self.geo_lng)
        elif t == "event":
            p = build_event(self.event_title, self.event_start, self.event_end, self.event_location,
                            self.event_description)
        elif t == "whatsapp":
            p = build_whatsapp(self.wa_number, self.wa_message)
        elif t == "telegram":
            p = build_telegram(self.telegram_user)
        else:
            raise ValidationError(f"Unknown content type '{t}'.")
        check_payload_length(p)
        return p


@dataclass
class LogoSettings:
    enabled: bool = True
    path: str = ""                 # absolute path as last seen
    relative_path: str = ""        # relative to the project file (portable projects)
    sha256: str = ""               # detect a swapped/changed file
    size_pct: float = 20.0         # backing box as % of QR symbol width (10-25)
    backing: str = "rounded"       # none | square | rounded | circle
    backing_color: str = "#FFFFFF"
    padding_pct: float = 10.0      # padding inside backing as % of backing box
    auto_high_ecc: bool = True


@dataclass
class ColorSettings:
    foreground: str = "#111111"
    background: str = "#FFFFFF"
    transparent: bool = False
    gradient: bool = False
    gradient_end: str = "#2563EB"
    gradient_angle: int = 45
    module_style: str = "square"
    preset: str = "Classic Black & White"


@dataclass
class EyeSettings:
    follow_foreground: bool = True
    outer_color: str = "#111111"
    inner_color: str = "#111111"
    outer_style: str = "square"
    inner_style: str = "square"


@dataclass
class FrameSettings:
    type: str = "none"
    color: str = "#111111"
    background: str = "#FFFFFF"
    outer_color: str = "#FFFFFF"        # canvas colour outside the frame shape
    thickness: int = 12
    radius: int = 40
    padding: int = 40
    margin: int = 30
    min_width: int = 0                  # 0 = automatic
    min_height: int = 0
    border_style: str = "solid"         # solid | dashed
    title: str = ""
    title_position: str = "top"
    company: str = ""
    company_position: str = "top"
    caption: str = ""
    caption_position: str = "bottom"
    font_family: str = "Arial"
    font_size: int = 44
    font_weight: str = "bold"           # normal | bold
    text_color: str = "#111111"
    bar_text_color: str = "#FFFFFF"     # text on filled header / button bars
    text_gap: int = 24


@dataclass
class ExportSettings:
    format: str = "png"
    width_px: int = 2000
    dpi: int = 300
    jpeg_quality: int = 95
    qr_size: int = 600                  # logical size of the QR block (incl. quiet zone)


@dataclass
class ProjectSettings:
    content: ContentSettings = field(default_factory=ContentSettings)
    logo: LogoSettings = field(default_factory=LogoSettings)
    colors: ColorSettings = field(default_factory=ColorSettings)
    eyes: EyeSettings = field(default_factory=EyeSettings)
    frame: FrameSettings = field(default_factory=FrameSettings)
    export: ExportSettings = field(default_factory=ExportSettings)

    # ------------------------------------------------------------------ serialisation
    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "app_version": VERSION, **asdict(self)}

    def clone(self) -> "ProjectSettings":
        return copy.deepcopy(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSettings":
        if not isinstance(data, dict):
            raise ValidationError("The settings file does not contain a valid project.")
        ver = data.get("schema_version", 1)
        if not isinstance(ver, int) or ver > SCHEMA_VERSION:
            raise ValidationError("This project was created by a newer version of TL Studio Pro.")
        obj = cls()
        for f in fields(cls):
            section = data.get(f.name)
            if isinstance(section, dict):
                _fill(getattr(obj, f.name), section)
        obj.sanitize()
        return obj

    # ------------------------------------------------------------------ normalisation
    def sanitize(self) -> "ProjectSettings":
        """Clamp numbers, fix enums and colours. Called after loading and from the UI."""
        c, lg, co, ey, fr, ex = self.content, self.logo, self.colors, self.eyes, self.frame, self.export
        c.type = _choice(c.type, CONTENT_TYPES, "url")
        c.ecc = _choice(str(c.ecc).upper(), ECC_LEVELS, "M")
        c.quiet_zone = _clamp(c.quiet_zone, 1, 10)
        c.wifi_security = _choice(str(c.wifi_security).upper(), ("WPA", "WEP", "NOPASS"), "WPA")
        lg.size_pct = _clamp(lg.size_pct, 10.0, 25.0)
        lg.padding_pct = _clamp(lg.padding_pct, 0.0, 30.0)
        lg.backing = _choice(lg.backing, BACKING_SHAPES, "rounded")
        lg.backing_color = _color(lg.backing_color, "#FFFFFF")
        co.foreground = _color(co.foreground, "#111111")
        co.background = _color(co.background, "#FFFFFF")
        co.gradient_end = _color(co.gradient_end, "#2563EB")
        co.gradient_angle = int(_clamp(co.gradient_angle, 0, 360))
        co.module_style = _choice(co.module_style, MODULE_STYLES, "square")
        ey.outer_color = _color(ey.outer_color, "#111111")
        ey.inner_color = _color(ey.inner_color, "#111111")
        ey.outer_style = _choice(ey.outer_style, EYE_STYLES, "square")
        ey.inner_style = _choice(ey.inner_style, EYE_STYLES, "square")
        fr.type = _choice(fr.type, FRAME_TYPES, "none")
        for name in ("color", "background", "outer_color", "text_color", "bar_text_color"):
            setattr(fr, name, _color(getattr(fr, name), "#111111"))
        fr.thickness = int(_clamp(fr.thickness, 0, 60))
        fr.radius = int(_clamp(fr.radius, 0, 200))
        fr.padding = int(_clamp(fr.padding, 0, 200))
        fr.margin = int(_clamp(fr.margin, 0, 200))
        fr.min_width = int(_clamp(fr.min_width, 0, 4000))
        fr.min_height = int(_clamp(fr.min_height, 0, 4000))
        fr.border_style = _choice(fr.border_style, ("solid", "dashed"), "solid")
        for name in ("title_position", "company_position", "caption_position"):
            setattr(fr, name, _choice(getattr(fr, name), TEXT_POSITIONS, "top"))
        fr.font_family = (str(fr.font_family).strip() or "Arial")[:80]
        fr.font_size = int(_clamp(fr.font_size, 12, 120))
        fr.font_weight = _choice(fr.font_weight, ("normal", "bold"), "bold")
        fr.text_gap = int(_clamp(fr.text_gap, 8, 120))
        for name in ("title", "company", "caption"):
            setattr(fr, name, str(getattr(fr, name))[:120].replace("\n", " "))
        ex.format = _choice(ex.format, EXPORT_FORMATS, "png")
        ex.width_px = int(_clamp(ex.width_px, 200, 6000))
        ex.dpi = int(_clamp(ex.dpi, 72, 1200))
        ex.jpeg_quality = int(_clamp(ex.jpeg_quality, 60, 100))
        ex.qr_size = int(_clamp(ex.qr_size, 200, 2000))
        return self


def _fill(target: Any, src: dict[str, Any]) -> None:
    for f in fields(target):
        if f.name not in src:
            continue
        cur, val = getattr(target, f.name), src[f.name]
        try:
            if isinstance(cur, bool):
                setattr(target, f.name, bool(val))
            elif isinstance(cur, int):
                setattr(target, f.name, int(float(val)))
            elif isinstance(cur, float):
                setattr(target, f.name, float(val))
            elif isinstance(cur, str):
                setattr(target, f.name, "" if val is None else str(val))
        except (TypeError, ValueError):
            pass  # keep default for malformed values


def _clamp(v: Any, lo: float, hi: float) -> Any:
    try:
        return max(lo, min(hi, v))
    except TypeError:
        return lo


def _choice(v: Any, allowed: tuple[str, ...], default: str) -> str:
    return v if v in allowed else default


def _color(v: Any, default: str) -> str:
    return normalize_hex(v) if isinstance(v, str) and is_valid_hex(v) else default


def style_sections() -> tuple[str, ...]:
    """Sections stored in brand presets (everything except the encoded content)."""
    return ("logo", "colors", "eyes", "frame", "export")


__all__ = [n for n in dir() if n[0].isupper() or n.endswith("Settings")] + ["is_dataclass"]
