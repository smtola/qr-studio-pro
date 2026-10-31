"""Convert Studio (documents) and Convert Media (images, GIF, video) windows."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from ..convert import documents as D
from ..convert import media as M
from ..convert import pdf_tools as P
from ..convert.common import ConvertError, find_ffmpeg, find_office
from ..services.app_prefs import AppPrefs
from .convert_widgets import FilesBox, TaskPage
from .widgets import combo, form, muted, spin

PDF = (".pdf",)
EXCEL = (".xlsx", ".xlsm", ".xls", ".csv")
WORD = (".docx", ".doc", ".odt", ".rtf", ".txt")
IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")
VIDEOS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".gif", ".flv", ".wmv")


def _opts(rows: list[tuple[str, QWidget]], getter) -> tuple[QWidget, callable]:
    w = QWidget()
    f = form()
    for label, wid in rows:
        f.addRow(label, wid) if label else f.addRow(wid)
    w.setLayout(f)
    return w, getter


def _need_office() -> str:
    return "" if find_office() else ("LibreOffice (free) is not installed, so a simpler built-in renderer is used. "
                                     "Install LibreOffice for best layout fidelity.")


def _need_office_strict() -> str:
    return "" if find_office() else "This conversion needs LibreOffice (free, libreoffice.org) installed on your computer."


def _need_ffmpeg() -> str:
    return "" if find_ffmpeg() else "This tool needs FFmpeg (free). Install it and restart the app."


class ToolsWindow(QMainWindow):
    """Sidebar of tools on the left, the selected tool on the right."""

    def __init__(self, title: str, pages: list[tuple[str, QWidget]], footer: QWidget | None = None):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1000, 700)
        self.setMinimumSize(780, 560)
        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        side = QVBoxLayout()
        self.menu = QListWidget()
        self.menu.setObjectName("toolMenu")
        self.menu.setFixedWidth(230)
        self.menu.setAccessibleName("Tools")
        side.addWidget(self.menu, 1)
        if footer is not None:
            side.addWidget(footer)
        lay.addLayout(side)
        self.stack = QStackedWidget()
        card = QWidget()
        card.setObjectName("toolCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 12)
        cl.addWidget(self.stack)
        lay.addWidget(card, 1)
        self.setCentralWidget(root)
        self.pages: dict[str, QWidget] = {}
        for name, page in pages:
            self.menu.addItem(name)
            self.stack.addWidget(page)
            self.pages[name] = page
        self.menu.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.menu.setCurrentRow(0)

    def show_page(self, name: str) -> None:
        names = list(self.pages)
        if name in names:
            self.menu.setCurrentRow(names.index(name))


def convert_studio(prefs: AppPrefs) -> ToolsWindow:
    pages: list[tuple[str, QWidget]] = []

    # Excel -> PDF
    fb = FilesBox(EXCEL, "Excel / CSV files", prefs=prefs)
    pages.append(("Excel → PDF", TaskPage(
        "Excel to PDF", "Turn spreadsheets (.xlsx, .xls, .csv) into PDF documents. Every sheet becomes pages.", fb,
        lambda files, out, o, prog, c: D.excel_to_pdf(files[0], out), needs=_need_office, prefs=prefs)))

    # PDF -> Word
    fb = FilesBox(PDF, "PDF files", prefs=prefs)
    page = TaskPage("PDF to Word", "Rebuild headings, paragraphs, tables and pictures as an editable .docx. "
                    "Scanned pages become pictures (no text recognition).", fb, None, prefs=prefs)

    def pdf_word(files, out, o, prog, c, _page=None):
        notes: list[str] = []
        r = D.pdf_to_word(files[0], out, notes=notes)
        return r
    page.worker = pdf_word
    pages.append(("PDF → Word", page))

    # PDF -> Excel
    fb = FilesBox(PDF, "PDF files", prefs=prefs)
    one = QCheckBox("Put all tables on one sheet")
    w, g = _opts([("", one)], lambda: {"one": one.isChecked()})
    pages.append(("PDF → Excel", TaskPage(
        "PDF to Excel", "Find tables in the PDF and save them as spreadsheets. If no tables exist, the text is saved line by line.",
        fb, lambda files, out, o, prog, c: D.pdf_to_excel(files[0], out, one_sheet=o["one"]), options=w, get_opts=g, prefs=prefs)))

    # Word -> PDF
    fb = FilesBox(WORD, "Word documents", prefs=prefs)
    pages.append(("Word → PDF", TaskPage(
        "Word to PDF", "Convert .docx, .doc, .odt or .rtf documents to PDF using LibreOffice.", fb,
        lambda files, out, o, prog, c: D.word_to_pdf(files[0], out), needs=_need_office_strict, prefs=prefs)))

    # Excel <-> CSV
    fb = FilesBox((".xlsx", ".xlsm", ".csv"), "Excel / CSV files", prefs=prefs)

    def xl_csv(files, out, o, prog, c):
        f = files[0]
        return D.csv_to_excel(f, out) if f.suffix.lower() == ".csv" else D.excel_to_csv(f, out)
    pages.append(("Excel ↔ CSV", TaskPage(
        "Excel ↔ CSV", "Excel (.xlsx) becomes CSV (one file per sheet); CSV becomes an Excel workbook. Khmer and other Unicode text are kept.",
        fb, xl_csv, prefs=prefs)))

    # Images -> PDF
    fb = FilesBox(IMAGES, "Pictures", ordered=True, prefs=prefs)
    layout = combo("Page size", [("Same size as each picture", "fit"), ("A4 pages", "a4")])
    name = QLineEdit("images")
    name.setAccessibleName("PDF name")
    w, g = _opts([("Pages", layout), ("File name", name)], lambda: {"page": layout.currentData(), "name": name.text().strip() or "images"})
    pages.append(("Images → PDF", TaskPage(
        "Images to PDF", "Combine pictures into one PDF, one picture per page. Use Move up / Move down to set the order.",
        fb, lambda files, out, o, prog, c: P.images_to_pdf(files, out, name=o["name"], page=o["page"], progress=prog),
        options=w, get_opts=g, per_file=False, prefs=prefs)))

    # PDF -> Images
    fb = FilesBox(PDF, "PDF files", prefs=prefs)
    fmt = combo("Image format", [("PNG (sharp)", "png"), ("JPG (small)", "jpg")])
    dpi = spin("Resolution", 36, 600, " dpi", 25)
    dpi.setValue(150)
    w, g = _opts([("Format", fmt), ("Resolution", dpi)], lambda: {"fmt": fmt.currentData(), "dpi": dpi.value()})
    pages.append(("PDF → Images", TaskPage(
        "PDF to images", "Save every page of a PDF as a picture.", fb,
        lambda files, out, o, prog, c: P.pdf_to_images(files[0], out, fmt=o["fmt"], dpi=o["dpi"]), options=w, get_opts=g, prefs=prefs)))

    # Merge
    fb = FilesBox(PDF, "PDF files", ordered=True, prefs=prefs)
    name = QLineEdit("merged")
    name.setAccessibleName("Merged file name")
    w, g = _opts([("File name", name)], lambda: {"name": name.text().strip() or "merged"})
    pages.append(("Merge PDF", TaskPage(
        "Merge PDF", "Join several PDFs into one, in the order shown below.", fb,
        lambda files, out, o, prog, c: P.merge_pdfs(files, out, name=o["name"], progress=prog),
        options=w, get_opts=g, per_file=False, min_files=2, run_text="Merge", prefs=prefs)))

    # Split
    fb = FilesBox(PDF, "PDF file", multi=False, prefs=prefs)
    rng = QLineEdit()
    rng.setPlaceholderText("e.g. 1-3, 5, 8-")
    rng.setAccessibleName("Pages to keep")
    each = QCheckBox("Save every page as its own PDF")
    w, g = _opts([("Pages", rng), ("", each)], lambda: {"ranges": rng.text(), "each": each.isChecked()})
    pages.append(("Split PDF", TaskPage(
        "Split / extract pages", "Keep only some pages (1-3, 5, 8-) or save every page separately.", fb,
        lambda files, out, o, prog, c: P.split_pdf(files[0], out, ranges=o["ranges"], every_page=o["each"], progress=prog),
        options=w, get_opts=g, run_text="Split", prefs=prefs)))
    return ToolsWindow("Convert Studio", pages)


def convert_media(prefs: AppPrefs) -> ToolsWindow:
    pages: list[tuple[str, QWidget]] = []
    ff = _need_ffmpeg

    def page(name, desc, files, worker, **kw):
        pages.append((name, TaskPage(name, desc, files, worker, prefs=prefs, **kw)))

    fmt = combo("Format", [("PNG", "png"), ("JPG", "jpg"), ("WebP", "webp"), ("GIF", "gif"), ("BMP", "bmp"),
                           ("TIFF", "tiff"), ("ICO (icon)", "ico")])
    q = spin("Quality", 10, 100, "", 5)
    q.setValue(90)
    w, g = _opts([("Convert to", fmt), ("Quality (JPG/WebP)", q)], lambda: {"fmt": fmt.currentData(), "q": q.value()})
    page("Convert image", "Change the format of pictures. Animated GIF and WebP keep their animation.",
         FilesBox(M.IMAGE_EXTS, "Pictures", prefs=prefs), lambda f, out, o, p, c: M.convert_image(f[0], out, fmt=o["fmt"], quality=o["q"]),
         options=w, get_opts=g)

    wd, ht, pc = spin("Width", 0, 20000, " px", 10), spin("Height", 0, 20000, " px", 10), spin("Percent", 0, 1000, " %", 5)
    keep = QCheckBox("Keep proportions")
    keep.setChecked(True)
    w, g = _opts([("Width", wd), ("Height", ht), ("or percent", pc), ("", keep)],
                 lambda: {"w": wd.value(), "h": ht.value(), "p": pc.value(), "k": keep.isChecked()})
    page("Resize", "Make pictures or animated GIFs smaller or larger. Leave a field at 0 to ignore it.",
         FilesBox(M.IMAGE_EXTS, "Pictures", prefs=prefs),
         lambda f, out, o, p, c: M.resize_image(f[0], out, width=o["w"], height=o["h"], percent=o["p"], keep_aspect=o["k"]),
         options=w, get_opts=g)

    cl, ct, cw, ch = (spin("Left", 0, 20000, " px", 10), spin("Top", 0, 20000, " px", 10),
                      spin("Width", 0, 20000, " px", 10), spin("Height", 0, 20000, " px", 10))
    w, g = _opts([("Left", cl), ("Top", ct), ("Width", cw), ("Height", ch)],
                 lambda: {"l": cl.value(), "t": ct.value(), "w": cw.value(), "h": ch.value()})
    page("Crop", "Cut a rectangle out of a picture.", FilesBox(M.IMAGE_EXTS, "Pictures", prefs=prefs),
         lambda f, out, o, p, c: M.crop_image(f[0], out, left=o["l"], top=o["t"], width=o["w"], height=o["h"]),
         options=w, get_opts=g, run_text="Crop")

    rot = combo("Rotate", [("No rotation", "0"), ("90° clockwise", "90"), ("180°", "180"), ("90° counter-clockwise", "270")])
    fh, fv = QCheckBox("Flip horizontally"), QCheckBox("Flip vertically")
    w, g = _opts([("Rotate", rot), ("", fh), ("", fv)],
                 lambda: {"r": int(rot.currentData()), "h": fh.isChecked(), "v": fv.isChecked()})
    page("Rotate / flip", "Turn pictures around or mirror them.", FilesBox(M.IMAGE_EXTS, "Pictures", prefs=prefs),
         lambda f, out, o, p, c: M.transform_image(f[0], out, rotate=o["r"], flip_h=o["h"], flip_v=o["v"]),
         options=w, get_opts=g, run_text="Apply")

    cq, cs = spin("Quality", 10, 95, "", 5), spin("Longest side", 0, 20000, " px", 100)
    cq.setValue(75)
    w, g = _opts([("Quality", cq), ("Shrink longest side to", cs)], lambda: {"q": cq.value(), "s": cs.value()})
    page("Compress image", "Make JPG, PNG or WebP files smaller for sharing. 0 px keeps the original size.",
         FilesBox((".png", ".jpg", ".jpeg", ".webp"), "Pictures", prefs=prefs),
         lambda f, out, o, p, c: M.compress_image(f[0], out, quality=o["q"], max_side=o["s"]), options=w, get_opts=g,
         run_text="Compress")

    dl, gw, loop = spin("Delay", 20, 5000, " ms", 20), spin("Width", 0, 4000, " px", 20), QCheckBox("Loop forever")
    dl.setValue(200)
    loop.setChecked(True)
    w, g = _opts([("Delay per frame", dl), ("Width (0 = first picture)", gw), ("", loop)],
                 lambda: {"d": dl.value(), "w": gw.value(), "l": 0 if loop.isChecked() else 1})
    page("Images → GIF", "Make an animated GIF from pictures. Use Move up / Move down to set the frame order.",
         FilesBox(M.IMAGE_EXTS, "Pictures", ordered=True, prefs=prefs),
         lambda f, out, o, p, c: M.images_to_gif(f, out, delay_ms=o["d"], width=o["w"], loop=o["l"], progress=p),
         options=w, get_opts=g, per_file=False, min_files=2, run_text="Make GIF")

    sp, gw2, cols = spin("Speed", 10, 1000, " %", 10), spin("Width", 0, 4000, " px", 20), spin("Colours", 2, 256, "", 16)
    sp.setValue(100)
    cols.setValue(256)
    rev = QCheckBox("Play backwards")
    w, g = _opts([("Speed", sp), ("Width (0 = keep)", gw2), ("Colours", cols), ("", rev)],
                 lambda: {"s": sp.value(), "w": gw2.value(), "c": cols.value(), "r": rev.isChecked()})
    page("Edit GIF", "Change the speed, direction, size and colours of an animated GIF.",
         FilesBox((".gif",), "GIF files", prefs=prefs),
         lambda f, out, o, p, c: M.gif_edit(f[0], out, speed_pct=o["s"], reverse=o["r"], width=o["w"], colors=o["c"]),
         options=w, get_opts=g, run_text="Apply")

    ffmt = combo("Format", [("PNG", "png"), ("JPG", "jpg")])
    w, g = _opts([("Save frames as", ffmt)], lambda: {"f": ffmt.currentData()})
    page("GIF → frames", "Save every frame of a GIF as a separate picture.", FilesBox((".gif", ".webp"), "GIF files", prefs=prefs),
         lambda f, out, o, p, c: M.gif_to_frames(f[0], out, fmt=o["f"]), options=w, get_opts=g, run_text="Extract")

    st, du, fp, vw = (QDoubleSpinBox(), QDoubleSpinBox(), spin("Frames per second", 1, 30, " fps"), spin("Width", 64, 1920, " px", 20))
    for s_, hi in ((st, 36000), (du, 600)):
        s_.setRange(0, hi)
        s_.setDecimals(1)
        s_.setSuffix(" s")
    du.setValue(5)
    fp.setValue(12)
    vw.setValue(480)
    st.setAccessibleName("Start time")
    du.setAccessibleName("Length")
    w, g = _opts([("Start at", st), ("Length (0 = to the end)", du), ("Speed", fp), ("Width", vw)],
                 lambda: {"s": st.value(), "d": du.value(), "f": fp.value(), "w": vw.value()})
    page("Video → GIF", "Make an animated GIF from part of a video.", FilesBox(VIDEOS, "Videos", prefs=prefs),
         lambda f, out, o, p, c: M.video_to_gif(f[0], out, start=o["s"], duration=o["d"], fps=o["f"], width=o["w"], cancel=c),
         options=w, get_opts=g, needs=ff, run_text="Make GIF")

    vf = combo("Format", [("MP4 (works everywhere)", "mp4"), ("WebM", "webm"), ("MKV", "mkv"), ("MOV", "mov")])
    vq = combo("Quality", [("High", "20"), ("Balanced", "26"), ("Small file", "32")])
    vq.setCurrentIndex(1)
    vh = combo("Size", [("Keep size", "0"), ("1080p", "1080"), ("720p", "720"), ("480p", "480")])
    w, g = _opts([("Convert to", vf), ("Quality", vq), ("Height", vh)],
                 lambda: {"f": vf.currentData(), "q": int(vq.currentData()), "h": int(vh.currentData())})
    page("Convert video", "Change a video's format, size or quality. GIFs can be converted to MP4/WebM too.",
         FilesBox(VIDEOS, "Videos", prefs=prefs),
         lambda f, out, o, p, c: M.gif_to_video(f[0], out, fmt=o["f"], cancel=c) if f[0].suffix.lower() == ".gif" and o["f"] in ("mp4", "webm")
         else M.convert_video(f[0], out, fmt=o["f"], crf=o["q"], max_height=o["h"], cancel=c),
         options=w, get_opts=g, needs=ff)

    ts, te = QDoubleSpinBox(), QDoubleSpinBox()
    for s_ in (ts, te):
        s_.setRange(0, 36000)
        s_.setDecimals(1)
        s_.setSuffix(" s")
    ts.setAccessibleName("Start")
    te.setAccessibleName("End")
    w, g = _opts([("Start", ts), ("End (0 = to the end)", te)], lambda: {"s": ts.value(), "e": te.value()})
    page("Trim video", "Cut a video to a shorter clip.", FilesBox(VIDEOS, "Videos", prefs=prefs),
         lambda f, out, o, p, c: M.trim_video(f[0], out, start=o["s"], end=o["e"], cancel=c), options=w, get_opts=g,
         needs=ff, run_text="Trim")

    af = combo("Format", [("MP3", "mp3"), ("M4A (AAC)", "m4a"), ("WAV", "wav")])
    w, g = _opts([("Save as", af)], lambda: {"f": af.currentData()})
    page("Extract audio", "Save the sound of a video as an audio file.", FilesBox(VIDEOS, "Videos", prefs=prefs),
         lambda f, out, o, p, c: M.extract_audio(f[0], out, fmt=o["f"], cancel=c), options=w, get_opts=g, needs=ff,
         run_text="Extract")

    link = QPushButton("More online tools: ezgif.com")
    link.setProperty("flat", True)
    link.setAccessibleName("Open ezgif.com")
    link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(M.EZGIF_URL)))
    return ToolsWindow("Convert Media", pages, footer=link)
