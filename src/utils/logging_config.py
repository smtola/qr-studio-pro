"""Structured (JSON-lines) logging to a rotating file in the user's log directory plus stderr."""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path

from ..version import APP_SLUG
from .paths import log_dir


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "ctx", None)
        if extra:
            data["ctx"] = extra
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, to_file: bool = True) -> Path | None:
    root = logging.getLogger(APP_SLUG)
    if root.handlers:
        return None
    root.setLevel(level)
    root.propagate = False
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)
    log_path = None
    if to_file:
        try:
            d = log_dir()
            d.mkdir(parents=True, exist_ok=True)
            log_path = d / "app.log"
            fh = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=512_000, backupCount=2, encoding="utf-8")
            fh.setFormatter(JsonFormatter())
            root.addHandler(fh)
        except OSError:
            log_path = None  # logging must never prevent the app from starting
    return log_path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{APP_SLUG}.{name}")
