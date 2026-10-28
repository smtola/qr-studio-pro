import pytest

from src.core.export_manager import prepare, render_image
from src.core.qr_generator import generate_matrix
from src.models.project_settings import ProjectSettings
from src.utils.validation import ValidationError, normalize_url
from conftest import decode_qr


def roundtrip(s: ProjectSettings, width: int = 900) -> str:
    return decode_qr(render_image(prepare(s), width))


def test_url_encoding_roundtrip(settings):
    settings.content.url = "https://www.example.com/path?a=1&b=two#frag"
    assert roundtrip(settings) == "https://www.example.com/path?a=1&b=two#frag"


def test_url_without_scheme_gets_https():
    assert normalize_url("example.com/x") == "https://example.com/x"


@pytest.mark.parametrize("bad", ["", "   ", "javascript:alert(1)", "http://", "not a url", "https://a b.com",
                                 "ftp://example.com", "https://-bad-.com", "data:text/html,hi"])
def test_invalid_urls_rejected(bad):
    with pytest.raises(ValidationError):
        normalize_url(bad)


def test_plain_text_roundtrip(settings):
    settings.content.type = "text"
    settings.content.text = "Hello, QR Studio! 123"
    assert roundtrip(settings) == "Hello, QR Studio! 123"


def test_unicode_and_khmer_roundtrip(settings):
    settings.content.type = "text"
    for txt in ("សួស្តី ពិភពលោក", "Café – naïve ✓ 日本語"):
        settings.content.text = txt
        assert roundtrip(settings, 1100) == txt


@pytest.mark.parametrize("ecc", ["L", "M", "Q", "H"])
def test_each_error_correction_level(settings, ecc):
    settings.logo.enabled = False
    settings.content.ecc = ecc
    prep = prepare(settings)
    assert prep.qrm.ecc == ecc
    assert roundtrip(settings) == "https://example.com"


def test_higher_ecc_means_larger_symbol():
    payload = "https://example.com/some/longer/path/for/size/comparison"
    assert generate_matrix(payload, "H").version >= generate_matrix(payload, "L").version


def test_ecc_raised_to_h_with_logo(settings, logo_png):
    settings.logo.path = str(logo_png)
    settings.content.ecc = "L"
    assert prepare(settings).ecc_used == "H"
    settings.logo.auto_high_ecc = False
    assert prepare(settings).ecc_used == "L"


def test_quiet_zone_is_preserved(settings):
    settings.frame.type = "none"
    prep = prepare(settings)
    bx, by, S, _ = prep.scene.qr_block
    sx, sy, sw, _ = prep.scene.symbol
    m = sw / prep.qrm.size
    assert round((sx - bx) / m) == settings.content.quiet_zone


def test_empty_and_overlong_content(settings):
    settings.content.url = ""
    with pytest.raises(ValidationError):
        prepare(settings)
    settings.content.type = "text"
    settings.content.text = "x" * 5000
    with pytest.raises(ValidationError):
        prepare(settings)


def test_payload_types(settings):
    c = settings.content
    c.type, c.email_to, c.email_subject = "email", "a@b.com", "Hi there"
    assert c.payload() == "mailto:a@b.com?subject=Hi%20there"
    c.type, c.phone = "phone", "+855 12 345 678"
    assert c.payload() == "tel:+85512345678"
    c.type, c.wifi_ssid, c.wifi_password = "wifi", "My;Net", "pass:word12"
    assert c.payload() == r"WIFI:T:WPA;S:My\;Net;P:pass\:word12;;"
    c.wifi_security = "NOPASS"
    assert c.payload() == r"WIFI:T:nopass;S:My\;Net;;"
    c.type, c.vcard_name = "vcard", "Sok Dara"
    assert c.payload().startswith("BEGIN:VCARD")
    c.type, c.sms_number, c.sms_message = "sms", "012345678", "hello"
    assert c.payload() == "SMSTO:012345678:hello"


def test_wifi_payload_decodes(settings):
    c = settings.content
    c.type, c.wifi_ssid, c.wifi_password = "wifi", "Cafe-5G", "supersecret1"
    assert roundtrip(settings) == "WIFI:T:WPA;S:Cafe-5G;P:supersecret1;;"
