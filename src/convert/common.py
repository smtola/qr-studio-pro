from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class ConvertError(ValueError):
    """User-facing conversion failure."""


def unique_path(directory: str | Path, stem: str, ext: str) -> Path:
    """`directory/stem.ext`, or `stem (2).ext` ... if it already exists. Never overwrites."""
    d = Path(directory)
    if not d.is_dir():
        raise ConvertError(f"The folder '{d}' does not exist.")
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .") or "output"
    p = d / f"{stem}{ext}"
    n = 2
    while p.exists():
        p = d / f"{stem} ({n}){ext}"
        n += 1
    return p


def require_file(path: str | Path, exts: tuple[str, ...]) -> Path:
    p = Path(path)
    if not p.is_file():
        raise ConvertError(f"The file '{p.name}' could not be found.")
    if exts and p.suffix.lower() not in exts:
        raise ConvertError(f"'{p.name}' is not a supported file type here (expected {', '.join(exts)}).")
    return p


def find_office() -> str | None:
    """Path to LibreOffice's soffice, if installed (gives the best Excel/Word -> PDF fidelity)."""
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(p).is_file():
            return p
    return None


def office_convert(src: Path, out_dir: Path, target: str, timeout: int = 180) -> Path:
    """Convert with headless LibreOffice. Returns the produced file (named by LibreOffice)."""
    office = find_office()
    if not office:
        raise ConvertError("This conversion needs LibreOffice (free) installed on your computer.")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="tlstudio-") as profile:
        cmd = [office, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--convert-to", target,
               "--outdir", str(out_dir), str(src)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ConvertError("LibreOffice took too long to convert this file.") from None
        except (subprocess.CalledProcessError, OSError) as e:
            raise ConvertError(f"LibreOffice could not convert this file ({e}).") from None
    out = out_dir / (src.stem + "." + target.split(":")[0])
    if not out.is_file():
        raise ConvertError("The conversion produced no output file.")
    return out


def find_ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:                                   # the FFmpeg bundled with the optional imageio-ffmpeg package
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:  # noqa: BLE001
        pass
    for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"):
        if Path(c).is_file():
            return c
    return None
