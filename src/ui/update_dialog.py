"""Update check (background thread), 'update available' dialog and download/install flow."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..services.app_prefs import AppPrefs
from ..services.updater import (UpdateError, UpdateInfo, check_for_update, download_asset, manifest_url,
                                start_installer)
from ..utils.logging_config import get_logger
from ..version import APP_NAME, VERSION

log = get_logger("update-ui")
AUTO_CHECK_INTERVAL = 24 * 3600


class _Sig(QObject):
    checked = Signal(object, str)       # UpdateInfo | None, error text
    progress = Signal(int, int)
    downloaded = Signal(object, str)    # Path | None, error text


class _CheckJob(QRunnable):
    def __init__(self, sig: _Sig):
        super().__init__()
        self.sig = sig

    def run(self) -> None:
        try:
            self.sig.checked.emit(check_for_update(), "")
        except UpdateError as e:
            self.sig.checked.emit(None, str(e))
        except Exception as e:  # noqa: BLE001 - a failed check must never crash the app
            log.exception("update check failed")
            self.sig.checked.emit(None, f"Update check failed: {e}")


class _DownloadJob(QRunnable):
    def __init__(self, asset, sig: _Sig, flag: dict):
        super().__init__()
        self.asset, self.sig, self.flag = asset, sig, flag

    def run(self) -> None:
        try:
            path = download_asset(self.asset, progress=self.sig.progress.emit, cancelled=lambda: self.flag["cancel"])
            self.sig.downloaded.emit(path, "")
        except UpdateError as e:
            self.sig.downloaded.emit(None, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("update download failed")
            self.sig.downloaded.emit(None, f"The download failed: {e}")


class UpdateDialog(QDialog):
    """Shows release notes; 'Update now' downloads, verifies and starts the installer."""

    def __init__(self, parent: QWidget, info: UpdateInfo, prefs: AppPrefs):
        super().__init__(parent)
        self.info, self.prefs = info, prefs
        self.asset = info.asset_for_this_computer()
        self.flag = {"cancel": False}
        self.sig = _Sig()
        self.sig.progress.connect(self._progress)
        self.sig.downloaded.connect(self._downloaded)
        self.setWindowTitle(f"{APP_NAME} – update available")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        title = QLabel(f"<b>Version {info.version} is available</b><br>You are using version {VERSION}.")
        title.setAccessibleName("Update available")
        lay.addWidget(title)
        notes = QTextBrowser()
        notes.setPlainText(info.notes or "No release notes were provided.")
        notes.setAccessibleName("Release notes")
        notes.setMinimumHeight(130)
        lay.addWidget(notes)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.skip = QPushButton("Skip this version")
        self.later = QPushButton("Later")
        self.go = QPushButton("Update now" if self.asset else "Open download page")
        self.go.setProperty("primary", True)
        self.go.setDefault(True)
        row.addWidget(self.skip)
        row.addStretch(1)
        row.addWidget(self.later)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.later.clicked.connect(self.reject)
        self.skip.clicked.connect(self._skip)
        self.go.clicked.connect(self._start)
        if self.asset is None and not info.page:
            self.go.setEnabled(False)
            self.status.setText("No installer is published for this computer yet.")
        elif self.asset is None:
            self.status.setText("There is no automatic installer for this system; the download page will open.")

    def _skip(self) -> None:
        self.prefs.skipped_version = self.info.version
        self.prefs.save()
        self.reject()

    def reject(self) -> None:
        self.flag["cancel"] = True
        super().reject()

    def _start(self) -> None:
        if self.asset is None:
            QDesktopServices.openUrl(QUrl(self.info.page))
            self.accept()
            return
        self.go.setEnabled(False)
        self.skip.setEnabled(False)
        self.bar.setRange(0, 0)
        self.bar.show()
        self.status.setText("Downloading the update…")
        QThreadPool.globalInstance().start(_DownloadJob(self.asset, self.sig, self.flag))

    def _progress(self, done: int, total: int) -> None:
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
        self.status.setText(f"Downloading… {done / 1048576:.1f}" + (f" / {total / 1048576:.1f} MB" if total else " MB"))

    def _downloaded(self, path: Path | None, error: str) -> None:
        if not self.isVisible() and path is None:
            return
        if path is None:
            self.bar.hide()
            self.go.setEnabled(True)
            self.skip.setEnabled(True)
            self.status.setText(error)
            return
        self.status.setText("Download verified. Starting the installer…")
        win = self.parent()
        # Let the user save first: the Windows installer closes the app.
        if win is not None and hasattr(win, "_confirm_discard") and not win._confirm_discard():
            self.status.setText("Update cancelled. The downloaded file will be removed.")
            self.go.setEnabled(True)
            return
        try:
            action = start_installer(path)
        except (UpdateError, OSError) as e:
            self.status.setText(f"The installer could not be started: {e}")
            self.go.setEnabled(True)
            return
        self.accept()
        if action == "quit":
            if win is not None and hasattr(win, "state"):
                win.state.dirty = False     # already confirmed above
            QApplication.quit()
        else:
            QMessageBox.information(self.parent(), "Finish the update",
                                    "The update disk image has been opened.\n\nDrag “QR Studio Pro” onto the "
                                    "Applications folder and choose Replace, then start the app again.")


class UpdateController(QObject):
    """Owns the background check; the main window calls check(manual=...)."""

    def __init__(self, window: QWidget, prefs: AppPrefs):
        super().__init__(window)
        self.window, self.prefs = window, prefs
        self.sig = _Sig()
        self.sig.checked.connect(self._on_checked)
        self._manual = False
        self._busy = False

    def auto_check_due(self) -> bool:
        return bool(manifest_url()) and self.prefs.auto_check_updates and \
            time.time() - self.prefs.last_update_check > AUTO_CHECK_INTERVAL

    def check(self, manual: bool) -> None:
        if self._busy:
            return
        if not manifest_url():
            if manual:
                QMessageBox.information(self.window, "Check for updates",
                                        f"You are using {APP_NAME} {VERSION}.\n\nUpdate checking is not set up for this "
                                        "build (no update address was configured by the publisher).")
            return
        self._manual, self._busy = manual, True
        if manual:
            self.window.statusBar().showMessage("Checking for updates…")
        QThreadPool.globalInstance().start(_CheckJob(self.sig))

    def _on_checked(self, info: UpdateInfo | None, error: str) -> None:
        self._busy = False
        if not error:
            self.prefs.last_update_check = time.time()
            self.prefs.save()
        if error:
            log.info("update check: %s", error)
            if self._manual:
                QMessageBox.warning(self.window, "Check for updates", error)
            return
        if info is None:
            if self._manual:
                self.window.statusBar().clearMessage()
                QMessageBox.information(self.window, "Check for updates",
                                        f"You have the latest version ({VERSION}).")
            return
        if not self._manual and info.version == self.prefs.skipped_version:
            return
        self.window.statusBar().showMessage(f"Version {info.version} is available (Help ▸ Check for Updates).", 15000)
        UpdateDialog(self.window, info, self.prefs).exec()
