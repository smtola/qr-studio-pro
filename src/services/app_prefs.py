"""Persisted UI preferences (theme, last folders, recent projects, window geometry)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ..utils.logging_config import get_logger
from ..utils.paths import user_data_dir
from .project_service import atomic_write_text

log = get_logger("prefs")
MAX_RECENT = 10


@dataclass
class AppPrefs:
    theme: str = "system"            # system | light | dark
    language: str = "en"             # en | km
    last_export_dir: str = ""
    last_logo_dir: str = ""
    last_project_dir: str = ""
    recent_projects: list[str] = field(default_factory=list)
    geometry: str = ""               # base64 of QMainWindow.saveGeometry()
    zoom_mode: str = "fit"
    show_right_panel: bool = True
    auto_check_updates: bool = True
    last_update_check: float = 0.0   # unix time of the last automatic check
    skipped_version: str = ""        # a version the user chose to ignore
    sections_open: dict[str, bool] = field(default_factory=dict)

    @staticmethod
    def path() -> Path:
        return user_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "AppPrefs":
        p = cls.path()
        obj = cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for f in fields(cls):
                if f.name in data and isinstance(data[f.name], type(getattr(obj, f.name))):
                    setattr(obj, f.name, data[f.name])
        except (OSError, ValueError):
            pass
        if obj.theme not in ("system", "light", "dark"):
            obj.theme = "system"
        if obj.language not in ("en", "km"):
            obj.language = "en"
        return obj

    def save(self) -> None:
        try:
            p = self.path()
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(p, json.dumps(asdict(self), indent=2))
        except OSError:
            log.warning("could not save preferences")

    def add_recent(self, path: str) -> None:
        self.recent_projects = [path] + [r for r in self.recent_projects if r != path]
        self.recent_projects = self.recent_projects[:MAX_RECENT]

    def prune_recent(self) -> None:
        self.recent_projects = [r for r in self.recent_projects if Path(r).is_file()]
