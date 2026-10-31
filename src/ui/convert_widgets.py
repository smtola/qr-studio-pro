"""Reusable building blocks for the converter windows: a file list with drag & drop, and a task page that runs
one conversion on a worker thread with progress, cancel and a results list."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..convert.common import ConvertError
from ..services.app_prefs import AppPrefs
from ..utils.logging_config import get_logger
from .widgets import muted

log = get_logger("convert-ui")


def exts_filter(label: str, exts: tuple[str, ...]) -> str:
    return f"{label} ({' '.join('*' + e for e in exts)});;All files (*)"


class FilesBox(QWidget):
    """Ordered list of input files. Accepts drops and a Browse dialog."""
    changed = Signal()

    def __init__(self, exts: tuple[str, ...], label: str, multi: bool = True, ordered: bool = False,
                 prefs: AppPrefs | None = None):
        super().__init__()
        self.exts, self.label, self.multi, self.prefs = exts, label, multi, prefs
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.list = QListWidget()
        self.list.setAccessibleName(f"{label} list")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMinimumHeight(110)
        self.list.setAlternatingRowColors(False)
        lay.addWidget(self.list, 1)
        self.hint = muted(f"Drop {label.lower()} here or click Add." if multi else f"Drop a {label.lower()} here or click Choose.")
        lay.addWidget(self.hint)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Add files…" if multi else "Choose file…")
        self.remove_btn = QPushButton("Remove")
        self.clear_btn = QPushButton("Clear")
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        row.addWidget(self.clear_btn)
        if ordered:
            self.up_btn, self.down_btn = QPushButton("Move up"), QPushButton("Move down")
            row.addWidget(self.up_btn)
            row.addWidget(self.down_btn)
            self.up_btn.clicked.connect(lambda: self._move(-1))
            self.down_btn.clicked.connect(lambda: self._move(1))
        row.addStretch(1)
        lay.addLayout(row)
        self.add_btn.clicked.connect(self._browse)
        self.remove_btn.clicked.connect(self._remove)
        self.clear_btn.clicked.connect(self.clear)

    # ---- API
    def files(self) -> list[Path]:
        return [Path(self.list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.list.count())]

    def add(self, paths: list[str | Path]) -> int:
        added = 0
        have = {str(p) for p in self.files()}
        for p in paths:
            p = Path(p)
            if self.exts and p.suffix.lower() not in self.exts:
                continue
            if not p.is_file() or str(p) in have:
                continue
            if not self.multi:
                self.list.clear()
                have.clear()
            it = QListWidgetItem(p.name)
            it.setToolTip(str(p))
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list.addItem(it)
            have.add(str(p))
            added += 1
        if added:
            self.changed.emit()
        return added

    def clear(self) -> None:
        self.list.clear()
        self.changed.emit()

    def _remove(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self.changed.emit()

    def _move(self, d: int) -> None:
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}, reverse=d > 0)
        for r in rows:
            n = r + d
            if 0 <= n < self.list.count():
                self.list.insertItem(n, self.list.takeItem(r))
                self.list.item(n).setSelected(True)
        self.changed.emit()

    def _browse(self) -> None:
        start = (self.prefs.last_project_dir if self.prefs else "") or str(Path.home())
        flt = exts_filter(self.label, self.exts) if self.exts else "All files (*)"
        if self.multi:
            paths, _ = QFileDialog.getOpenFileNames(self, f"Add {self.label}", start, flt)
        else:
            p, _ = QFileDialog.getOpenFileName(self, f"Choose {self.label}", start, flt)
            paths = [p] if p else []
        if paths and self.prefs:
            self.prefs.last_project_dir = str(Path(paths[0]).parent)
        self.add(paths)

    # ---- drag & drop
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        self.add([u.toLocalFile() for u in e.mimeData().urls()])
        e.acceptProposedAction()


class _Sig(QObject):
    progress = Signal(int, int)
    done = Signal(object, list, str)       # outputs, [(name, error)], fatal error


class _Run(QRunnable):
    def __init__(self, fn, sig: _Sig):
        super().__init__()
        self.fn, self.sig = fn, sig

    def run(self) -> None:
        try:
            outs, fails = self.fn(self.sig.progress.emit)
            self._emit(outs, fails, "")
        except ConvertError as e:
            self._emit([], [], str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("conversion crashed")
            self._emit([], [], f"Something went wrong: {e}")

    def _emit(self, *a) -> None:
        try:
            self.sig.done.emit(*a)
        except RuntimeError:           # window closed meanwhile
            pass


class TaskPage(QWidget):
    """One conversion. `worker(files, out_dir, opts, progress, cancel) -> list[Path]` is called on a thread.
    If `per_file` is True the worker is called once per input so one bad file cannot stop the rest."""

    def __init__(self, title: str, description: str, files: FilesBox, worker: Callable, *, options: QWidget | None = None,
                 get_opts: Callable[[], dict] | None = None, per_file: bool = True, run_text: str = "Convert",
                 min_files: int = 1, needs: Callable[[], str] | None = None, prefs: AppPrefs | None = None):
        super().__init__()
        self.title, self.worker, self.per_file, self.min_files = title, worker, per_file, min_files
        self.files, self.get_opts, self.needs, self.prefs = files, get_opts or (lambda: {}), needs, prefs
        self.results: list[Path] = []
        self._cancel = threading.Event()
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(10)
        h = QLabel(title)
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(muted(description))
        self.note = QLabel()
        self.note.setObjectName("warn")
        self.note.setWordWrap(True)
        self.note.hide()
        lay.addWidget(self.note)
        lay.addWidget(files, 1)
        if options is not None:
            lay.addWidget(options)
        orow = QHBoxLayout()
        self.out = QLineEdit()
        self.out.setPlaceholderText("Save next to the original file (or choose a folder…)")
        self.out.setAccessibleName("Output folder")
        self.out_btn = QPushButton("Browse…")
        orow.addWidget(self.out, 1)
        orow.addWidget(self.out_btn)
        lay.addLayout(orow)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setAccessibleName("Conversion status")
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        brow = QHBoxLayout()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.hide()
        self.run_btn = QPushButton(run_text)
        self.run_btn.setProperty("primary", True)
        brow.addWidget(self.open_btn)
        brow.addStretch(1)
        brow.addWidget(self.cancel_btn)
        brow.addWidget(self.run_btn)
        lay.addLayout(brow)
        if needs is not None:
            msg = needs()
            if msg:
                self.note.setText(msg)
                self.note.show()
        self.out_btn.clicked.connect(self._pick_out)
        self.run_btn.clicked.connect(self.start)
        self.cancel_btn.clicked.connect(self._cancel.set)
        self.open_btn.clicked.connect(self._open_folder)
        files.changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self.run_btn.setEnabled(len(self.files.files()) >= self.min_files and not self._busy)

    def _pick_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out.text() or str(Path.home()))
        if d:
            self.out.setText(d)

    def out_dir_for(self, files: list[Path]) -> Path:
        t = self.out.text().strip()
        return Path(t) if t else files[0].parent

    def _open_folder(self) -> None:
        if self.results:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results[0].parent)))

    def _say(self, text: str, error: bool = False) -> None:
        self.info.setObjectName("error" if error else "muted")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)
        self.info.setText(text)

    def start(self) -> None:
        files = self.files.files()
        if len(files) < self.min_files or self._busy:
            return
        out_dir = self.out_dir_for(files)
        if not out_dir.is_dir():
            self._say(f"The folder '{out_dir}' does not exist.", error=True)
            return
        opts = self.get_opts()
        self._cancel.clear()
        self._busy = True
        self.results = []
        self.open_btn.hide()
        self.run_btn.setEnabled(False)
        self.cancel_btn.show()
        self.bar.setRange(0, 0)
        self.bar.show()
        self._say("Working…")
        cancel = self._cancel

        def run(emit):
            outs: list[Path] = []
            fails: list[tuple[str, str]] = []
            if not self.per_file:
                r = self.worker(files, out_dir, opts, lambda i, n: emit(i, n), cancel)
                return (r if isinstance(r, list) else [r]), fails
            for i, f in enumerate(files):
                if cancel.is_set():
                    break
                emit(i, len(files))
                try:
                    r = self.worker([f], out_dir, opts, lambda a, b: None, cancel)
                    outs += r if isinstance(r, list) else [r]
                except ConvertError as e:
                    fails.append((f.name, str(e)))
            emit(len(files), len(files))
            return outs, fails

        sig = _Sig()
        self._sig = sig
        sig.progress.connect(self._progress)
        sig.done.connect(self._finished)
        QThreadPool.globalInstance().start(_Run(run, sig))

    def _progress(self, i: int, n: int) -> None:
        if n:
            self.bar.setRange(0, n)
            self.bar.setValue(i)

    def _finished(self, outs, fails, fatal: str) -> None:
        self._busy = False
        self.bar.hide()
        self.cancel_btn.hide()
        self._refresh()
        if fatal:
            self._say(fatal, error=True)
            return
        self.results = [Path(p) for p in outs]
        msg = f"Done: {len(outs)} file(s) created." if outs else "Nothing was created."
        if self._cancel.is_set():
            msg += " (cancelled)"
        if fails:
            msg += " Problems: " + "; ".join(f"{n}: {e}" for n, e in fails[:3]) + (" …" if len(fails) > 3 else "")
        if outs:
            msg += "\n" + ", ".join(p.name for p in self.results[:4]) + (" …" if len(outs) > 4 else "")
            self.open_btn.show()
        self._say(msg, error=bool(fails) and not outs)
        self.finished_ok = bool(outs)


class _CallSig(QObject):
    done = Signal(object, str)


class _CallJob(QRunnable):
    def __init__(self, fn, sig: _CallSig):
        super().__init__()
        self.fn, self.sig = fn, sig

    def run(self) -> None:
        try:
            res, err = self.fn(), ""
        except ConvertError as e:
            res, err = None, str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("background call crashed")
            res, err = None, f"Something went wrong: {e}"
        try:
            self.sig.done.emit(res, err)
        except RuntimeError:
            pass


class AsyncCall(QObject):
    """Run `fn()` on a worker thread; `on_done(result, error)` is called on the GUI thread."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.busy = False

    def start(self, fn, on_done) -> None:
        sig = _CallSig()
        self._sig = sig
        self.busy = True

        def finish(res, err):
            self.busy = False
            on_done(res, err)
        sig.done.connect(finish)
        QThreadPool.globalInstance().start(_CallJob(fn, sig))
