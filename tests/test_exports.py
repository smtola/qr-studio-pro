import io
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from src.core.export_manager import ExportError, export_to_file, prepare
from src.utils.validation import ValidationError
from conftest import decode_qr


def configure(s, logo):
    s.logo.path = str(logo)
    s.frame.type, s.frame.title, s.frame.caption = "rounded", "SCAN ME", "Visit Our Website"
    s.colors.foreground = "#0B3D91"
    s.export.width_px = 1400


def qt_raster_svg(path, width):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(str(path))
    assert r.isValid()
    h = round(width * r.defaultSize().height() / r.defaultSize().width())
    im = QImage(width, h, QImage.Format.Format_RGBA8888)
    im.fill(Qt.GlobalColor.white)
    p = QPainter(im)
    r.render(p, QRectF(0, 0, width, h))
    p.end()
    return Image.frombytes("RGBA", (width, h), bytes(im.constBits()), "raw", "RGBA", im.bytesPerLine(), 1)


def qt_raster_pdf(path, width):
    from PySide6.QtCore import QSize
    QPdfDocument = pytest.importorskip("PySide6.QtPdf", reason="needs PySide6-Addons").QPdfDocument
    doc = QPdfDocument(None)
    assert doc.load(str(path)) == QPdfDocument.Error.None_
    ps = doc.pagePointSize(0)
    h = round(width * ps.height() / ps.width())
    im = doc.render(0, QSize(width, h))
    return Image.frombytes("RGBA", (im.width(), im.height()), bytes(im.constBits()), "raw", "RGBA",
                           im.bytesPerLine(), 1)


def test_png_export_is_scannable_with_logo_frame_and_dpi(settings, logo_png, tmp_path):
    configure(settings, logo_png)
    res = export_to_file(settings, tmp_path / "qr-code-example.png")
    assert res.path.exists() and res.format == "png" and res.width == 1400
    img = Image.open(res.path)
    assert img.size == (res.width, res.height)
    assert round(img.info["dpi"][0]) == 300
    assert decode_qr(img) == "https://example.com"


def test_jpg_export(settings, logo_png, tmp_path):
    configure(settings, logo_png)
    res = export_to_file(settings, tmp_path / "q.jpg")
    img = Image.open(res.path)
    assert img.format == "JPEG" and img.mode == "RGB"
    assert decode_qr(img) == "https://example.com"


def test_jpg_notes_transparency(settings, tmp_path):
    settings.colors.transparent = True
    res = export_to_file(settings, tmp_path / "q.jpg")
    assert any("transparen" in n for n in res.notes)


def test_png_transparent_background(settings, tmp_path):
    settings.colors.transparent = True
    res = export_to_file(settings, tmp_path / "t.png")
    img = Image.open(res.path)
    assert img.mode == "RGBA" and img.getpixel((1, 1))[3] == 0


def test_svg_export_is_vector_and_scannable(settings, logo_png, tmp_path, qapp):
    configure(settings, logo_png)
    res = export_to_file(settings, tmp_path / "q.svg")
    text = res.path.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    ns = "{http://www.w3.org/2000/svg}"
    assert root.tag == ns + "svg"
    assert root.findall(f".//{ns}path") and root.findall(f".//{ns}image"), "vector paths + embedded logo"
    assert "SCAN ME" in text and "Visit Our Website" in text
    assert str(tmp_path) not in text and "logo.png" not in text, "no local paths leak into exports"
    assert decode_qr(qt_raster_svg(res.path, 1200)) == "https://example.com"


def test_svg_gradient(settings, tmp_path, qapp):
    settings.colors.gradient = True
    res = export_to_file(settings, tmp_path / "g.svg")
    assert "linearGradient" in res.path.read_text()
    assert decode_qr(qt_raster_svg(res.path, 1000)) == "https://example.com"


def test_pdf_export_is_valid_and_scannable(settings, logo_png, tmp_path, qapp):
    configure(settings, logo_png)
    res = export_to_file(settings, tmp_path / "q.pdf")
    data = res.path.read_bytes()
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert str(tmp_path).encode() not in data
    assert decode_qr(qt_raster_pdf(res.path, 1400)) == "https://example.com"


def test_pdf_page_size_matches_dpi(settings, tmp_path, qapp):
    settings.export.width_px, settings.export.dpi = 1500, 300   # 5 inch wide
    res = export_to_file(settings, tmp_path / "s.pdf")
    QPdfDocument = pytest.importorskip("PySide6.QtPdf", reason="needs PySide6-Addons").QPdfDocument
    doc = QPdfDocument(None)
    doc.load(str(res.path))
    assert doc.pagePointSize(0).width() == pytest.approx(360, abs=0.5)


def test_pdf_with_khmer_text_and_gradient(settings, tmp_path, qapp):
    settings.frame.type, settings.frame.title = "cta", "ស្កែនទីនេះ"
    settings.colors.gradient = True
    res = export_to_file(settings, tmp_path / "k.pdf")
    assert decode_qr(qt_raster_pdf(res.path, 1200)) == "https://example.com"


def test_overwrite_protection(settings, tmp_path):
    p = tmp_path / "a.png"
    export_to_file(settings, p)
    with pytest.raises(FileExistsError):
        export_to_file(settings, p)
    export_to_file(settings, p, overwrite=True)


def test_extension_added_when_missing(settings, tmp_path):
    settings.export.format = "svg"
    res = export_to_file(settings, tmp_path / "noext")
    assert res.path.name == "noext.svg"
    assert res.path.exists()


def test_bad_paths_and_no_temp_files_left(settings, tmp_path):
    with pytest.raises(ExportError):
        export_to_file(settings, tmp_path / "missing-dir" / "a.png")
    assert not list(tmp_path.glob(".qrstudio-*"))


def test_export_fails_loudly_when_logo_missing(settings, tmp_path):
    settings.logo.path = str(tmp_path / "gone.png")
    with pytest.raises(ValidationError):
        export_to_file(settings, tmp_path / "a.png")
    assert not (tmp_path / "a.png").exists()


def test_export_invalid_content(settings, tmp_path):
    settings.content.url = ""
    with pytest.raises(ValidationError):
        export_to_file(settings, tmp_path / "a.png")


def test_too_large_export_rejected(settings, tmp_path):
    settings.frame.type, settings.frame.min_height = "rounded", 4000
    settings.export.width_px = 6000
    with pytest.raises(ExportError):
        export_to_file(settings, tmp_path / "huge.png")


def test_png_contains_no_metadata_beyond_dpi(settings, tmp_path):
    res = export_to_file(settings, tmp_path / "m.png")
    img = Image.open(res.path)
    assert set(img.info) <= {"dpi", "gamma"}
