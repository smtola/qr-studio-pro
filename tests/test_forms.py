from pathlib import Path

import pytest

from src.convert.common import ConvertError
from src.convert.forms import (FieldSpec, detect_fields, fields_csv_template, fill_form, fill_from_csv,
                               list_form_fields, make_fillable)


def make_blank_form(path: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 790, "Application form")
    c.setFont("Helvetica", 11)
    c.drawString(72, 740, "Full name:")
    c.line(140, 738, 400, 738)                       # ruled blank
    c.drawString(72, 700, "Phone:")
    c.drawString(120, 700, "____________________")   # underscore blank
    c.drawString(72, 660, "Address")
    c.rect(72, 600, 300, 50)                         # empty box under the label
    c.rect(72, 560, 10, 10)                          # checkbox
    c.drawString(90, 561, "I agree to the terms")
    c.showPage()
    c.save()


def test_detect_finds_blanks_and_labels(tmp_path):
    pdf = tmp_path / "form.pdf"
    make_blank_form(pdf)
    specs = detect_fields(pdf)
    kinds = sorted(s.kind for s in specs)
    assert kinds.count("checkbox") == 1 and kinds.count("text") >= 3
    names = {s.name for s in specs}
    assert "full_name" in names and "phone" in names and "address" in names
    assert len(names) == len(specs)                  # unique names
    cb = next(s for s in specs if s.kind == "checkbox")
    assert 8 <= cb.size[0] <= 12


def test_make_fillable_and_fill(tmp_path):
    pdf = tmp_path / "form.pdf"
    make_blank_form(pdf)
    specs = detect_fields(pdf)
    out = make_fillable(pdf, tmp_path, specs)
    fields = {f.name: f for f in list_form_fields(out)}
    assert "full_name" in fields and fields["full_name"].kind == "text"
    cbs = [f for f in fields.values() if f.kind == "checkbox"]
    assert len(cbs) == 1
    filled = fill_form(out, tmp_path, {"full_name": "Sokha Chan", cbs[0].name: "yes"})
    vals = {f.name: f.value for f in list_form_fields(filled)}
    assert vals["full_name"] == "Sokha Chan" and vals[cbs[0].name] == "Yes"
    flat = fill_form(out, tmp_path, {"full_name": "Dara Kim"}, flatten=True, suffix="-flat")
    import pdfplumber
    with pdfplumber.open(str(flat)) as p:
        assert "Dara Kim" in (p.pages[0].extract_text() or "")
    assert list_form_fields(flat) == [] or all(not f.value for f in list_form_fields(flat) if f.name == "phone")


def test_disabled_fields_are_skipped_and_errors(tmp_path):
    pdf = tmp_path / "form.pdf"
    make_blank_form(pdf)
    specs = detect_fields(pdf)
    for s in specs:
        s.enabled = False
    with pytest.raises(ConvertError):
        make_fillable(pdf, tmp_path, specs)
    with pytest.raises(ConvertError):
        fill_form(pdf, tmp_path, {"x": "1"})            # no fields yet
    out = make_fillable(pdf, tmp_path, [FieldSpec(0, 100, 100, 300, 120, name="manual", label="Manual")])
    with pytest.raises(ConvertError):
        fill_form(out, tmp_path, {"nope": "1"})
    with pytest.raises(ConvertError):
        make_fillable(pdf, tmp_path, [FieldSpec(5, 0, 0, 10, 10, name="x")])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 junk")
    with pytest.raises(ConvertError):
        detect_fields(bad)


def test_csv_template_and_bulk_fill(tmp_path):
    pdf = tmp_path / "form.pdf"
    make_blank_form(pdf)
    out = make_fillable(pdf, tmp_path, detect_fields(pdf))
    tpl = fields_csv_template(out, tmp_path / "t.csv")
    header = tpl.read_text(encoding="utf-8-sig").strip().split(",")
    assert "full_name" in header
    data = tmp_path / "people.csv"
    data.write_text("full_name,phone\nAlice A,111\nBob B,222\n", encoding="utf-8")
    files = fill_from_csv(out, data, tmp_path, name_column="full_name")
    assert len(files) == 2 and "alice_a" in files[0].name
    assert {f.name: f.value for f in list_form_fields(files[1])}["phone"] == "222"
