import json
import shutil

import pytest

from src.models.project_settings import ProjectSettings
from src.services import preset_service
from src.services.app_prefs import AppPrefs
from src.services.history import History
from src.services.project_service import load_project, save_project
from src.utils.validation import ValidationError


def test_roundtrip_preserves_everything(settings, tmp_path, logo_png):
    settings.content.url = "https://khmer.example/ស្វាគមន៍"
    settings.logo.path = str(logo_png)
    settings.frame.type, settings.frame.title = "badge", "SCAN ME"
    settings.eyes.follow_foreground, settings.eyes.outer_color = False, "#B91C1C"
    p = save_project(settings, tmp_path / "a.qrsp")
    res = load_project(p)
    assert not res.logo_missing and not res.logo_changed
    assert res.settings.frame.type == "badge" and res.settings.eyes.outer_color == "#B91C1C"
    assert res.settings.content.url == settings.content.url
    assert res.settings.logo.path == str(logo_png.resolve())


def test_project_stores_references_not_pixels(settings, tmp_path, logo_png):
    settings.logo.path = str(logo_png)
    p = save_project(settings, tmp_path / "a.qrsp")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["logo"]["relative_path"] == "logo.png" and len(data["logo"]["sha256"]) == 64
    assert p.stat().st_size < 20_000


def test_moved_project_finds_logo_via_relative_path(settings, tmp_path, logo_png):
    a = tmp_path / "proj"
    a.mkdir()
    shutil.copy(logo_png, a / "logo.png")
    settings.logo.path = str(a / "logo.png")
    save_project(settings, a / "p.qrsp")
    b = tmp_path / "moved"
    shutil.copytree(a, b)
    shutil.rmtree(a)
    res = load_project(b / "p.qrsp")
    assert not res.logo_missing and res.settings.logo.path == str((b / "logo.png").resolve())


def test_missing_logo_is_reported_not_fatal(settings, tmp_path, logo_png):
    settings.logo.path = str(logo_png)
    p = save_project(settings, tmp_path / "a.qrsp")
    logo_png.unlink()
    res = load_project(p)
    assert res.logo_missing and res.logo_reference
    assert res.settings.content.url == settings.content.url


def test_changed_logo_detected(settings, tmp_path, logo_png):
    settings.logo.path = str(logo_png)
    p = save_project(settings, tmp_path / "a.qrsp")
    logo_png.write_bytes(logo_png.read_bytes() + b"\0")
    assert load_project(p).logo_changed


@pytest.mark.parametrize("text", ["", "not json", "[1,2]", '{"schema_version": 99}', "\xff\xfe"])
def test_malformed_projects_rejected(tmp_path, text):
    p = tmp_path / "bad.qrsp"
    p.write_text(text, encoding="latin-1")
    with pytest.raises(ValidationError):
        load_project(p)


def test_missing_project_file(tmp_path):
    with pytest.raises(ValidationError):
        load_project(tmp_path / "none.qrsp")


def test_tampered_values_are_sanitised(tmp_path):
    p = tmp_path / "t.qrsp"
    p.write_text(json.dumps({"logo": {"size_pct": 999, "backing": "weird", "backing_color": "javascript"},
                             "frame": {"type": "x", "thickness": -5, "font_size": "big"},
                             "export": {"width_px": 10**9}, "unknown": 1}))
    s = load_project(p).settings
    assert s.logo.size_pct == 25 and s.logo.backing == "rounded" and s.logo.backing_color == "#FFFFFF"
    assert s.frame.type == "none" and s.frame.thickness == 0 and s.frame.font_size == 44
    assert s.export.width_px == 6000


def test_preset_save_list_apply(settings, tmp_path, logo_png):
    settings.colors.foreground = "#0B3D91"
    settings.frame.type, settings.frame.title = "cta", "SCAN ME"
    settings.logo.path = str(logo_png)
    path = preset_service.save_preset("ACME Brand", settings, tmp_path)
    assert [n for n, _ in preset_service.list_presets(tmp_path)] == ["ACME Brand"]
    other = ProjectSettings()
    other.content.url = "https://other.example"
    applied = preset_service.apply_preset_file(other, path)
    assert applied.content.url == "https://other.example", "content is not part of a brand preset"
    assert applied.colors.foreground == "#0B3D91" and applied.frame.type == "cta"
    assert applied.logo.path == str(logo_png)
    no_logo = preset_service.apply_preset_file(other, path, apply_logo=False)
    assert no_logo.logo.path == ""


def test_preset_rejects_foreign_files(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"hello": 1}')
    with pytest.raises(ValidationError):
        preset_service.load_preset_file(p)
    with pytest.raises(ValidationError):
        preset_service.save_preset("   !!!  ", ProjectSettings(), tmp_path)


def test_prefs_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path))
    prefs = AppPrefs.load()
    prefs.theme, prefs.last_export_dir = "dark", "/x/y"
    prefs.add_recent("/a.qrsp")
    prefs.add_recent("/b.qrsp")
    prefs.add_recent("/a.qrsp")
    prefs.save()
    again = AppPrefs.load()
    assert again.theme == "dark" and again.last_export_dir == "/x/y"
    assert again.recent_projects == ["/a.qrsp", "/b.qrsp"]


def test_prefs_survive_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text("{{{")
    assert AppPrefs.load().theme == "system"


def test_history_undo_redo():
    s = ProjectSettings()
    h = History(s)
    s.colors.foreground = "#112233"
    assert h.push(s) and not h.push(s)
    s.colors.foreground = "#445566"
    h.push(s)
    assert h.undo().colors.foreground == "#112233"
    assert h.undo().colors.foreground == "#111111" and h.undo() is None
    assert h.redo().colors.foreground == "#112233"
    s.colors.foreground = "#778899"
    h.push(s)   # branching discards redo
    assert not h.can_redo
