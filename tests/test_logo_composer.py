import pytest
from PIL import Image

from src.core.export_manager import prepare, render_image
from src.core.logo_composer import LogoError, load_logo, plan_logo
from conftest import decode_qr

SYMBOL = (100.0, 100.0, 400.0, 400.0)


def test_logo_is_centred_and_keeps_aspect(settings, logo_png):
    settings.logo.backing = "square"
    img = load_logo(logo_png).image
    plan = plan_logo(settings, img, SYMBOL)
    x, y, w, h = plan.logo_box
    assert x + w / 2 == pytest.approx(300) and y + h / 2 == pytest.approx(300)
    assert w / h == pytest.approx(img.width / img.height)
    bx, by, bw, bh = plan.backing_box
    assert bx + bw / 2 == pytest.approx(300) and bw == bh


@pytest.mark.parametrize("pct", [10, 15, 20, 25])
def test_logo_size_pct(settings, logo_png, pct):
    settings.logo.size_pct, settings.logo.backing = pct, "rounded"
    plan = plan_logo(settings, load_logo(logo_png).image, SYMBOL)
    assert plan.backing_box[2] == pytest.approx(400 * pct / 100)
    assert plan.covered_fraction <= (pct / 100) ** 2 + 1e-9


@pytest.mark.parametrize("shape", ["none", "square", "rounded", "circle"])
def test_logo_always_inside_backing(settings, logo_png, shape):
    settings.logo.backing = shape
    plan = plan_logo(settings, load_logo(logo_png).image, SYMBOL)
    lx, ly, lw, lh = plan.logo_box
    bx, by, bw, bh = plan.backing_box
    assert lx >= bx - 1e-6 and ly >= by - 1e-6 and lx + lw <= bx + bw + 1e-6 and ly + lh <= by + bh + 1e-6
    if shape == "circle":  # all four logo corners within the circle
        r = bw / 2
        assert ((lx - (bx + r)) ** 2 + (ly - (by + r)) ** 2) ** 0.5 <= r + 1e-6


def test_tall_logo_not_distorted(settings, tmp_path):
    p = tmp_path / "tall.png"
    Image.new("RGBA", (100, 400), (0, 0, 255, 255)).save(p)
    plan = plan_logo(settings, load_logo(p).image, SYMBOL)
    assert plan.logo_box[2] / plan.logo_box[3] == pytest.approx(0.25)


def test_transparent_png_and_jpg_load(tmp_path, logo_png):
    assert load_logo(logo_png).has_alpha
    jp = tmp_path / "l.jpg"
    Image.new("RGB", (64, 64), "red").save(jp)
    assert not load_logo(jp).has_alpha


def test_svg_logo(tmp_path):
    p = tmp_path / "l.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" '
                 'fill="#c00"/></svg>')
    pytest.importorskip("PySide6.QtSvg")
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication(["t"])
    info = load_logo(p)
    assert info.image.width / info.image.height == pytest.approx(2.0, rel=0.02)


def test_unsafe_svg_rejected(tmp_path):
    p = tmp_path / "bad.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    with pytest.raises(LogoError):
        load_logo(p)


@pytest.mark.parametrize("content,name", [(b"not an image", "a.png"), (b"", "b.png"), (b"GIF89a....", "c.jpg")])
def test_invalid_logo_files(tmp_path, content, name):
    p = tmp_path / name
    p.write_bytes(content)
    with pytest.raises(LogoError):
        load_logo(p)


def test_missing_and_unsupported_logo(tmp_path):
    with pytest.raises(LogoError):
        load_logo(tmp_path / "nope.png")
    p = tmp_path / "x.bmp"
    p.write_bytes(b"BM")
    with pytest.raises(LogoError):
        load_logo(p)
    with pytest.raises(LogoError):
        load_logo("")


def test_oversized_dimensions_rejected(tmp_path):
    p = tmp_path / "huge.png"
    Image.new("L", (9000, 10), 0).save(p)
    with pytest.raises(LogoError):
        load_logo(p)


def test_preview_survives_missing_logo_but_export_prep_fails(settings, tmp_path):
    settings.logo.path = str(tmp_path / "gone.png")
    prep = prepare(settings, strict=False)
    assert prep.logo is None and prep.logo_error
    assert any(a.code == "logo-missing" for a in prep.advice)
    with pytest.raises(LogoError):
        prepare(settings, strict=True)


@pytest.mark.parametrize("shape", ["none", "square", "rounded", "circle"])
@pytest.mark.parametrize("pct", [15, 20, 25])
def test_logo_codes_still_scan(settings, logo_png, shape, pct):
    settings.logo.path, settings.logo.backing, settings.logo.size_pct = str(logo_png), shape, pct
    img = render_image(prepare(settings), 1000)
    assert decode_qr(img) == "https://example.com"


def test_logo_pixels_present_at_centre(settings, logo_png):
    settings.logo.path = str(logo_png)
    img = render_image(prepare(settings), 800)
    cx, cy = img.width // 2, img.height // 2
    r, g, b, a = img.getpixel((cx - 40, cy))  # inside the red ellipse part of the logo
    assert r > 180 and g < 90
