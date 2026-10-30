import pytest

from src.core.export_manager import prepare
from src.core.render_raster import render_raster
from src.models.project_settings import ProjectSettings
from src.services.templates import TEMPLATES, apply_template
from src.core.scan_check import OK, check_scan


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.name)
def test_every_template_renders_and_scans(tpl):
    base = ProjectSettings()
    base.logo.enabled = False
    base.content.url = "https://example.com/tpl"
    s = apply_template(base, tpl, with_sample=True)
    prep = prepare(s)
    assert not [a for a in prep.advice if a.level == "error"], [a.message for a in prep.advice]
    assert check_scan(prep, render_raster(prep.scene, 800)).status == OK


def test_apply_keeps_content_and_logo():
    base = ProjectSettings()
    base.content.url = "https://keep.me"
    base.logo.path = "/some/logo.png"
    base.export.width_px = 1234
    s = apply_template(base, TEMPLATES[1])
    assert s.content.url == "https://keep.me" and s.content.type == "url"
    assert s.logo.path == "/some/logo.png" and s.export.width_px == 1234
    assert s.frame.title == "SCAN FOR MENU"


def test_wifi_template_switches_type():
    wifi = next(t for t in TEMPLATES if t.content_type == "wifi")
    assert apply_template(ProjectSettings(), wifi).content.type == "wifi"
