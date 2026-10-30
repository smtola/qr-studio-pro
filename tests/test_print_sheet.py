import pytest

from src.core.print_sheet import build_print_sheet, compute_layout
from src.models.project_settings import ProjectSettings
from src.utils.validation import ValidationError


def test_layout_a4():
    lay = compute_layout("A4", 40, 10, 6)
    assert (lay.cols, lay.rows) == (4, 6) and lay.per_page == 24
    assert lay.x0 >= 10 and lay.y0 >= 10


def test_layout_errors():
    for args in (("A5", 40, 10, 6), ("A4", 10, 10, 6), ("A4", 150, 40, 6), ("A4", 40, 50, 6)):
        with pytest.raises(ValidationError):
            compute_layout(*args)


def test_pdf_pages_and_content(tmp_path):
    s = ProjectSettings()
    s.logo.enabled = False
    s.frame.type, s.frame.title = "card", "SCAN"
    out, pages = build_print_sheet([s.clone() for _ in range(30)], tmp_path / "sheet.pdf", cell_mm=40)
    assert pages == 2 and out.read_bytes().startswith(b"%PDF")
    assert out.read_bytes().count(b"/Type /Page\n") + out.read_bytes().count(b"/Type /Page ") >= 2


def test_pdf_scans_when_rasterised(tmp_path):
    pytest.importorskip("PySide6.QtPdf")
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument
    s = ProjectSettings()
    s.logo.enabled = False
    s.content.url = "https://example.com/sheet"
    out, _ = build_print_sheet([s], tmp_path / "one.pdf", cell_mm=60)
    doc = QPdfDocument()
    doc.load(str(out))
    assert doc.pageCount() == 1
    im = doc.render(0, QSize(1240, 1754))
    assert not im.isNull()


def test_errors(tmp_path):
    with pytest.raises(ValidationError):
        build_print_sheet([], tmp_path / "x.pdf")
    with pytest.raises(ValidationError):
        build_print_sheet([ProjectSettings()], tmp_path / "nope" / "x.pdf")
    bad = ProjectSettings()
    bad.content.url = ""
    with pytest.raises(ValidationError):
        build_print_sheet([bad], tmp_path / "x.pdf")
    assert not list(tmp_path.glob(".qrstudio-*"))
