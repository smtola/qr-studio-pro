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
    for key in ("qr", "convert", "media", "form", "download", "ai"):
        w1 = hub.open_tool(key)
        assert w1 is not None and w1.isVisible()
        assert hub.open_tool(key) is w1                      # raised, not duplicated
    assert "TL Studio Pro" in hub.windows["qr"].windowTitle()


def test_unavailable_tools_say_so(hub, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    hub.set_available("ai", False)
    assert hub.open_tool("ai") is None and shown
    hub.set_available("ai", True)
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


def test_downloader_window_flow(hub, qapp, tmp_path, monkeypatch):
    w = hub.open_tool("download")
    assert not w.run_btn.isEnabled()
    w.urls.setPlainText("https://youtu.be/abc\nnot a link\nhttps://x.com/a/status/1")
    assert w.links() == ["https://youtu.be/abc", "https://x.com/a/status/1"]
    assert not w.run_btn.isEnabled()                       # rights box not ticked
    w.agree.setChecked(True)
    assert w.run_btn.isEnabled()
    w.out.setText(str(tmp_path))
    from src.convert.common import ConvertError

    def fake(url, out, kind, quality, afmt, progress=None, cancel=None):
        if "x.com" in url:
            raise ConvertError("This link needs a sign-in")
        p = out / "clip.mp4"
        p.write_bytes(b"1")
        progress(1.0, "")
        return [p]
    w.start(downloader=fake)
    assert pump(qapp, 10, lambda: not w._busy)
    assert [p.name for p in w.results] == ["clip.mp4"] and "sign-in" in w.info.text()
    w.kind.setCurrentIndex(1)
    assert w.afmt.isEnabled() and not w.quality.isEnabled()


def test_ai_window_chat_with_mock_api(hub, qapp, tmp_path, monkeypatch):
    import json
    from src.ai import keystore
    from src.ai.client import GroqClient
    from src.ui.ai_window import AIWindow
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    w = AIWindow(hub.prefs)
    w.work_dir = str(tmp_path)
    assert not w.send_btn.isEnabled() and not w.key_note.isHidden()      # no key yet
    keystore.save("gsk_abcdefghijklmnopqrstuvwxyz")
    w._refresh()
    assert w.send_btn.isEnabled()
    call = {"id": "1", "type": "function", "function": {"name": "make_qr", "arguments": json.dumps(
        {"type": "url", "value": "https://example.com", "filename": "z.png"})}}
    replies = [{"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}, "finish_reason": "tool_calls"}]},
               {"choices": [{"message": {"role": "assistant", "content": "All done <b>"}, "finish_reason": "stop"}]}]
    w.client_factory = lambda: GroqClient("gsk_k", "m", transport=lambda *a: (200, json.dumps(replies.pop(0)).encode()))
    w._confirm_override = lambda t: True
    w.input.setPlainText("make qr")
    w.send()
    assert pump(qapp, 20, lambda: not w._busy)
    assert (tmp_path / "z.png").exists()
    text = w.chat.toPlainText()
    assert "make qr" in text and "All done <b>" in text            # HTML is escaped, not rendered
    assert "gsk_" not in text
    w.close()


def test_ai_window_shows_friendly_error_and_keeps_history_clean(hub, qapp, tmp_path):
    from src.ai import keystore
    from src.ai.client import GroqClient
    from src.ui.ai_window import AIWindow
    keystore.save("gsk_abcdefghijklmnopqrstuvwxyz")
    w = AIWindow(hub.prefs)
    w.work_dir = str(tmp_path)
    w.client_factory = lambda: GroqClient("gsk_k", "m", transport=lambda *a: (401, b'{"error":{"message":"bad"}}'))
    w.input.setPlainText("hi")
    w.send()
    assert pump(qapp, 10, lambda: not w._busy)
    assert "rejected" in w.chat.toPlainText() and w.history == [] and w.send_btn.isEnabled()
    w.close()


def test_downloader_button_click_does_not_pass_bool(hub, qapp, tmp_path, monkeypatch):
    """Regression: clicked(bool) must not be taken as the downloader function."""
    w = hub.open_tool("download")
    w.urls.setPlainText("https://youtu.be/abc")
    w.agree.setChecked(True)
    w.out.setText(str(tmp_path))
    from src.convert import downloader as DL
    from src.convert.common import ConvertError

    def boom(*a, **k):
        raise ConvertError("stub")
    monkeypatch.setattr(DL, "download", boom)
    w.run_btn.click()
    assert pump(qapp, 10, lambda: not w._busy)
    assert "stub" in w.info.text() and "not callable" not in w.info.text()
