"""Headless self-test used to verify installed/packaged builds.

    QR Studio Pro --selftest

Renders a design with centre logo, colours, frame and Khmer text, exports PNG, JPG,
SVG and PDF into a temporary folder, checks the files and (when the optional
`zxingcpp` decoder is installed) scans the PNG. The report goes to stdout and to
<user data dir>/selftest.txt because packaged GUI builds have no console.
Exit code 0 means everything worked.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from PIL import Image, ImageDraw

from src.utils.paths import user_data_dir
from src.version import APP_NAME, VERSION

URL = "https://example.com/selftest?lang=km"


def _make_logo(path: Path) -> None:
    im = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, 319, 239), fill=(30, 111, 224, 255))
    d.rectangle((130, 70, 190, 170), fill=(255, 255, 255, 255))
    im.save(path)


def run_selftest() -> int:
    lines: list[str] = [f"{APP_NAME} {VERSION} self-test", f"python {sys.version.split()[0]} on {sys.platform}"]
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="qrs-selftest-"))

    def step(name: str, fn) -> None:
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"PASS  {name}" + (f" - {detail}" if detail else ""))
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL  {name}: {exc}")
            lines.append(traceback.format_exc(limit=3))

    try:
        from src.core.export_manager import export_to_file
        from src.core.logo_composer import load_logo
        from src.models.project_settings import ProjectSettings

        logo_path = tmp / "logo.png"
        _make_logo(logo_path)
        s = ProjectSettings()
        s.content.url = URL
        s.logo.path = str(logo_path)
        s.colors.foreground, s.colors.background = "#0B3D91", "#FFFFFF"
        s.colors.module_style = "rounded"
        s.eyes.follow_foreground = False
        s.eyes.outer_color, s.eyes.inner_color = "#0B3D91", "#1E6FE0"
        s.frame.type, s.frame.title, s.frame.caption = "rounded", "SCAN ME", "ទស្សនាគេហទំព័ររបស់យើង"
        s.export.width_px = 900
        s.sanitize()

        step("load logo", lambda: f"{load_logo(logo_path).image.width}px wide")
        for fmt in ("png", "jpg", "svg", "pdf"):
            def do(fmt=fmt):
                res = export_to_file(s, tmp / f"out.{fmt}", overwrite=True)
                size = res.path.stat().st_size
                if size < 500:
                    raise RuntimeError("output file is suspiciously small")
                return f"{res.width}x{res.height}px, {size} bytes"

            step(f"export {fmt.upper()}", do)

        def scan():
            try:
                import cv2
                import numpy as np
            except ImportError:
                return "skipped (decoder not bundled)"
            img = Image.open(tmp / "out.png").convert("RGB")
            padded = Image.new("RGB", (img.width + 200, img.height + 200), "white")
            padded.paste(img, (100, 100))
            text, _, _ = cv2.QRCodeDetector().detectAndDecode(np.array(padded)[:, :, ::-1].copy())
            if text != URL:
                raise RuntimeError("exported PNG could not be decoded")
            return "decoded OK"

        step("scan exported PNG", scan)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append("RESULT: " + ("OK" if ok else "FAILED"))
    report = "\n".join(lines)
    print(report)
    try:
        user_data_dir().mkdir(parents=True, exist_ok=True)
        (user_data_dir() / "selftest.txt").write_text(report + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1
