"""Independent "does it really scan?" check: decode the rendered code with OpenCV's QR detector.

A pass proves one decoder can read this exact image; it is still not a guarantee for every phone,
print size or lighting. If OpenCV is not installed the check reports ``unavailable``."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

try:  # optional at run time; bundled in the release builds
    import cv2
    import numpy as np
except Exception:  # noqa: BLE001
    cv2 = None
    np = None

OK, FAIL, UNAVAILABLE = "ok", "fail", "unavailable"


@dataclass(frozen=True)
class ScanResult:
    status: str
    message: str


def available() -> bool:
    return cv2 is not None


def _decode(img: Image.Image) -> str:
    padded = Image.new("RGB", (img.width + 160, img.height + 160), "white")
    padded.paste(img, (80, 80))
    arr = np.array(padded)[:, :, ::-1].copy()
    text, _pts, _ = cv2.QRCodeDetector().detectAndDecode(arr)
    return text or ""


def check_scan(prep, image: Image.Image) -> ScanResult:
    """`prep` is a Prepared (scene geometry + payload); `image` is the rendered raster of prep.scene."""
    if cv2 is None:
        return ScanResult(UNAVAILABLE, "Scan check is not available in this build.")
    rgba = image.convert("RGBA")
    flat = Image.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba.getchannel("A"))
    want = prep.qrm.payload
    sc = flat.width / prep.scene.width
    bx, by, bw, bh = prep.scene.qr_block
    crop = flat.crop((max(int(bx * sc), 0), max(int(by * sc), 0),
                      min(int((bx + bw) * sc) + 1, flat.width), min(int((by + bh) * sc) + 1, flat.height)))
    for cand in (crop, flat):
        for k in (1.0, 0.75, 0.5):
            im = cand if k == 1.0 else cand.resize((max(int(cand.width * k), 60), max(int(cand.height * k), 60)),
                                                   Image.LANCZOS)
            got = _decode(im)
            if got:
                if got == want:
                    if any(a.level == "error" and a.code in ("contrast", "inverted") for a in prep.advice):
                        return ScanResult(FAIL, "A test decoder can read it only because it boosts contrast; phone "
                                                "cameras will probably struggle. Use darker modules on a lighter background.")
                    return ScanResult(OK, "Scans OK in this test. Still test with your own phone at print size.")
                return ScanResult(FAIL, "The code decodes to different content than expected.")
    return ScanResult(FAIL, "A test scanner could not read this code. Increase contrast, shrink the logo "
                            "or raise the error-correction level.")
