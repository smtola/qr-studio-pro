"""Project files (.qrsp = JSON). They store settings plus *references* to assets, never rendered pixels."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.logo_composer import sha256_file
from ..models.project_settings import ProjectSettings
from ..utils.validation import ValidationError

MAX_PROJECT_BYTES = 2 * 1024 * 1024


@dataclass
class LoadResult:
    settings: ProjectSettings
    logo_missing: bool = False      # a logo was referenced but could not be found -> ask the user to re-select
    logo_changed: bool = False      # file found but its content differs from when the project was saved
    logo_reference: str = ""        # what the project pointed at (for the message)


def atomic_write_text(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".qrs-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_project(settings: ProjectSettings, path: str | os.PathLike) -> Path:
    p = Path(path)
    s = settings.clone().sanitize()
    lg = s.logo
    if lg.path:
        lp = Path(lg.path)
        try:
            lg.relative_path = os.path.relpath(lp, p.resolve().parent).replace("\\", "/")
        except ValueError:      # different drive on Windows
            lg.relative_path = ""
        try:
            lg.sha256 = sha256_file(lp)
        except OSError:
            pass
    else:
        lg.relative_path = lg.sha256 = ""
    try:
        atomic_write_text(p, json.dumps(s.to_dict(), indent=2, ensure_ascii=False))
    except OSError as e:
        raise ValidationError(f"The project could not be saved: {e.strerror or e}") from None
    return p


def load_project(path: str | os.PathLike) -> LoadResult:
    p = Path(path)
    try:
        if p.stat().st_size > MAX_PROJECT_BYTES:
            raise ValidationError("This file is too large to be a TL Studio Pro project.")
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        raise ValidationError(f"The project '{p.name}' could not be opened.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError(f"'{p.name}' is not a valid project file (damaged or wrong format).") from None
    settings = ProjectSettings.from_dict(data)
    return resolve_logo(settings, p)


def resolve_logo(settings: ProjectSettings, project_file: Path) -> LoadResult:
    lg = settings.logo
    ref = lg.path or lg.relative_path
    if not ref:
        return LoadResult(settings)
    candidates = []
    if lg.relative_path:
        candidates.append((project_file.resolve().parent / lg.relative_path))
    if lg.path:
        candidates.append(Path(lg.path))
    for c in candidates:
        if c.is_file():
            lg.path = str(c.resolve())
            changed = False
            if lg.sha256:
                try:
                    changed = sha256_file(c) != lg.sha256
                except OSError:
                    changed = False
            return LoadResult(settings, False, changed, ref)
    # not found: keep the reference so the UI can show it, but flag it
    return LoadResult(settings, True, False, ref)
