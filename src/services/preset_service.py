"""Brand presets: the style (logo, colours, eyes, frame, export) without the encoded content."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from ..models.project_settings import ProjectSettings, style_sections
from ..utils.paths import presets_dir
from ..utils.validation import ValidationError
from .project_service import atomic_write_text

PRESET_KIND = "qr-studio-brand-preset"


def _safe_name(name: str) -> str:
    n = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip()
    if not n:
        raise ValidationError("Give the preset a name (letters, numbers, spaces, - and _).")
    return n[:60]


def preset_to_dict(name: str, settings: ProjectSettings, include_logo_path: bool = True) -> dict:
    full = asdict(settings.clone().sanitize())
    data = {k: full[k] for k in style_sections()}
    if not include_logo_path:
        data["logo"]["path"] = data["logo"]["relative_path"] = data["logo"]["sha256"] = ""
    return {"kind": PRESET_KIND, "name": name, "schema_version": 1, **data}


def save_preset(name: str, settings: ProjectSettings, directory: Path | None = None,
                include_logo_path: bool = True) -> Path:
    d = directory or presets_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{_safe_name(name)}.json"
        atomic_write_text(path, json.dumps(preset_to_dict(name, settings, include_logo_path), indent=2,
                                           ensure_ascii=False))
    except OSError as e:
        raise ValidationError(f"The preset could not be saved: {e.strerror or e}") from None
    return path


def load_preset_file(path: str | Path) -> dict:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        raise ValidationError(f"The preset '{p.name}' could not be opened.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError(f"'{p.name}' is not a valid preset file.") from None
    if not isinstance(data, dict) or data.get("kind") != PRESET_KIND:
        raise ValidationError(f"'{p.name}' is not a QR Studio Pro brand preset.")
    return data


def apply_preset_file(settings: ProjectSettings, path: str | Path, apply_logo: bool = True) -> ProjectSettings:
    """Return new settings = `settings` content + preset style."""
    data = load_preset_file(path)
    merged = settings.to_dict()
    for k in style_sections():
        if isinstance(data.get(k), dict):
            merged[k] = {**merged[k], **data[k]}
    if not apply_logo:
        merged["logo"] = {**merged["logo"], **{kk: getattr(settings.logo, kk) for kk in ("path", "relative_path", "sha256")}}
    return ProjectSettings.from_dict(merged)


def list_presets(directory: Path | None = None) -> list[tuple[str, Path]]:
    d = directory or presets_dir()
    out: list[tuple[str, Path]] = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                out.append((str(load_preset_file(p).get("name", p.stem)), p))
            except ValidationError:
                continue
    return out


def delete_preset(path: Path) -> None:
    try:
        path.unlink()
    except OSError as e:
        raise ValidationError(f"The preset could not be deleted: {e.strerror or e}") from None
