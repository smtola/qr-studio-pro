import pytest

from src.core.color_manager import PRESET_NAMES, PRESETS, apply_preset, contrast_ratio
from src.core.export_manager import prepare, render_image
from src.core.scan_advisor import advise
from src.utils.validation import ValidationError, normalize_hex
from conftest import decode_qr


def test_hex_normalisation():
    assert normalize_hex("#abc") == "#AABBCC" and normalize_hex("111111") == "#111111"
    for bad in ("", "#12", "red", "#GGGGGG", "#1234567"):
        with pytest.raises(ValidationError):
            normalize_hex(bad)


def test_contrast_ratio_extremes():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_all_required_presets_exist():
    for n in ("Classic Black & White", "Corporate Blue", "Emerald Green", "Crimson Red", "Purple Modern",
              "Dark Premium", "Custom Brand Colors"):
        assert n in PRESET_NAMES


@pytest.mark.parametrize("preset", [p.name for p in PRESETS])
def test_every_preset_scans_and_has_good_contrast(settings, preset):
    apply_preset(settings, preset)
    assert not any(a.level == "error" for a in advise(settings))
    assert decode_qr(render_image(prepare(settings), 900)) == "https://example.com"


def test_custom_preset_keeps_colours(settings):
    settings.colors.foreground = "#123456"
    apply_preset(settings, "Custom Brand Colors")
    assert settings.colors.foreground == "#123456"


def test_low_contrast_warns(settings):
    settings.colors.foreground, settings.colors.background = "#DDDDDD", "#FFFFFF"
    assert any(a.code == "contrast" and a.level == "error" for a in advise(settings))


def test_inverted_warns(settings):
    settings.colors.foreground, settings.colors.background = "#FFFFFF", "#000000"
    assert any(a.code == "inverted" for a in advise(settings))


def test_custom_colours_scan(settings):
    settings.colors.foreground, settings.colors.background = "#0B3D91", "#FFF8E1"
    settings.eyes.follow_foreground = False
    settings.eyes.outer_color, settings.eyes.inner_color = "#B91C1C", "#0B3D91"
    assert decode_qr(render_image(prepare(settings), 900)) == "https://example.com"


def test_eye_colours_are_independent(settings):
    settings.eyes.follow_foreground = False
    settings.eyes.outer_color, settings.eyes.inner_color = "#FF0000", "#00AA00"
    prep = prepare(settings)
    img = render_image(prep, 1000)
    k = 1000 / prep.scene.width
    sx, sy, sw, _ = prep.scene.symbol
    m = sw / prep.qrm.size * k
    ring = img.getpixel((int(sx * k + 0.5 * m), int(sy * k + 3.5 * m)))
    pupil = img.getpixel((int(sx * k + 3.5 * m), int(sy * k + 3.5 * m)))
    assert ring[:3] == (255, 0, 0) and pupil[:3] == (0, 170, 0)


def test_gradient_foreground_scans_and_varies(settings):
    c = settings.colors
    c.gradient, c.foreground, c.gradient_end, c.gradient_angle = True, "#0B1F5C", "#7A1230", 0
    settings.eyes.follow_foreground = True
    prep = prepare(settings)
    img = render_image(prep, 1000)
    assert decode_qr(img) == "https://example.com"
    k = 1000 / prep.scene.width
    sx, sy, sw, _ = prep.scene.symbol
    m = sw / prep.qrm.size * k
    left = img.getpixel((int(sx * k + 3.5 * m), int(sy * k + 3.5 * m)))      # centre of left eye
    right = img.getpixel((int((sx + sw) * k - 3.5 * m), int(sy * k + 3.5 * m)))  # centre of right eye
    assert left[2] > right[2] and right[0] > left[0]


def test_transparent_background_png_has_alpha(settings):
    settings.colors.transparent = True
    img = render_image(prepare(settings), 600)
    assert img.getpixel((2, 2))[3] == 0
    assert img.getchannel("A").getextrema()[1] == 255
