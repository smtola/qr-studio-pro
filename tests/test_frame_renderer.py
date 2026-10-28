import pytest

from src.core.export_manager import prepare, render_image
from src.models.project_settings import FRAME_TYPES
from conftest import decode_qr


def inter(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def inside(inner, outer, tol=1e-6):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox - tol and iy >= oy - tol and ix + iw <= ox + ow + tol and iy + ih <= oy + oh + tol


def configure(s, ftype, **kw):
    s.frame.type = ftype
    s.frame.title, s.frame.caption, s.frame.company = "SCAN ME", "Visit Our Website", "ACME Co."
    for k, v in kw.items():
        setattr(s.frame, k, v)


@pytest.mark.parametrize("ftype", FRAME_TYPES)
@pytest.mark.parametrize("positions", [("top", "bottom", "top"), ("bottom", "top", "bottom"), ("top", "top", "top")])
def test_text_never_overlaps_qr_block(settings, ftype, positions):
    configure(settings, ftype, title_position=positions[0], caption_position=positions[1],
              company_position=positions[2])
    scene = prepare(settings).scene
    for tb in scene.text_boxes:
        assert not inter(tb, scene.qr_block), (ftype, tb, scene.qr_block)
    assert inside(scene.qr_block, (0, 0, scene.width, scene.height))
    for tb in scene.text_boxes:
        assert inside(tb, (0, 0, scene.width, scene.height))


@pytest.mark.parametrize("ftype", [t for t in FRAME_TYPES if t != "none"])
def test_content_inside_frame(settings, ftype):
    configure(settings, ftype)
    scene = prepare(settings).scene
    fx, fy, fw, fh = scene.frame_box
    assert inside(scene.qr_block, scene.frame_box)
    for tb in scene.text_boxes:
        assert inside(tb, scene.frame_box)
    if ftype == "badge":  # QR block corners must lie within the circle
        r = fw / 2
        cx, cy = fx + r, fy + r
        bx, by, bw, bh = scene.qr_block
        for px, py in ((bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh)):
            assert ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 <= r


def test_long_text_is_shrunk_not_overflowing(settings):
    configure(settings, "rounded", title="A VERY LONG CALL TO ACTION HEADLINE THAT WOULD NOT FIT AT ALL " * 2)
    scene = prepare(settings).scene
    assert all(inside(tb, scene.frame_box) for tb in scene.text_boxes)


def test_min_frame_size_is_honoured_and_content_centred(settings):
    configure(settings, "rounded", min_width=1200, min_height=1500)
    scene = prepare(settings).scene
    assert scene.frame_box[2] >= 1200 and scene.frame_box[3] >= 1500
    bx, _, bw, _ = scene.qr_block
    assert bx + bw / 2 == pytest.approx(scene.frame_box[0] + scene.frame_box[2] / 2)


def test_no_frame_has_no_margin_or_border(settings):
    prep = prepare(settings)
    assert prep.scene.width == pytest.approx(settings.export.qr_size)


def test_frame_and_colours_are_independent(settings):
    configure(settings, "double", color="#FF0000", background="#EEEEEE")
    settings.colors.foreground = "#003366"
    prep = prepare(settings)
    img = render_image(prep, 900)
    assert img.getpixel((int(prep.scene.frame_box[0] * 900 / prep.scene.width + 3), img.height // 2))[:3] \
        == (255, 0, 0)
    assert decode_qr(img) == "https://example.com"


@pytest.mark.parametrize("ftype", FRAME_TYPES)
def test_framed_codes_still_scan(settings, ftype, logo_png):
    configure(settings, ftype)
    settings.logo.path = str(logo_png)
    assert decode_qr(render_image(prepare(settings), 1100)) == "https://example.com"


@pytest.mark.parametrize("style", ["square", "rounded", "dots"])
@pytest.mark.parametrize("outer", ["square", "rounded"])
@pytest.mark.parametrize("inner", ["square", "rounded", "circle"])
def test_module_and_eye_styles_scan(settings, style, outer, inner):
    settings.colors.module_style = style
    settings.eyes.outer_style, settings.eyes.inner_style = outer, inner
    settings.content.ecc = "Q"
    assert decode_qr(render_image(prepare(settings), 1000)) == "https://example.com"


def test_dashed_border_renders(settings):
    configure(settings, "rounded", border_style="dashed")
    img = render_image(prepare(settings), 600)
    assert img.size[0] == 600


def test_khmer_frame_text(settings):
    configure(settings, "cta", title="ស្កែនទីនេះ", caption="សូមចូលមើលគេហទំព័រ")
    prep = prepare(settings)
    assert prep.scene.text_boxes and all(tb[2] > 0 for tb in prep.scene.text_boxes)
    render_image(prep, 800)


def test_circular_outer_eyes_trigger_warning(settings):
    from src.core.scan_advisor import advise
    settings.eyes.outer_style = "circle"
    assert any(a.code == "circle-eyes" for a in advise(settings))
