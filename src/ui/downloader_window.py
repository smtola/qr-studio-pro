"""Media Downloader: paste public links, choose video / audio / picture, save to a folder."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..convert import downloader as DL
from ..convert.common import ConvertError
from ..services.app_prefs import AppPrefs
from .convert_widgets import _Run, _Sig
from .widgets import combo, form, muted


class DownloaderWindow(QMainWindow):
    def __init__(self, prefs: AppPrefs):
        super().__init__()
        self.prefs = prefs
        self.setWindowTitle("Download Image & Video")
        self.resize(820, 640)
        self.setMinimumSize(640, 520)
        self.results: list[Path] = []
        self._busy = False
        self._cancel = threading.Event()
        root = QWidget()
        card = QWidget()
        card.setObjectName("toolCard")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        h = QLabel("Download Image & Video")
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(muted("Paste public links from YouTube, TikTok, Facebook, Instagram or X (one per line)."))
        self.rights = QLabel(DL.RIGHTS_NOTICE)
        self.rights.setObjectName("warn")
        self.rights.setWordWrap(True)
        lay.addWidget(self.rights)
        self.agree = QCheckBox("I own this content or have permission to download it")
        lay.addWidget(self.agree)

        self.urls = QPlainTextEdit()
        self.urls.setAccessibleName("Links")
        self.urls.setPlaceholderText("https://…")
        self.urls.setMinimumHeight(110)
        lay.addWidget(self.urls, 1)

        f = form()
        self.kind = combo("Download as", [("Video (MP4)", "video"), ("Audio only", "audio"), ("Picture / thumbnail", "image")])
        self.quality = combo("Quality", [("Best available", "best"), ("Up to 1080p", "1080"), ("Up to 720p", "720"),
                                         ("Up to 480p", "480"), ("Up to 360p", "360")])
        self.afmt = combo("Audio format", [("MP3", "mp3"), ("M4A", "m4a")])
        f.addRow("Download as", self.kind)
        f.addRow("Quality", self.quality)
        f.addRow("Audio format", self.afmt)
        lay.addLayout(f)

        row = QHBoxLayout()
        self.out = QLineEdit(self._default_dir())
        self.out.setAccessibleName("Save to folder")
        self.out_btn = QPushButton("Browse…")
        row.addWidget(self.out, 1)
        row.addWidget(self.out_btn)
        lay.addLayout(row)

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setAccessibleName("Download status")
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        b = QHBoxLayout()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.hide()
        self.run_btn = QPushButton("Download")
        self.run_btn.setProperty("primary", True)
        b.addWidget(self.open_btn)
        b.addStretch(1)
        b.addWidget(self.cancel_btn)
        b.addWidget(self.run_btn)
        lay.addLayout(b)
        self.setCentralWidget(root)

        self.out_btn.clicked.connect(self._pick)
        self.run_btn.clicked.connect(lambda _checked=False: self.start())
        self.cancel_btn.clicked.connect(self._cancel.set)
        self.open_btn.clicked.connect(self._open)
        self.agree.toggled.connect(self._refresh)
        self.urls.textChanged.connect(self._refresh)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()
        self._refresh()

    # ---- helpers
    def _default_dir(self) -> str:
        for c in (self.prefs.last_export_dir, str(Path.home() / "Downloads"), str(Path.home())):
            if c and Path(c).is_dir():
                return c
        return ""

    def links(self) -> list[str]:
        return DL.split_urls(self.urls.toPlainText())

    def _kind_changed(self) -> None:
        k = self.kind.currentData()
        self.quality.setEnabled(k == "video")
        self.afmt.setEnabled(k == "audio")

    def _refresh(self) -> None:
        self.run_btn.setEnabled(bool(self.links()) and self.agree.isChecked() and not self._busy)

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Save to folder", self.out.text() or str(Path.home()))
        if d:
            self.out.setText(d)

    def _open(self) -> None:
        if self.results:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results[0].parent)))

    def _say(self, text: str, error: bool = False) -> None:
        self.info.setObjectName("error" if error else "muted")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)
        self.info.setText(text)

    # ---- run
    def start(self, downloader=None) -> None:
        downloader = downloader or DL.download
        links = self.links()
        if not links or self._busy or not self.agree.isChecked():
            return
        out = Path(self.out.text().strip())
        if not out.is_dir():
            self._say(f"The folder '{out}' does not exist.", error=True)
            return
        self.prefs.last_export_dir = str(out)
        kind, quality, afmt = self.kind.currentData(), self.quality.currentData(), self.afmt.currentData()
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
        sig = _Sig()
        self._sig = sig
        sig.progress.connect(self._progress)
        sig.done.connect(self._finished)
        n = len(links)

        def run(emit):
            outs: list[Path] = []
            fails: list[tuple[str, str]] = []
            for i, url in enumerate(links):
                if cancel.is_set():
                    break
                emit(i * 100, n * 100)
                try:
                    outs += downloader(url, out, kind, quality, afmt,
                                       progress=lambda frac, _s, i=i: emit(int((i + frac) * 100), n * 100), cancel=cancel)
                except ConvertError as e:
                    fails.append((DL.detect_platform(url) + " link", str(e)))
            emit(n * 100, n * 100)
            return outs, fails

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
        msg = f"Done: {len(outs)} file(s) saved." if outs else "Nothing was downloaded."
        if self._cancel.is_set():
            msg += " (cancelled)"
        if fails:
            msg += " Problems: " + "; ".join(f"{a}: {b}" for a, b in fails[:3]) + (" …" if len(fails) > 3 else "")
        if outs:
            msg += "\n" + ", ".join(p.name for p in self.results[:3]) + (" …" if len(outs) > 3 else "")
            self.open_btn.show()
        self._say(msg, error=bool(fails) and not outs)


def media_downloader(prefs: AppPrefs) -> DownloaderWindow:
    return DownloaderWindow(prefs)
