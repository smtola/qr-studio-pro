import pytest

from src.models.project_settings import ContentSettings, ProjectSettings
from src.utils.validation import (ValidationError, build_event, build_geo, build_telegram, build_whatsapp,
                                  parse_datetime)
from tests.conftest import decode_qr as decode


def test_geo():
    assert build_geo("11.5564", "104.9282") == "geo:11.556400,104.928200"
    assert build_geo("11,5", "104") == "geo:11.500000,104.000000"
    for bad in (("abc", "1"), ("91", "0"), ("0", "181"), ("", "")):
        with pytest.raises(ValidationError):
            build_geo(*bad)


def test_event_timed_and_all_day():
    e = build_event("Launch, party", "2026-12-31 18:00", "", "Phnom Penh; Cambodia", "Bring friends")
    assert "SUMMARY:Launch" + chr(92) + ", party" in e and "DTSTART:20261231T180000" in e and "DTEND:20261231T190000" in e
    assert "LOCATION:Phnom Penh" + chr(92) + "; Cambodia" in e
    d = build_event("Holiday", "2026-04-14")
    assert "DTSTART;VALUE=DATE:20260414" in d and "DTEND;VALUE=DATE:20260415" in d


def test_event_errors():
    with pytest.raises(ValidationError):
        build_event("", "2026-01-01 10:00")
    with pytest.raises(ValidationError):
        build_event("x", "tomorrow")
    with pytest.raises(ValidationError):
        build_event("x", "2026-01-02 10:00", "2026-01-01 10:00")
    assert parse_datetime("2026-01-02T10:30").hour == 10


def test_whatsapp_and_telegram():
    assert build_whatsapp("+855 12 345 678") == "https://wa.me/85512345678"
    assert build_whatsapp("012345678", "Hello & welcome").endswith("?text=Hello%20%26%20welcome")
    with pytest.raises(ValidationError):
        build_whatsapp("12")
    assert build_telegram("@my_channel") == "https://t.me/my_channel"
    assert build_telegram("https://t.me/abcde") == "https://t.me/abcde"
    with pytest.raises(ValidationError):
        build_telegram("a")


@pytest.mark.parametrize("t,kw,starts", [
    ("geo", dict(geo_lat="11.5", geo_lng="104.9"), "geo:"),
    ("event", dict(event_title="Hi", event_start="2026-12-31 18:00"), "BEGIN:VEVENT"),
    ("whatsapp", dict(wa_number="+85512345678"), "https://wa.me/"),
    ("telegram", dict(telegram_user="@abcdef"), "https://t.me/")])
def test_payload_dispatch(t, kw, starts):
    c = ContentSettings(type=t, **kw)
    assert c.payload().startswith(starts)
    s = ProjectSettings()
    s.content = c
    assert ProjectSettings.from_dict(s.to_dict()).content.type == t


def test_new_module_styles_render_and_decode():
    from src.core.export_manager import prepare
    from src.core.render_raster import render_raster
    for style in ("small-dots", "gapped", "bars"):
        s = ProjectSettings()
        s.content.url = "https://example.com/styles"
        s.colors.module_style = style
        s.logo.enabled = False
        im = render_raster(prepare(s).scene, 700)
        assert decode(im) == "https://example.com/styles", style
