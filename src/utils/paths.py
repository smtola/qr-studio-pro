"""Per-user data locations (no admin rights needed) and bundled-resource lookup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..version import APP_NAME


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource both in dev checkouts and PyInstaller bundles."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath(*parts)


def user_data_dir() -> Path:
    override = os.environ.get("QRSP_DATA_DIR")  # used by tests / portable mode
    if override:
        return Path(override)
    home = Path.home()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME.replace(" ", "")
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "qr-studio-pro"


def presets_dir() -> Path:
    return user_data_dir() / "presets"


def log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    return user_data_dir() / "logs"
