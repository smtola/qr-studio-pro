import threading

import pytest

from src.core.batch import BatchRow, parse_csv_text, read_csv, run_batch, safe_name, settings_for_row
from src.models.project_settings import ProjectSettings
from src.utils.validation import ValidationError
from tests.conftest import decode_qr


def test_parse_with_header_and_columns():
    rows = parse_csv_text("url,filename,title\nhttps://a.com,card-a,HELLO\n\nhttps://b.com,,\n")
    assert [r.value for r in rows] == ["https://a.com", "https://b.com"]
    assert rows[0].filename == "card-a" and rows[0].title == "HELLO" and rows[1].title is None
    assert rows[1].line == 4


def test_parse_without_header_semicolons_and_bom():
    rows = parse_csv_text("﻿https://a.com;x\nhello world;y\n")
    assert [r.value for r in rows] == ["https://a.com", "hello world"]
    assert rows[0].title is None


def test_parse_errors(tmp_path):
    for bad in ("", "\n\n", "url\n"):
        with pytest.raises(ValidationError):
            parse_csv_text(bad)
    with pytest.raises(ValidationError):
        read_csv(tmp_path / "missing.csv")


def test_khmer_csv(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("content,title\nសួស្តី ពិភពលោក,ស្កេន\n", encoding="utf-8")
    r = read_csv(p)
    assert r[0].value == "សួស្តី ពិភពលោក" and r[0].title == "ស្កេន"


def test_settings_for_row_kinds():
    base = ProjectSettings()
    assert settings_for_row(base, BatchRow(2, "example.org/x")).content.type == "url"
    assert settings_for_row(base, BatchRow(2, "just some words")).content.type == "text"
    assert settings_for_row(base, BatchRow(2, "example.org"), "text").content.type == "text"
    s = settings_for_row(base, BatchRow(2, "https://a.com", title="T"))
    assert s.frame.title == "T" and base.frame.title == ""


def test_safe_name():
    assert safe_name("../../etc/passwd.png", "x") == "etc-passwd"
    assert safe_name("", "fb") == "fb"


def test_run_batch_creates_files_and_report(tmp_path):
    base = ProjectSettings()
    base.logo.enabled = False
    base.export.width_px = 500
    rows = [BatchRow(2, "https://one.example.com", "same"), BatchRow(3, "https://two.example.com", "same"),
            BatchRow(4, "x" * 2500)]
    seen = []
    rep = run_batch(base, rows, tmp_path, progress=lambda i, n, r: seen.append((i, n, r.ok)))
    assert rep.ok_count == 2 and len(rep.failed) == 1 and seen[-1] == (3, 3, False)
    assert (tmp_path / "same.png").exists() and (tmp_path / "same-2.png").exists()
    assert (tmp_path / "batch-report.csv").read_text(encoding="utf-8-sig").count("\n") >= 4
    from PIL import Image
    assert decode_qr(Image.open(tmp_path / "same-2.png")) == "https://two.example.com"


def test_cancel_and_bad_folder(tmp_path):
    ev = threading.Event()
    ev.set()
    rep = run_batch(ProjectSettings(), [BatchRow(2, "https://a.com")], tmp_path, cancel=ev)
    assert rep.cancelled and not rep.results
    with pytest.raises(ValidationError):
        run_batch(ProjectSettings(), [BatchRow(2, "a")], tmp_path / "nope")
