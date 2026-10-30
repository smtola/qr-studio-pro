from src.core.export_manager import prepare
from src.core.render_raster import render_raster
from src.core.scan_check import FAIL, OK, check_scan
from src.models.project_settings import ProjectSettings


def _run(s):
    s.logo.enabled = False
    prep = prepare(s)
    return check_scan(prep, render_raster(prep.scene, 700))


def test_good_code_passes():
    assert _run(ProjectSettings()).status == OK


def test_framed_code_passes():
    s = ProjectSettings()
    s.frame.type, s.frame.title = "card", "SCAN ME"
    assert _run(s).status == OK


def test_unreadable_code_fails():
    s = ProjectSettings()
    s.colors.foreground, s.colors.background = "#DDDDDD", "#FFFFFF"
    assert _run(s).status == FAIL
