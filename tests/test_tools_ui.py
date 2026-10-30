"""Headless tests for the batch / print / template / recent dialogs and the new content pages."""
from __future__ import annotations

import pytest

from tests.test_ui import pump, window  # noqa: F401  (fixture)

pytestmark = pytest.mark.ui


def test_new_content_types_in_panel(window, qapp):
    cp = window.content_panel
    for key in ("geo", "event", "whatsapp", "telegram"):
        assert cp.type.findData(key) >= 0
    cp.type.setCurrentIndex(cp.type.findData("geo"))
    cp.geo_lat.setText("11.5564")
    cp.geo_lat.textEdited.emit("11.5564")
    cp.geo_lng.setText("104.9282")
    cp.geo_lng.textEdited.emit("104.9282")
    window.state.flush()
    assert window.state.settings.content.payload() == "geo:11.556400,104.928200"
    pump(qapp, 6, lambda: window.state.last_prep is not None and window.state.last_prep.qrm.payload.startswith("geo:"))
    assert window.state.last_prep.qrm.payload.startswith("geo:")


def test_template_applies_as_one_undo_step(window):
    from src.services.templates import TEMPLATES, apply_template
    before = window.state.settings.colors.foreground
    window._adopt(apply_template(window.state.settings, TEMPLATES[1]), "x")
    assert window.state.settings.frame.title == "SCAN FOR MENU"
    window.state.undo()
    assert window.state.settings.frame.title == "" and window.state.settings.colors.foreground == before


def test_template_gallery_lists_and_selects(window, qapp):
    from src.services.templates import TEMPLATES
    from src.ui.tools_dialogs import TemplateGallery
    dlg = TemplateGallery(window, window.state.settings)
    assert dlg.list.count() == len(TEMPLATES)
    pump(qapp, 6, lambda: not dlg.list.item(len(TEMPLATES) - 1).icon().isNull())
    assert not dlg.list.item(0).icon().isNull()
    dlg.list.setCurrentRow(3)
    dlg._accept()
    assert dlg.selected is TEMPLATES[3]


def test_batch_dialog_end_to_end(window, qapp, tmp_path):
    from src.ui.tools_dialogs import BatchDialog
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("content,filename\nhttps://a.example.com,alpha\nhttps://b.example.com,beta\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    window.state.settings.export.width_px = 400
    dlg = BatchDialog(window, window.state, window.prefs)
    dlg.out.setText(str(out))
    dlg.csv.setText(str(csv_path))
    dlg.load_csv(str(csv_path))
    assert len(dlg.rows) == 2 and dlg.start.isEnabled()
    dlg._go()
    pump(qapp, 30, lambda: hasattr(dlg, "result_report"))
    assert dlg.result_report.ok_count == 2
    assert (out / "alpha.png").exists() and (out / "beta.png").exists() and dlg.open_btn.isVisibleTo(dlg)


def test_batch_dialog_rejects_bad_csv(window, tmp_path):
    from src.ui.tools_dialogs import BatchDialog
    dlg = BatchDialog(window, window.state, window.prefs)
    bad = tmp_path / "bad.csv"
    bad.write_text("", encoding="utf-8")
    dlg.load_csv(str(bad))
    assert not dlg.start.isEnabled() and "empty" in dlg.info.text().lower()


def test_print_dialog_items(window, tmp_path):
    from src.ui.tools_dialogs import PrintSheetDialog
    dlg = PrintSheetDialog(window, window.state, window.prefs)
    dlg.copies.setValue(5)
    assert len(dlg.build_items()) == 5
    assert "per page" in dlg.info.text()
    csv_path = tmp_path / "p.csv"
    csv_path.write_text("a.example.com\nb.example.com\nc.example.com\n", encoding="utf-8")
    dlg._load(str(csv_path))
    assert dlg.r_csv.isChecked() and len(dlg.build_items()) == 3


def test_recent_dialog(window, qapp, tmp_path):
    from src.services.project_service import save_project
    from src.ui.tools_dialogs import RecentProjectsDialog
    p = save_project(window.state.settings, tmp_path / "demo.qrsp")
    window.prefs.add_recent(str(p))
    dlg = RecentProjectsDialog(window, window.prefs)
    assert dlg.list.count() == 1 and not dlg.empty.isVisibleTo(dlg)
    pump(qapp, 6, lambda: not dlg.list.item(0).icon().isNull())
    assert not dlg.list.item(0).icon().isNull()
    dlg._accept()
    assert dlg.chosen == str(p)


def test_recent_dialog_empty(window):
    from src.ui.tools_dialogs import RecentProjectsDialog
    window.prefs.recent_projects = []
    dlg = RecentProjectsDialog(window, window.prefs)
    assert dlg.list.count() == 0 and not dlg.open_btn.isEnabled()


def test_drop_csv_opens_batch(window, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(window, "open_batch", lambda p="": seen.append(p))
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    f = tmp_path / "x.csv"
    f.write_text("a.com\n")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(f))])
    window.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert seen == [str(f)]
