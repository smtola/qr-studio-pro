from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QRSP_DATA_DIR", str(Path(__file__).parent / ".userdata"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.project_settings import ProjectSettings  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV is the independent QR decoder used by the scan tests")
import numpy as np  # noqa: E402


def decode_qr(img: Image.Image) -> str:
    """Decode with OpenCV (an implementation independent of the `qrcode` encoder)."""
    rgb = Image.new("RGB", img.size, "white")
    rgb.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
    det = cv2.QRCodeDetector()
    for scale in (1.0, 0.5, 0.75, 1.5):
        im = rgb if scale == 1.0 else rgb.resize((int(rgb.width * scale), int(rgb.height * scale)), Image.LANCZOS)
        padded = Image.new("RGB", (im.width + 200, im.height + 200), "white")
        padded.paste(im, (100, 100))
        text, _pts, _ = det.detectAndDecode(np.array(padded)[:, :, ::-1].copy())
        if text:
            return text
    return ""


@pytest.fixture
def settings() -> ProjectSettings:
    return ProjectSettings()


@pytest.fixture
def logo_png(tmp_path) -> Path:
    im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 380, 280), fill=(220, 38, 38, 255))
    d.rectangle((150, 100, 250, 200), fill=(255, 255, 255, 255))
    p = tmp_path / "logo.png"
    im.save(p)
    return p


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["pytest"])
    yield app
