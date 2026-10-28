"""Shared mutable application state; panels edit `settings` and call edit()."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ..models.project_settings import ProjectSettings
from ..services.history import History


class AppState(QObject):
    changed = Signal()   # any edit -> re-render preview, update inspector
    loaded = Signal()    # settings replaced / bulk-changed -> panels must re-read all controls
    toast = Signal(str)  # transient status message
    meta = Signal()      # title / dirty flag / undo availability changed

    def __init__(self, settings: ProjectSettings | None = None):
        super().__init__()
        self.settings = settings or ProjectSettings()
        self.project_path: Path | None = None
        self.dirty = False
        self.content_error = ""     # latest payload validation message
        self.last_prep = None       # latest core.export_manager.Prepared (for the inspector)
        self.history = History(self.settings)
        self._timer = QTimer(self)  # coalesces slider drags / typing into one undo step
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._commit)

    # ------------------------------------------------------------------ editing
    def edit(self, refresh: bool = False) -> None:
        self.dirty = True
        self._timer.start()
        if refresh:
            self.loaded.emit()
        self.changed.emit()
        self.meta.emit()

    def _commit(self) -> None:
        self.history.push(self.settings)
        self.meta.emit()

    def flush(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._commit()

    def replace(self, settings: ProjectSettings, path: Path | None = None, dirty: bool = False,
                keep_history: bool = False) -> None:
        self._timer.stop()
        self.settings = settings
        self.project_path = path
        self.dirty = dirty
        if keep_history:
            self.history.push(settings)
        else:
            self.history.reset(settings)
        self.loaded.emit()
        self.changed.emit()
        self.meta.emit()

    def mark_saved(self, path: Path) -> None:
        self.project_path = path
        self.dirty = False
        self.meta.emit()

    # ------------------------------------------------------------------ undo / redo
    @property
    def can_undo(self) -> bool:
        return self.history.can_undo or self._timer.isActive()

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo

    def undo(self) -> None:
        self.flush()
        s = self.history.undo()
        if s is not None:
            self._apply_history(s)

    def redo(self) -> None:
        self.flush()
        s = self.history.redo()
        if s is not None:
            self._apply_history(s)

    def _apply_history(self, s: ProjectSettings) -> None:
        self.settings = s
        self.dirty = True
        self.loaded.emit()
        self.changed.emit()
        self.meta.emit()

    # ------------------------------------------------------------------ project level
    def new_project(self) -> None:
        self.replace(ProjectSettings())

    def reset_design(self) -> None:
        """Back to default style, keeping what is encoded."""
        self.flush()
        fresh = ProjectSettings()
        fresh.content = self.settings.content
        self.settings = fresh
        self.history.push(fresh)
        self.dirty = True
        self.loaded.emit()
        self.changed.emit()
        self.meta.emit()
