"""Headless tests: hub, converter windows, PDF to Form window."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui

from tests.test_convert_docs import make_text_pdf, make_xlsx  # noqa: E402
from tests.test_forms import make_blank_form  # noqa: E402


def pump(app, seconds=1.5, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return bool(until and until())


@pytest.fixture
def hub(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path / "data"))
    from src.services.app_prefs import AppPrefs
    from src.ui.hub import HubWindow
    from src.ui.main_window import check_icon_path
    from src.ui.theme import apply_theme
    apply_theme(qapp, "light", check_icon_path())
    h = HubWindow(AppPrefs())
    h.show()
    pump(qapp, 0.3)
    yield h
    for w in list(h.windows.values()):
        if hasattr(w, "state"):
            w.state.dirty = False
        w.close()
    h.close()


def test_hub_lists_tools_and_title(hub):
    from src.ui.hub import TOOLS
    assert set(hub.tiles) == {t.key for t in TOOLS}
    assert "TL Studio Pro" in hub.windowTitle()
    assert not hub.tiles["convert"].soon


def test_open_each_tool_once(hub, qapp):
    for key in ("qr", "convert", "media", "form"):
        w1 = hub.open_tool(key)
        assert w1 is not None and w1.isVisible()
        assert hub.open_tool(key) is w1                      # raised, not duplicated
    assert "TL Studio Pro" in hub.windows["qr"].windowTitle()


def test_unavailable_tools_say_so(hub, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    assert hub.open_tool("ai") is None and shown
    hub.set_available("ai", True)
    hub.factories = {"ai": lambda prefs: __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()}
    assert hub.open_tool("ai") is not None


def test_theme_and_language_switch(hub, qapp):
    hub.toggle_theme()
    assert hub.mode == "dark" and hub.a_theme.text() == "Light mode"
    hub.set_language("km")
    assert hub.a_theme.text() == "របៀបភ្លឺ"
    hub.set_language("en")
    assert hub.a_theme.text() == "Light mode"


def _run(page, qapp, seconds=60):
    page.start()
    assert pump(qapp, seconds, lambda: not page._busy and bool(page.info.text()) and page.info.text() != "Working…")


def test_convert_studio_excel_to_pdf_and_merge(hub, qapp, tmp_path):
    w = hub.open_tool("convert")
    x = tmp_path / "b.xlsx"
    make_xlsx(x)
    page = w.pages["Excel → PDF"]
    page.files.add([x])
    page.out.setText(str(tmp_path))
    _run(page, qapp)
    assert page.results and page.results[0].suffix == ".pdf" and page.open_btn.isVisibleTo(page)
    # merge needs two files
    merge = w.pages["Merge PDF"]
    a, b = tmp_path / "a.pdf", tmp_path / "b2.pdf"
    make_text_pdf(a, 1)
    make_text_pdf(b, 1)
    assert not merge.run_btn.isEnabled()
    merge.files.add([a, b])
    assert merge.run_btn.isEnabled()
    merge.out.setText(str(tmp_path))
    _run(merge, qapp)
    assert merge.results[0].name.startswith("merged")


def test_one_bad_file_does_not_stop_the_rest(hub, qapp, tmp_path):
    w = hub.open_tool("convert")
    page = w.pages["PDF → Excel"]
    good, bad = tmp_path / "good.pdf", tmp_path / "bad.pdf"
    make_text_pdf(good, 1)
    bad.write_bytes(b"%PDF-1.4 junk")
    page.files.add([bad, good])
    page.out.setText(str(tmp_path))
    _run(page, qapp)
    assert len(page.results) == 1 and "bad.pdf" in page.info.text()


def test_convert_media_resize_and_bad_folder(hub, qapp, tmp_path):
    from PIL import Image
    w = hub.open_tool("media")
    img = tmp_path / "p.png"
    Image.new("RGB", (400, 200), "blue").save(img)
    page = w.pages["Resize"]
    page.files.add([img])
    page.out.setText(str(tmp_path / "missing"))
    page.start()
    assert "does not exist" in page.info.text()
    page.out.setText(str(tmp_path))
    page.get_opts()                                  # options widget builds
    for sp in page.findChildren(__import__("PySide6.QtWidgets", fromlist=["QSpinBox"]).QSpinBox):
        if sp.accessibleName() == "Width":
            sp.setValue(100)
    _run(page, qapp)
    assert Image.open(page.results[0]).size == (100, 50)


def test_files_box_filters_and_orders(hub, tmp_path):
    from src.ui.convert_widgets import FilesBox
    box = FilesBox((".pdf",), "PDF files", ordered=True)
    a, b, c = tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "c.txt"
    for f in (a, b, c):
        f.write_bytes(b"x")
    assert box.add([a, b, c, a]) == 2                # wrong type and duplicate ignored
    box.list.setCurrentRow(1)
    box.list.item(1).setSelected(True)
    box._move(-1)
    assert [p.name for p in box.files()] == ["b.pdf", "a.pdf"]
    box._remove()
    box.clear()
    assert box.files() == []
    single = FilesBox((".pdf",), "PDF", multi=False)
    single.add([a])
    single.add([b])
    assert [p.name for p in single.files()] == ["b.pdf"]


def test_pdf_to_form_window_roundtrip(hub, qapp, tmp_path):
    w = hub.open_tool("form")
    make = w.pages["Make a PDF fillable"]
    pdf = tmp_path / "form.pdf"
    make_blank_form(pdf)
    make.files.add([pdf])
    assert make.find_btn.isEnabled()
    make.out.setText(str(tmp_path))
    make.find()
    assert pump(qapp, 30, lambda: make.table.rowCount() > 0)
    assert make.make_btn.isEnabled() and make.preview.pixmap() is not None and not make.preview.pixmap().isNull()
    # untick one field
    make.table.item(0, 0).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Unchecked)
    assert make.specs[0].enabled is False
    make.create()
    assert pump(qapp, 30, lambda: make.out_path is not None)
    fill = w.pages["Fill a form"]
    fill.files.add([make.out_path])
    assert "full_name" not in fill.editors and fill.save_btn.isEnabled()     # the unticked field was not added
    key = "phone"
    fill.editors[key].setText("Sokha")
    fill.out.setText(str(tmp_path))
    fill.save()
    assert pump(qapp, 30, lambda: bool(fill.results))
    from src.convert.forms import list_form_fields
    assert {f.name: f.value for f in list_form_fields(fill.results[0])}[key] == "Sokha"


def test_fill_page_reports_non_form(hub, tmp_path):
    w = hub.open_tool("form")
    fill = w.pages["Fill a form"]
    pdf = tmp_path / "plain.pdf"
    make_text_pdf(pdf, 1)
    fill.files.add([pdf])
    assert not fill.save_btn.isEnabled() and "no fillable" in fill.info.text().lower()
