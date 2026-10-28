"""Input validation and payload builders. Pure functions, no Qt."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
HEX3_RE = re.compile(r"^#?([0-9a-fA-F]{3})$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
HOST_LABEL_RE = re.compile(r"^(?!-)[\w-]{1,63}(?<!-)$", re.UNICODE)
MAX_PAYLOAD_CHARS = 2000  # comfortable for scanning; hard limit is enforced by the encoder


class ValidationError(ValueError):
    """User-facing validation failure; str(e) is safe to show in the UI."""


def normalize_hex(value: str, *, field: str = "Colour") -> str:
    v = (value or "").strip()
    m = HEX_RE.match(v)
    if m:
        return "#" + m.group(1).upper()
    m = HEX3_RE.match(v)
    if m:
        return "#" + "".join(ch * 2 for ch in m.group(1)).upper()
    raise ValidationError(f"{field}: '{value}' is not a valid HEX colour (expected e.g. #111111).")


def is_valid_hex(value: str) -> bool:
    try:
        normalize_hex(value)
        return True
    except ValidationError:
        return False


def _valid_host(host: str) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        return all(0 <= int(p) <= 255 for p in host.split("."))
    if ":" in host:  # IPv6 literal (urlsplit strips brackets)
        return re.fullmatch(r"[0-9a-fA-F:.]+", host) is not None
    labels = host.rstrip(".").split(".")
    if len(labels) < 2 or len(host) > 253:
        return False
    return all(HOST_LABEL_RE.match(lb) for lb in labels) and not labels[-1].isdigit()


def normalize_url(raw: str) -> str:
    """Validate a web URL; add https:// when the scheme is missing. Never fetches or opens it."""
    url = (raw or "").strip()
    if not url:
        raise ValidationError("Enter a URL, e.g. https://example.com")
    if any(ch.isspace() for ch in url):
        raise ValidationError("A URL cannot contain spaces. Encode them as %20 or remove them.")
    if any(unicodedata.category(ch) == "Cc" for ch in url):
        raise ValidationError("The URL contains control characters.")
    if "://" not in url:
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d+(/|$))", url):  # javascript:, data:, file: ...
            raise ValidationError("Only http:// and https:// links are supported in the URL type. "
                                  "Use the Text type for other content.")
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        _ = parts.port  # raises ValueError if the port is invalid
    except ValueError:
        raise ValidationError("This URL is malformed (check the host name and port).") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise ValidationError("Only http:// and https:// links are supported in the URL type. "
                              "Use the Text type for other content.")
    if not _valid_host(host):
        raise ValidationError(f"'{host or url}' is not a valid host name. Example: www.example.com")
    return url


def check_payload_length(payload: str) -> None:
    if not payload:
        raise ValidationError("There is nothing to encode yet.")
    if len(payload) > MAX_PAYLOAD_CHARS:
        raise ValidationError(
            f"The content is {len(payload)} characters long; keep it under {MAX_PAYLOAD_CHARS} "
            "so the QR code stays easy to scan.")


def build_email(to: str, subject: str = "", body: str = "") -> str:
    from urllib.parse import quote
    to = (to or "").strip()
    if not EMAIL_RE.match(to):
        raise ValidationError("Enter a valid e-mail address, e.g. name@example.com")
    q = []
    if subject.strip():
        q.append("subject=" + quote(subject.strip(), safe=""))
    if body.strip():
        q.append("body=" + quote(body.strip(), safe=""))
    return f"mailto:{to}" + ("?" + "&".join(q) if q else "")


def normalize_phone(raw: str) -> str:
    p = (raw or "").strip()
    if not re.fullmatch(r"\+?[\d\s().-]{3,30}", p) or sum(c.isdigit() for c in p) < 3:
        raise ValidationError("Enter a valid phone number (digits, spaces, + - ( ) only).")
    return ("+" if p.startswith("+") else "") + "".join(c for c in p if c.isdigit())


def build_phone(raw: str) -> str:
    return "tel:" + normalize_phone(raw)


def build_sms(number: str, message: str = "") -> str:
    num = normalize_phone(number)
    msg = (message or "").replace("\n", " ").strip()
    return f"SMSTO:{num}:{msg}" if msg else f"SMSTO:{num}:"


def _wifi_escape(s: str) -> str:
    return re.sub(r'([\;,:"])', r"\\\1", s)


def build_wifi(ssid: str, password: str = "", security: str = "WPA", hidden: bool = False) -> str:
    if not ssid:
        raise ValidationError("Enter the Wi-Fi network name (SSID).")
    if len(ssid) > 32:
        raise ValidationError("A Wi-Fi network name can be at most 32 characters.")
    security = security.upper()
    if security not in ("WPA", "WEP", "NOPASS"):
        raise ValidationError("Choose a Wi-Fi security type.")
    if security != "NOPASS":
        if not password:
            raise ValidationError("Enter the Wi-Fi password or choose 'No password'.")
        if security == "WPA" and not 8 <= len(password) <= 63:
            raise ValidationError("A WPA password must be 8–63 characters long.")

    def q(v: str) -> str:  # hex-looking values must be quoted so they are not read as hex keys
        e = _wifi_escape(v)
        return f'"{e}"' if re.fullmatch(r"[0-9a-fA-F]+", v) and len(v) % 2 == 0 else e

    out = f"WIFI:T:{'nopass' if security == 'NOPASS' else security};S:{q(ssid)};"
    if security != "NOPASS":
        out += f"P:{q(password)};"
    if hidden:
        out += "H:true;"
    return out + ";"


def _vc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def build_vcard(name: str, org: str = "", phone: str = "", email: str = "", url: str = "") -> str:
    if not name.strip():
        raise ValidationError("Enter a contact name.")
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_vc(name.strip())}", f"N:{_vc(name.strip())};;;;"]
    if org.strip():
        lines.append(f"ORG:{_vc(org.strip())}")
    if phone.strip():
        lines.append(f"TEL:{normalize_phone(phone)}")
    if email.strip():
        if not EMAIL_RE.match(email.strip()):
            raise ValidationError("The contact e-mail address is not valid.")
        lines.append(f"EMAIL:{email.strip()}")
    if url.strip():
        lines.append(f"URL:{normalize_url(url)}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def slugify(text: str, fallback: str = "qr-code", max_len: int = 40) -> str:
    t = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (text or "").strip().lower())
    t = re.sub(r"[^\w]+", "-", t, flags=re.UNICODE).strip("-_")
    return (t[:max_len].strip("-_") or fallback)
