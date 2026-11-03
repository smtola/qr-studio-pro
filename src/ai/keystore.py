"""Local storage for the user's own Claude API key and model choice.

The key is kept in a file in the app's data folder that only the current user can read (best effort on Windows).
It is never logged, never shown in full and only ever sent to api.anthropic.com."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..services.project_service import atomic_write_text
from ..utils.paths import user_data_dir

DEFAULT_MODEL = "claude-sonnet-5-5"


def _path() -> Path:
    return user_data_dir() / "ai.json"


def load() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def get_key() -> str:
    return str(load().get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()


def get_model() -> str:
    return str(load().get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def save(api_key: str | None = None, model: str | None = None) -> None:
    d = load()
    if api_key is not None:
        d["api_key"] = api_key.strip()
    if model is not None:
        d["model"] = model.strip() or DEFAULT_MODEL
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(d))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def clear_key() -> None:
    d = load()
    d.pop("api_key", None)
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(d))


def looks_valid(key: str) -> bool:
    k = key.strip()
    return k.startswith("sk-ant-") and len(k) > 20 and " " not in k


def mask(key: str) -> str:
    return "" if not key else (key[:7] + "…" + key[-4:] if len(key) > 14 else "…")
