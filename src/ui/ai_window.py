"""AI Agent: a chat that can run TL Studio Pro's tools, using the user's own Groq API key."""
from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from ..ai import keystore
from ..ai.agent import run_turn
from ..ai.client import AIError, GroqClient
from ..ai.tools import Toolbox
from ..i18n import tr
from ..services.app_prefs import AppPrefs
from ..utils.logging_config import get_logger
from .widgets import form, muted

log = get_logger("ai-ui")

PRIVACY = ("Your messages and the tool results are sent to Groq (groq.com) using your own API key. File contents are not sent "
           "unless a tool reads them. The agent can only use files inside the work folder, and asks before it writes or downloads.")


class _Sig(QObject):
    event = Signal(str, str)
    ask = Signal(str)
    done = Signal(str, str)         # answer, error


class _Job(QRunnable):
    def __init__(self, fn, sig: _Sig):
        super().__init__()
        self.fn, self.sig = fn, sig

    def run(self) -> None:
        try:
            ans, err = self.fn(), ""
        except AIError as e:
            ans, err = "", str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("agent crashed")
            ans, err = "", f"Something went wrong: {type(e).__name__}"
        try:
            self.sig.done.emit(ans, err)
        except RuntimeError:
            pass


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("AI settings"))
        lay = QVBoxLayout(self)
        lay.addWidget(muted(tr("Use your own Groq API key (from console.groq.com/keys). It is stored only on this computer "
                               "and sent only to Groq.")))
        f = form()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setAccessibleName("API key")
        self.key.setPlaceholderText(keystore.mask(keystore.get_key()) or "gsk_…")
        self.model = QLineEdit(keystore.get_model())
        self.model.setAccessibleName("Model")
        f.addRow(tr("API key"), self.key)
        f.addRow(tr("Model"), self.model)
        lay.addLayout(f)
        self.err = QLabel()
        self.err.setObjectName("error")
        lay.addWidget(self.err)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.remove = bb.addButton(tr("Remove key"), QDialogButtonBox.ButtonRole.DestructiveRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        self.remove.clicked.connect(self._remove)
        lay.addWidget(bb)

    def _save(self) -> None:
        k = self.key.text().strip()
        if k and not keystore.looks_valid(k):
            self.err.setText(tr("That does not look like a Groq API key (it starts with gsk_)."))
            return
        keystore.save(k if k else None, self.model.text())
        self.accept()

    def _remove(self) -> None:
        keystore.clear_key()
        self.key.clear()
        self.key.setPlaceholderText("gsk_…")


class AIWindow(QMainWindow):
    def __init__(self, prefs: AppPrefs, client_factory=None, confirm=None):
        super().__init__()
        self.prefs = prefs
        self.client_factory = client_factory or (lambda: GroqClient(keystore.get_key(), keystore.get_model()))
        self._confirm_override = confirm
        self.setWindowTitle("AI Agent")
        self.resize(860, 700)
        self.setMinimumSize(640, 520)
        self.history: list[dict] = []
        self._busy = False
        self._cancel = threading.Event()
        self._answer = threading.Event()
        self._allowed = False
        self.work_dir = prefs.last_export_dir if prefs.last_export_dir and Path(prefs.last_export_dir).is_dir() else str(Path.home())
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QWidget()
        card.setObjectName("toolCard")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        h = QLabel("AI Agent")
        h.setObjectName("h2")
        top.addWidget(h)
        top.addStretch(1)
        self.settings_btn = QPushButton("Settings")
        self.new_btn = QPushButton("New chat")
        top.addWidget(self.new_btn)
        top.addWidget(self.settings_btn)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.addWidget(QLabel("Work folder:"))
        self.folder = QLineEdit(self.work_dir)
        self.folder.setReadOnly(True)
        self.folder.setAccessibleName("Work folder")
        self.folder_btn = QPushButton("Change…")
        self.open_btn = QPushButton("Open")
        row.addWidget(self.folder, 1)
        row.addWidget(self.folder_btn)
        row.addWidget(self.open_btn)
        lay.addLayout(row)
        self.key_note = QLabel()
        self.key_note.setObjectName("warn")
        self.key_note.setWordWrap(True)
        lay.addWidget(self.key_note)
        self.chat = QTextBrowser()
        self.chat.setAccessibleName("Conversation")
        self.chat.setOpenLinks(False)
        lay.addWidget(self.chat, 1)
        lay.addWidget(muted(PRIVACY))
        self.status = QLabel()
        self.status.setObjectName("muted")
        lay.addWidget(self.status)
        irow = QHBoxLayout()
        self.input = _Input()
        self.input.setAccessibleName("Message")
        self.input.setPlaceholderText(tr("Ask in plain words, for example: make a QR code for https://example.com"))
        self.input.setFixedHeight(70)
        self.send_btn = QPushButton("Send")
        self.send_btn.setProperty("primary", True)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.hide()
        col = QVBoxLayout()
        col.addWidget(self.send_btn)
        col.addWidget(self.stop_btn)
        irow.addWidget(self.input, 1)
        irow.addLayout(col)
        lay.addLayout(irow)
        self.setCentralWidget(root)

        self.send_btn.clicked.connect(self.send)
        self.input.submit.connect(self.send)
        self.stop_btn.clicked.connect(self._stop)
        self.settings_btn.clicked.connect(self._settings)
        self.new_btn.clicked.connect(self._new_chat)
        self.folder_btn.clicked.connect(self._pick_folder)
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.work_dir)))
        self._welcome()
        self._refresh()

    # ---- UI helpers
    def _welcome(self) -> None:
        self.chat.clear()
        self._add("assistant", tr("Hi! Tell me what to do with your files: make QR codes, convert Excel/Word/PDF, convert pictures "
                                  "or videos, fill PDF forms, or download media you have the right to keep. I will ask before I change anything."))

    def _add(self, who: str, text: str) -> None:
        label = {"user": tr("You"), "assistant": "AI", "tool": tr("Tool"), "error": tr("Error")}.get(who, who)
        colour = {"user": "#3E6A93", "error": "#C0392B", "tool": "#7A7A7A"}.get(who, "#2E7D5B")
        body = html.escape(text).replace("\n", "<br>")
        self.chat.append(f'<p><b style="color:{colour}">{html.escape(label)}</b><br>{body}</p>')
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _refresh(self) -> None:
        has_key = bool(keystore.get_key())
        self.key_note.setVisible(not has_key)
        self.key_note.setText(tr("Add your Groq API key in Settings to start chatting."))
        self.send_btn.setEnabled(has_key and not self._busy)

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def _settings(self) -> None:
        SettingsDialog(self).exec()
        self._refresh()

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Work folder"), self.work_dir)
        if d:
            self.work_dir = d
            self.folder.setText(d)
            self.prefs.last_export_dir = d

    def _new_chat(self) -> None:
        if self._busy:
            return
        self.history.clear()
        self._welcome()

    def _stop(self) -> None:
        self._cancel.set()
        self._allowed = False
        self._answer.set()
        self._say(tr("Stopping…"))

    # ---- confirm (worker thread asks, GUI thread answers)
    def _confirm_from_worker(self, text: str) -> bool:
        if self._confirm_override is not None:
            return bool(self._confirm_override(text))
        self._answer.clear()
        self._allowed = False
        self._sig.ask.emit(text)
        self._answer.wait()
        return self._allowed and not self._cancel.is_set()

    def _on_ask(self, text: str) -> None:
        r = QMessageBox.question(self, tr("Allow this action?"), text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        self._allowed = r == QMessageBox.StandardButton.Yes
        self._answer.set()

    # ---- run
    def send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self._busy or not keystore.get_key():
            return
        folder = Path(self.work_dir)
        if not folder.is_dir():
            self._add("error", tr("The work folder does not exist."))
            return
        self.input.clear()
        self._add("user", text)
        self._busy = True
        self._cancel.clear()
        self.send_btn.setEnabled(False)
        self.stop_btn.show()
        self._say(tr("Thinking…"))
        sig = _Sig()
        self._sig = sig
        sig.event.connect(self._on_event)
        sig.ask.connect(self._on_ask)
        sig.done.connect(self._finished)
        client = self.client_factory()
        toolbox = Toolbox(folder, self._confirm_from_worker, self._cancel)
        self._toolbox = toolbox
        cancel = self._cancel

        def work() -> str:
            return run_turn(client, toolbox, self.history, text, lambda k, v: self._emit(sig, k, v), cancel)
        QThreadPool.globalInstance().start(_Job(work, sig))

    @staticmethod
    def _emit(sig: _Sig, kind: str, text: str) -> None:
        try:
            sig.event.emit(kind, text)
        except RuntimeError:
            pass

    def _on_event(self, kind: str, text: str) -> None:
        if kind == "text":
            self._add("assistant", text)
        elif kind == "tool":
            self._say(tr("Running") + f" {text}…")
        elif kind == "result":
            self._add("tool", text[:600])

    def _finished(self, answer: str, error: str) -> None:
        self._busy = False
        self.stop_btn.hide()
        self._say("")
        if error:
            self._add("error", error)
            if self.history and self.history[-1]["role"] == "user" and isinstance(self.history[-1]["content"], str):
                self.history.pop()                     # failed turn: let the user retry cleanly
        elif answer:
            self._add("assistant", answer)
        self._refresh()

    def closeEvent(self, e) -> None:
        self._cancel.set()
        self._allowed = False
        self._answer.set()
        super().closeEvent(e)


class _Input(QPlainTextEdit):
    submit = Signal()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)


def ai_agent(prefs: AppPrefs) -> AIWindow:
    return AIWindow(prefs)
