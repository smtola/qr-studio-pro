"""Headless GUI tests (Qt offscreen)."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui


def pump(app, seconds: float = 1.5, until=None) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until and until():
            return
        time.sleep(0.01)


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path / "data"))
    from src.services.app_prefs import AppPrefs
    from src.ui.main_window import MainWindow, check_icon_path
    from src.ui.theme import apply_theme
    apply_theme(qapp, "light", check_icon_path())
    w = MainWindow(AppPrefs())
    w.resize(1400, 900)
    w.show()
    pump(qapp, 5, lambda: w.state.last_prep is not None)
    yield w
    w.state.dirty = False
    w.close()


def test_preview_renders_on_start(window):
    assert window.state.last_prep is not None
    assert window.preview.canvas.pixmap is not None


def test_logo_upload_forces_high_ecc_and_centres_logo(window, qapp, logo_png):
    assert window.logo_panel.set_logo_file(str(logo_png))
    pump(qapp, 5, lambda: window.state.last_prep.logo is not None)
    prep = window.state.last_prep
    assert prep.logo is not None and prep.ecc_used == "H"
    x, y, w, h = prep.scene.logo_box
    sx, sy, sw, sh = prep.scene.symbol
    assert abs((x + w / 2) - (sx + sw / 2)) < 1 and abs((y + h / 2) - (sy + sh / 2)) < 1


def test_bad_logo_is_rejected_without_changing_settings(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert window.logo_panel.set_logo_file(str(bad)) is False
    assert window.state.settings.logo.path == ""


def test_color_preset_and_custom_hex(window, qapp):
    cp = window.color_panel
    cp.preset.setCurrentIndex(cp.preset.findData("Corporate Blue"))
    assert window.state.settings.colors.foreground == "#0B3D91"
    cp.fg.edit.textEdited.emit("#112233")
    cp.fg.edit.setText("#112233")
    cp.fg._typed("#112233")
    assert window.state.settings.colors.foreground == "#112233"
    assert window.state.settings.colors.preset == "Custom Brand Colors"


def test_frame_text_and_type(window, qapp):
    fp = window.frame_panel
    fp.type.setCurrentIndex(fp.type.findData("cta"))
    fp.title.setText("SCAN ME")
    fp.title.textEdited.emit("SCAN ME")
    pump(qapp, 5, lambda: window.state.last_prep.settings.frame.title == "SCAN ME")
    p = window.state.last_prep
    assert p.settings.frame.type == "cta" and p.settings.frame.title == "SCAN ME"
    assert p.scene.text_boxes  # text laid out outside the QR block


def test_invalid_content_shows_error_and_keeps_app_alive(window, qapp):
    window.state.settings.content.url = "http://"
    window.state.edit(refresh=True)
    pump(qapp, 5, lambda: window.state.content_error != "")
    assert window.state.content_error
    assert window.content_panel.error.isVisibleTo(window.content_panel)


def test_undo_redo_and_reset_keep_content(window, qapp):
    st = window.state
    st.settings.colors.foreground = "#222222"
    st.edit(refresh=True)
    st.flush()
    st.undo()
    assert st.settings.colors.foreground != "#222222"
    st.redo()
    assert st.settings.colors.foreground == "#222222"
    st.settings.content.url = "https://keep.example"
    st.reset_design()
    assert st.settings.colors.foreground == "#111111"
    assert st.settings.content.url == "https://keep.example"


def test_theme_toggle(window, qapp):
    before = window.mode
    window.toggle_theme()
    assert window.mode != before
    window.toggle_theme()
    assert window.mode == before


def test_project_roundtrip_through_window(window, qapp, tmp_path, logo_png):
    window.logo_panel.set_logo_file(str(logo_png))
    window.state.settings.frame.type = "badge"
    window.state.edit(refresh=True)
    path = tmp_path / "p.qrsp"
    from src.services.project_service import load_project, save_project
    save_project(window.state.settings, path)
    assert window.open_project(str(path))
    assert window.state.settings.frame.type == "badge"
    assert window.state.settings.logo.path.endswith("logo.png")


def test_export_via_core_from_window_state(window, tmp_path):
    from src.core.export_manager import export_to_file
    for fmt in ("png", "jpg", "svg", "pdf"):
        r = export_to_file(window.state.settings, tmp_path / f"o.{fmt}")
        assert r.path.exists() and r.size_bytes > 500


def test_version_visible_and_update_dialog_appears(window, qapp, monkeypatch):
    import http.server, json, threading
    from src.version import VERSION
    from src.ui import update_dialog as ud
    assert window.version_label.text() == f"v{VERSION}"
    assert VERSION in window.windowTitle()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            body = json.dumps({"version": "99.0.0", "notes": "Shiny", "page": "https://example.com/r"}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("QRSP_UPDATE_URL", f"http://127.0.0.1:{srv.server_port}/update.json")
    # the production check is https-only; allow the loopback test server only for this test
    from src.services import updater
    orig = updater.check_for_update
    monkeypatch.setattr(ud, "check_for_update", lambda: orig(allow_insecure=True))
    shown = []
    monkeypatch.setattr(ud.UpdateDialog, "exec", lambda self: shown.append(self.info.version))
    window.updates.check(manual=True)
    pump(qapp, 5, lambda: shown)
    srv.shutdown()
    assert shown == ["99.0.0"]
    assert window.prefs.last_update_check > 0


def test_manual_check_without_feed_explains(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from src.ui import update_dialog as ud
    monkeypatch.delenv("QRSP_UPDATE_URL", raising=False)
    monkeypatch.setattr(ud, "manifest_url", lambda: "")    # simulate a build with no feed configured
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[2]))
    window.updates.check(manual=True)
    assert msgs and "not set up" in msgs[0]


def test_scan_badge_reports_ok(window, qtbot_wait=None):
    import time
    from PySide6.QtWidgets import QApplication
    window.preview.render_now()
    t = time.time()
    while time.time() - t < 8 and window.preview.last_scan is None:
        QApplication.processEvents()
    assert window.preview.last_scan is not None and window.preview.last_scan.status == "ok"
    assert window.preview.scan_badge.text().startswith("✓")
