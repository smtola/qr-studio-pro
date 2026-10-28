"""Undo/redo over settings snapshots (pure Python)."""
from __future__ import annotations

import json

from ..models.project_settings import ProjectSettings


class History:
    def __init__(self, initial: ProjectSettings, limit: int = 100):
        self._limit = limit
        self._stack: list[str] = [self._dump(initial)]
        self._i = 0

    @staticmethod
    def _dump(s: ProjectSettings) -> str:
        return json.dumps(s.to_dict(), sort_keys=True)

    def push(self, s: ProjectSettings) -> bool:
        d = self._dump(s)
        if d == self._stack[self._i]:
            return False
        del self._stack[self._i + 1:]
        self._stack.append(d)
        if len(self._stack) > self._limit:
            self._stack.pop(0)
        self._i = len(self._stack) - 1
        return True

    def reset(self, s: ProjectSettings) -> None:
        self._stack, self._i = [self._dump(s)], 0

    @property
    def can_undo(self) -> bool:
        return self._i > 0

    @property
    def can_redo(self) -> bool:
        return self._i < len(self._stack) - 1

    def undo(self) -> ProjectSettings | None:
        if not self.can_undo:
            return None
        self._i -= 1
        return ProjectSettings.from_dict(json.loads(self._stack[self._i]))

    def redo(self) -> ProjectSettings | None:
        if not self.can_redo:
            return None
        self._i += 1
        return ProjectSettings.from_dict(json.loads(self._stack[self._i]))
