"""Main window: toolbar, settings sidebar, live preview and properties inspector."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (QLabel, QApplication, QFileDialog, QInputDialog, QMainWindow, QMenu, QMessageBox, QScrollArea,
                               QSizePolicy, QSplitter, QToolBar, QVBoxLayout, QWidget)

from .. import i18n
from ..core.export_manager import Prepared
from ..models.project_settings import ProjectSettings
from ..services.app_prefs import AppPrefs
from ..services.preset_service import apply_preset_file, list_presets, save_preset
from ..services.project_service import load_project, save_project
from ..services.templates import apply_template
from ..utils.logging_config import get_logger
from ..utils.paths import resource_path
from ..utils.validation import ValidationError
from ..version import APP_NAME, PROJECT_EXT, VERSION
from .color_panel import ColorPanel, EyePanel
from .content_panel import ContentPanel
from .export_dialog import ExportSection, run_export
from .frame_panel import FramePanel
from .icons import icon
from .logo_panel import LogoPanel
from .preview_panel import PreviewPanel
from .properties_panel import PropertiesPanel
from .state import AppState
from .tools_dialogs import BatchDialog, PrintSheetDialog, RecentProjectsDialog, TemplateGallery
from .theme import apply_theme, resolve_mode, tokens
from .update_dialog import UpdateController
from .widgets import CollapsibleSection

log = get_logger("window")
PROJECT_FILTER = f"QR Studio project (*{PROJECT_EXT});;JSON (*.json)"
PRESET_FILTER = "QR Studio brand preset (*.json)"


def check_icon_path() -> str:
    return resource_path("assets", "ui", "check.svg").as_posix()


class MainWindow(QMainWindow):
    def __init__(self, prefs: AppPrefs | None = None, state: AppState | None = None) -> None:
        super().__init__()
        self.prefs = prefs or AppPrefs.load()
        self.state = state or AppState()
        i18n.install(QApplication.instance(), self.prefs.language)
        self.mode = resolve_mode(self.prefs.theme)
        self.setAcceptDrops(True)
        self.resize(1480, 920)
        self.setMinimumSize(1060, 640)

        # ---- panels ---------------------------------------------------------
        self.content_panel = ContentPanel(self.state)
        self.logo_panel = LogoPanel(self.state, self.prefs)
        self.color_panel = ColorPanel(self.state)
        self.eye_panel = EyePanel(self.state)
        self.frame_panel = FramePanel(self.state)
        self.export_section = ExportSection(self.state)
        self.export_section.button.clicked.connect(self.export_design)

        self.sections: dict[str, CollapsibleSection] = {}
        body = QWidget()
        sl = QVBoxLayout(body)
        sl.setContentsMargins(10, 10, 10, 10)
        sl.setSpacing(10)
        for key, title, widget, default, ico in (
            ("content", "Content", self.content_panel, True, "link"),
            ("logo", "Logo", self.logo_panel, True, "image"),
            ("colors", "QR Colors", self.color_panel, False, "palette"),
            ("eyes", "Finder Eyes", self.eye_panel, False, "qr"),
            ("frame", "Frame Designer", self.frame_panel, False, "frame"),
            ("export", "Export", self.export_section, False, "export"),
        ):
            sec = CollapsibleSection(title, widget, self.prefs.sections_open.get(key, default), ico)
            sec.toggled.connect(lambda on, k=key: self._remember_section(k, on))
            sl.addWidget(sec)
            self.sections[key] = sec
        sl.addStretch(1)
        self.sidebar = QScrollArea()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setWidget(body)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setMinimumWidth(390)
        self.sidebar.setMaximumWidth(500)
        self.sidebar.setAccessibleName("Settings")

        self.preview = PreviewPanel(self.state, self.mode)
        self.props = PropertiesPanel(self.state)
        self.props.setMinimumWidth(270)
        self.props.setMaximumWidth(400)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.sidebar)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(4, 10, 4, 10)
        wl.addWidget(self.preview)
        self.splitter.addWidget(wrap)
        self.splitter.addWidget(self.props)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([400, 760, 320])
        self.setCentralWidget(self.splitter)
        self.props.setVisible(self.prefs.show_right_panel)

        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self._apply_icons()

        self.preview.rendered.connect(self._on_rendered)
        self.state.meta.connect(self._update_actions)
        self.state.meta.connect(self._update_title)
        self.state.toast.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.statusBar().showMessage("Ready – everything runs offline on your computer.")
        self.version_label = QLabel(f"v{VERSION}")
        self.version_label.setObjectName("muted")
        self.version_label.setAccessibleName(f"Application version {VERSION}")
        self.statusBar().addPermanentWidget(self.version_label)
        self.updates = UpdateController(self, self.prefs)
        if self.updates.auto_check_due():
            QTimer.singleShot(4000, lambda: self.updates.check(manual=False))

        if self.prefs.geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.prefs.geometry.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass
        self._update_title()
        self._update_actions()
        self.preview.render_now()

    # ===== actions ===============================================================
    def _act(self, text: str, slot, shortcut=None, ic: str = "", tip: str = "") -> QAction:
        a = QAction(text, self)
        a.triggered.connect(lambda _=False: slot())
        if isinstance(shortcut, list):
            a.setShortcuts([QKeySequence(x) for x in shortcut])
        elif shortcut:
            a.setShortcut(shortcut)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setProperty("iconName", ic)
        return a

    def _build_actions(self) -> None:
        S = QKeySequence.StandardKey
        self.a_new = self._act("New", self.new_project, S.New, "new", "Start a new QR project")
        self.a_open = self._act("Open…", self.open_project_dialog, S.Open, "open", "Open a saved project")
        self.a_save = self._act("Save", self.save_project_action, S.Save, "save", "Save the project")
        self.a_save_as = self._act("Save As…", lambda: self.save_project_action(True), S.SaveAs, "", "Save under a new name")
        self.a_load_preset = self._act("Open Preset…", self.open_preset_file, "Ctrl+Shift+O", "open", "Load a brand preset file")
        self.a_save_preset = self._act("Save Preset…", self.save_preset_action, "Ctrl+Shift+S", "preset", "Save the current style as a brand preset")
        self.a_templates = self._act("Design Templates…", self.open_templates, "Ctrl+Shift+T", "layout",
                                     "Start from a ready-made design")
        self.a_batch = self._act("Batch Generate from CSV…", self.open_batch, "Ctrl+B", "",
                                 "Create many QR codes from a CSV file")
        self.a_sheet = self._act("Create Print Sheet…", self.open_print_sheet, "Ctrl+Shift+L", "",
                                 "Arrange QR codes on an A4 / Letter PDF with cut guides")
        self.a_recent = self._act("Recent Projects…", self.open_recent_dialog, "Ctrl+Alt+O", "",
                                  "Browse recent projects with thumbnails")
        self.a_undo = self._act("Undo", self.state.undo, S.Undo, "undo", "Undo the last change")
        self.a_redo = self._act("Redo", self.state.redo, S.Redo, "redo", "Redo")
        self.a_reset = self._act("Reset", self.reset_design, "Ctrl+Shift+R", "reset", "Reset the design to defaults (keeps your content)")
        self.a_export = self._act("Export", self.export_design, "Ctrl+E", "export", "Export the QR code")
        self.a_theme = self._act("Dark mode", self.toggle_theme, "Ctrl+T", "moon", "Switch between light and dark themes")
        self.a_logo = self._act("Upload Center Logo…", self.logo_panel.choose_logo, "Ctrl+L", "upload", "Choose a logo for the centre")
        self.a_fit = self._act("Fit to Window", self.preview.fit, "Ctrl+0", "fit")
        self.a_zin = self._act("Zoom In", lambda: self.preview.step(1), ["Ctrl++", "Ctrl+="], "zoom-in")
        self.a_zout = self._act("Zoom Out", lambda: self.preview.step(-1), "Ctrl+-", "zoom-out")
        self.lang_actions: dict[str, QAction] = {}
        self.lang_group = QActionGroup(self)
        for code, label in i18n.LANGUAGES:
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(code == self.prefs.language)
            a.triggered.connect(lambda _=False, c=code: self.set_language(c))
            self.lang_group.addAction(a)
            self.lang_actions[code] = a
        self.a_props = self._act("Properties Panel", self.toggle_props, "Ctrl+Shift+P")
        self.a_props.setCheckable(True)
        self.a_props.setChecked(self.prefs.show_right_panel)
        self.a_about = self._act("About", self.about)
        self.a_update = self._act("Check for Updates…", lambda: self.updates.check(manual=True), None, "",
                                  "Look for a newer version of QR Studio Pro")
        self.a_update.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        self.a_auto_update = self._act("Check for updates automatically", self.toggle_auto_update)
        self.a_auto_update.setCheckable(True)
        self.a_auto_update.setChecked(self.prefs.auto_check_updates)
        self.a_quit = self._act("Quit", self.close, S.Quit)
        self.a_quit.setMenuRole(QAction.MenuRole.QuitRole)
        for a in (self.a_logo, self.a_fit, self.a_zin, self.a_zout, self.a_props, self.a_reset):
            self.addAction(a)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setAccessibleName("Main toolbar")
        self.addToolBar(tb)
        for a in (self.a_new, self.a_open, self.a_save):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_templates)
        tb.addAction(self.a_save_preset)
        tb.addSeparator()
        for a in (self.a_undo, self.a_redo, self.a_reset):
            tb.addAction(a)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.a_theme)
        tb.addSeparator()
        tb.addAction(self.a_export)
        tb.widgetForAction(self.a_export).setObjectName("exportButton")
        self.toolbar = tb

    def _build_menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("&File")
        f.addActions([self.a_new, self.a_open])
        self.recent_menu = QMenu("Open Recent", self)
        f.addMenu(self.recent_menu)
        f.addAction(self.a_recent)
        f.addSeparator()
        f.addActions([self.a_save, self.a_save_as])
        f.addSeparator()
        f.addAction(self.a_export)
        f.addAction(self.a_batch)
        f.addAction(self.a_sheet)
        f.addSeparator()
        f.addAction(self.a_quit)
        f.aboutToShow.connect(self._fill_recent)
        e = mb.addMenu("&Edit")
        e.addActions([self.a_undo, self.a_redo])
        e.addSeparator()
        e.addAction(self.a_logo)
        e.addAction(self.a_reset)
        p = mb.addMenu("&Presets")
        p.addAction(self.a_templates)
        p.addSeparator()
        p.addActions([self.a_save_preset, self.a_load_preset])
        self.preset_menu = QMenu("Saved Presets", self)
        p.addMenu(self.preset_menu)
        p.aboutToShow.connect(self._fill_presets)
        v = mb.addMenu("&View")
        v.addActions([self.a_fit, self.a_zin, self.a_zout])
        v.addSeparator()
        v.addActions([self.a_props, self.a_theme])
        lm = v.addMenu("Language")
        lm.addActions(list(self.lang_actions.values()))
        h = mb.addMenu("&Help")
        h.addAction(self.a_update)
        h.addAction(self.a_auto_update)
        h.addSeparator()
        h.addAction(self.a_about)

    def _apply_icons(self) -> None:
        color = tokens(self.mode)["icon"]
        for sec in self.sections.values():
            sec.retint(color)
        for a in (self.a_new, self.a_open, self.a_save, self.a_load_preset, self.a_save_preset, self.a_undo, self.a_redo,
                  self.a_reset, self.a_logo, self.a_templates, self.a_fit, self.a_zin, self.a_zout):
            name = a.property("iconName")
            if name:
                a.setIcon(icon(name, color))
        self.a_theme.setIcon(icon("sun" if self.mode == "dark" else "moon", color))
        self.a_theme.setText("Light mode" if self.mode == "dark" else "Dark mode")
        self.a_export.setIcon(icon("export", tokens(self.mode)["accent_text"]))
        self.setWindowIcon(self._app_icon())

    @staticmethod
    def _app_icon() -> QIcon:
        p = resource_path("assets", "icons", "app.png")
        return QIcon(str(p)) if p.exists() else QIcon()

    def _update_actions(self) -> None:
        self.a_undo.setEnabled(self.state.can_undo)
        self.a_redo.setEnabled(self.state.can_redo)

    def _update_title(self) -> None:
        name = self.state.project_path.name if self.state.project_path else "Untitled"
        self.setWindowTitle(f"{'• ' if self.state.dirty else ''}{name} – {APP_NAME} {VERSION}")

    def _on_rendered(self, prep: Prepared | None, error: str) -> None:
        self.props.show_prep(prep, error)
        self.content_panel.show_status(error, prep.ecc_used if prep else None)
        if prep is None:
            self.statusBar().showMessage(error or "Nothing to show yet.")
            return
        warns = sum(1 for a in prep.advice if a.level in ("warning", "error"))
        self.statusBar().showMessage(
            f"{prep.qrm.size}×{prep.qrm.size} modules, error correction {prep.ecc_used}  –  "
            + (f"{warns} scan-reliability note{'s' if warns != 1 else ''} (see Properties)" if warns
               else "no scan-reliability concerns found"))

    def _remember_section(self, key: str, on: bool) -> None:
        self.prefs.sections_open[key] = on

    # ===== project handling =====================================================
    def _confirm_discard(self) -> bool:
        if not self.state.dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved changes")
        box.setText("Save your changes to this project first?")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project_action()
        return box.clickedButton() is discard

    def new_project(self) -> None:
        if self._confirm_discard():
            self.state.new_project()

    def open_project_dialog(self) -> None:
        if not self._confirm_discard():
            return
        start = self.prefs.last_project_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, PROJECT_FILTER)
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> bool:
        try:
            result = load_project(path)
        except ValidationError as exc:
            QMessageBox.warning(self, "Project could not be opened", str(exc))
            self.prefs.prune_recent()
            return False
        self.state.replace(result.settings, Path(path))
        self.prefs.add_recent(path)
        self.prefs.last_project_dir = str(Path(path).parent)
        self.prefs.save()
        if result.logo_changed:
            QMessageBox.information(self, "Logo changed", "The logo file differs from the one used when this project "
                                    "was saved. Check that the preview still looks right.")
        if result.logo_missing:
            self.sections["logo"].set_expanded(True)
            r = QMessageBox.question(self, "Logo not found", f"The logo file for this project was moved or deleted:\n"
                                     f"{result.logo_reference}\n\nSelect it again now?")
            if r == QMessageBox.StandardButton.Yes:
                self.logo_panel.choose_logo()
        return True

    def save_project_action(self, save_as: bool = False) -> bool:
        self.state.flush()
        path = self.state.project_path
        if save_as or path is None:
            start = Path(self.prefs.last_project_dir or Path.home()) / (path.name if path else f"my-qr-code{PROJECT_EXT}")
            chosen, _ = QFileDialog.getSaveFileName(self, "Save project", str(start), PROJECT_FILTER)
            if not chosen:
                return False
            path = Path(chosen)
            if not path.suffix:
                path = path.with_suffix(PROJECT_EXT)
        try:
            saved = save_project(self.state.settings, path)
        except ValidationError as exc:
            QMessageBox.critical(self, "Project could not be saved", str(exc))
            return False
        self.state.mark_saved(saved)
        self.prefs.add_recent(str(saved))
        self.prefs.last_project_dir = str(saved.parent)
        self.prefs.save()
        self.statusBar().showMessage(f"Saved {saved.name}", 4000)
        return True

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        self.prefs.prune_recent()
        if not self.prefs.recent_projects:
            self.recent_menu.addAction("No recent projects").setEnabled(False)
            return
        for p in self.prefs.recent_projects:
            act = self.recent_menu.addAction(Path(p).name)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, path=p: self._open_recent(path))

    def _open_recent(self, path: str) -> None:
        if self._confirm_discard():
            self.open_project(path)

    def reset_design(self) -> None:
        r = QMessageBox.question(self, "Reset design", "Reset colours, logo style, frame and export settings to their "
                                 "defaults?\nYour content is kept. You can undo this.")
        if r == QMessageBox.StandardButton.Yes:
            self.state.reset_design()

    # ===== presets ===================================================================
    def save_preset_action(self) -> None:
        name, ok = QInputDialog.getText(self, "Save brand preset", "Preset name:", text="My brand")
        if not ok or not name.strip():
            return
        try:
            path = save_preset(name.strip(), self.state.settings)
        except ValidationError as exc:
            QMessageBox.warning(self, "Preset could not be saved", str(exc))
            return
        self.statusBar().showMessage(f"Preset saved: {path.name}", 4000)

    def open_preset_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open preset", str(Path.home()), PRESET_FILTER)
        if path:
            self.apply_preset(path)

    def apply_preset(self, path: str) -> None:
        try:
            new: ProjectSettings = apply_preset_file(self.state.settings, path)
        except ValidationError as exc:
            QMessageBox.warning(self, "Preset could not be loaded", str(exc))
            return
        self._adopt(new, f"Applied preset: {Path(path).stem}")

    def _adopt(self, new: ProjectSettings, message: str) -> None:
        """Replace the settings with `new` as one undoable step."""
        self.state.flush()
        self.state.settings = new
        self.state.history.push(new)
        self.state.dirty = True
        self.state.loaded.emit()
        self.state.changed.emit()
        self.state.meta.emit()
        self.statusBar().showMessage(message, 4000)

    # ===== productivity tools =========================================================
    def open_templates(self) -> None:
        self.state.flush()
        dlg = TemplateGallery(self, self.state.settings)
        if dlg.exec() and dlg.selected is not None:
            self._adopt(apply_template(self.state.settings, dlg.selected), f"Applied template: {dlg.selected.name}")

    def open_batch(self, csv_path: str = "") -> None:
        dlg = BatchDialog(self, self.state, self.prefs)
        if csv_path:
            dlg.csv.setText(csv_path)
            dlg.load_csv(csv_path)
        dlg.exec()
        self.prefs.save()

    def open_print_sheet(self) -> None:
        PrintSheetDialog(self, self.state, self.prefs).exec()
        self.prefs.save()

    def open_recent_dialog(self) -> None:
        dlg = RecentProjectsDialog(self, self.prefs)
        if dlg.exec() and dlg.chosen and self._confirm_discard():
            self.open_project(dlg.chosen)

    def _fill_presets(self) -> None:
        self.preset_menu.clear()
        items = list_presets()
        if not items:
            self.preset_menu.addAction("No saved presets yet").setEnabled(False)
        for name, p in items:
            self.preset_menu.addAction(name).triggered.connect(lambda _=False, path=str(p): self.apply_preset(path))

    # ===== misc =======================================================================
    def export_design(self) -> None:
        run_export(self, self.state, self.prefs)

    def toggle_theme(self) -> None:
        self.mode = "dark" if self.mode == "light" else "light"
        self.prefs.theme = self.mode
        self.prefs.save()
        apply_theme(QApplication.instance(), self.mode, check_icon_path())
        self.preview.set_theme(self.mode)
        self._apply_icons()
        i18n.retranslate(self)

    def set_language(self, code: str) -> None:
        self.prefs.language = code
        self.prefs.save()
        i18n.set_language(code)
        self.lang_actions[code].setChecked(True)
        i18n.retranslate(self)
        self.preview.request()

    def toggle_auto_update(self) -> None:
        self.prefs.auto_check_updates = self.a_auto_update.isChecked()
        self.prefs.save()

    def toggle_props(self) -> None:
        on = self.a_props.isChecked()
        self.props.setVisible(on)
        self.prefs.show_right_panel = on
        self.prefs.save()

    def about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME}</b><br>Version {VERSION}<br><br>Design QR codes with a centre logo, brand colours, "
                          "finder-eye styling and frames.<br>Everything is processed locally on your computer; nothing is "
                          "uploaded.<br><br>No QR code can be guaranteed to scan in every situation. Always test the final "
                          "design with real phones.")

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            low = p.lower()
            if low.endswith((".png", ".jpg", ".jpeg", ".svg")):
                self.logo_panel.set_logo_file(p)
                self.sections["logo"].set_expanded(True)
            elif low.endswith(".csv"):
                self.open_batch(p)
            elif low.endswith((PROJECT_EXT, ".json")) and self._confirm_discard():
                self.open_project(p)
            else:
                continue
            e.acceptProposedAction()
            return

    def closeEvent(self, e: QCloseEvent) -> None:
        if not self._confirm_discard():
            e.ignore()
            return
        self.prefs.geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.prefs.save()
        e.accept()
