import pytest

from src import i18n

pytestmark = pytest.mark.ui
from tests.test_ui import pump, window  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _reset_lang():
    yield
    i18n.set_language("en")


def test_tr_basic():
    i18n.set_language("en")
    assert i18n.tr("Export") == "Export"
    i18n.set_language("km")
    assert i18n.tr("Export") == "នាំចេញ"
    assert i18n.tr("&Save".replace("&", "")) == "រក្សាទុក"
    assert i18n.tr("ⓘ  Enter the content to encode and the QR code will appear here.".replace("ⓘ  ", "ⓘ  ")).startswith("ⓘ")
    assert i18n.tr("Unknown thing 42") == "Unknown thing 42"


def test_every_km_value_is_khmer_or_symbol():
    import re
    for k, v in i18n.KM.items():
        assert v.strip(), k
        assert re.search(r"[ក-៿]|[A-Z]{2,}|✓|⚠", v), (k, v)


def test_window_switches_and_back(window, qapp):
    assert window.a_export.text() == "Export"
    window.set_language("km")
    assert window.a_export.text() == "នាំចេញ"
    assert window.sections["logo"].findChild(type(window.sections["logo"]._lbl), "h2").text() == "ឡូហ្គោ"
    assert window.content_panel.type.itemText(0) == "គេហទំព័រ (URL)"
    assert window.menuBar().actions()[0].text() == "ឯកសារ"
    window.toggle_theme()                      # dynamic text set by code is re-translated
    assert window.a_theme.text() in ("របៀបភ្លឺ", "របៀបងងឹត")
    window.set_language("en")
    assert window.a_export.text() == "Export"
    assert window.content_panel.type.itemText(0) == "Website URL"
    assert window.menuBar().actions()[0].text().replace("&", "") == "File"


def test_new_dialog_is_translated_on_show(window, qapp):
    window.set_language("km")
    from src.ui.tools_dialogs import PrintSheetDialog
    dlg = PrintSheetDialog(window, window.state, window.prefs)
    dlg.show()
    pump(qapp, 0.5)
    assert dlg.make.text() == "បង្កើត PDF…"
    dlg.close()


def test_pref_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path))
    from src.services.app_prefs import AppPrefs
    p = AppPrefs()
    p.language = "km"
    p.save()
    assert AppPrefs.load().language == "km"
    p.language = "xx"
    p.save()
    assert AppPrefs.load().language == "en"
