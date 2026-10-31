"""Image / GIF / video conversions (an offline take on what ezgif.com offers). Images use Pillow; video and GIF
<-> video use FFmpeg when available."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from .common import ConvertError, find_ffmpeg, require_file, unique_path

Progress = Callable[[int, int], None] | None
EZGIF_URL = "https://ezgif.com/"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".ico")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".gif", ".flv", ".wmv")
IMAGE_FORMATS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "gif": "GIF", "bmp": "BMP", "tiff": "TIFF", "ico": "ICO"}


def _open(path: Path):
    from PIL import Image, ImageOps
    try:
        im = Image.open(path)
        im.load() if getattr(im, "n_frames", 1) == 1 else None
        return im
    except Exception:  # noqa: BLE001
        raise ConvertError(f"'{path.name}' is not a readable image.") from None


def _save(im, out: Path, fmt: str, quality: int = 90) -> None:
    fmt = fmt.lower()
    kw: dict = {}
    if fmt in ("jpg", "jpeg"):
        if im.mode != "RGB":
            from PIL import Image
            bg = Image.new("RGB", im.size, "white")
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.getchannel("A"))
            im = bg
        kw = {"quality": quality, "optimize": True}
    elif fmt == "webp":
        kw = {"quality": quality}
    elif fmt == "ico":
        im = im.convert("RGBA")
        kw = {"sizes": [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)] or [(16, 16)]}
    elif fmt == "png":
        kw = {"optimize": True}
    try:
        im.save(out, IMAGE_FORMATS[fmt], **kw)
    except OSError as e:
        raise ConvertError(f"The image could not be saved: {e}") from None


# ------------------------------------------------------------------------------------------ images
def convert_image(src, out_dir, *, fmt: str = "png", quality: int = 90, progress: Progress = None) -> Path:
    fmt = fmt.lower().replace("jpeg", "jpg")
    if fmt not in IMAGE_FORMATS:
        raise ConvertError("Choose a supported image format.")
    s = require_file(src, IMAGE_EXTS)
    from PIL import ImageOps
    im = _open(s)
    animated = getattr(im, "n_frames", 1) > 1
    out = unique_path(out_dir, s.stem, f".{fmt}")
    if animated and fmt in ("gif", "webp"):
        im.save(out, IMAGE_FORMATS[fmt], save_all=True, loop=0, duration=im.info.get("duration", 80))
        return out
    im.seek(0)
    _save(ImageOps.exif_transpose(im), out, fmt, quality)
    return out


def resize_image(src, out_dir, *, width: int = 0, height: int = 0, percent: int = 0, keep_aspect: bool = True,
                 progress: Progress = None) -> Path:
    from PIL import Image
    s = require_file(src, IMAGE_EXTS)
    im = _open(s)
    w0, h0 = im.size
    if percent:
        w, h = max(1, round(w0 * percent / 100)), max(1, round(h0 * percent / 100))
    else:
        if not width and not height:
            raise ConvertError("Enter a width, a height or a percentage.")
        if keep_aspect:
            k = (width / w0) if width else (height / h0)
            if width and height:
                k = min(width / w0, height / h0)
            w, h = max(1, round(w0 * k)), max(1, round(h0 * k))
        else:
            w, h = width or w0, height or h0
    if w * h > 100_000_000:
        raise ConvertError("The result would be too large.")
    out = unique_path(out_dir, f"{s.stem}-{w}x{h}", s.suffix.lower() if s.suffix.lower() != ".jpeg" else ".jpg")
    if getattr(im, "n_frames", 1) > 1 and s.suffix.lower() == ".gif":
        frames, durs = _frames(im)
        frames = [f.resize((w, h), Image.Resampling.LANCZOS) for f in frames]
        _save_gif(frames, durs, out)
    else:
        fmt = out.suffix.lstrip(".").lower()
        _save(im.resize((w, h), Image.Resampling.LANCZOS), out, "jpg" if fmt == "jpeg" else fmt)
    return out


def crop_image(src, out_dir, *, left: int = 0, top: int = 0, width: int = 0, height: int = 0,
               progress: Progress = None) -> Path:
    s = require_file(src, IMAGE_EXTS)
    im = _open(s)
    if width <= 0 or height <= 0 or left < 0 or top < 0 or left + width > im.width or top + height > im.height:
        raise ConvertError(f"The crop area must fit inside the picture ({im.width} × {im.height} px).")
    out = unique_path(out_dir, f"{s.stem}-crop", s.suffix.lower())
    _save(im.crop((left, top, left + width, top + height)), out, out.suffix.lstrip(".").replace("jpeg", "jpg"))
    return out


def transform_image(src, out_dir, *, rotate: int = 0, flip_h: bool = False, flip_v: bool = False,
                    progress: Progress = None) -> Path:
    from PIL import Image
    s = require_file(src, IMAGE_EXTS)
    im = _open(s)
    if rotate % 90:
        raise ConvertError("Rotation must be 0, 90, 180 or 270 degrees.")
    if rotate % 360:
        im = im.rotate(-rotate, expand=True)
    if flip_h:
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    out = unique_path(out_dir, f"{s.stem}-edited", s.suffix.lower())
    _save(im, out, out.suffix.lstrip(".").replace("jpeg", "jpg"))
    return out


def compress_image(src, out_dir, *, quality: int = 75, max_side: int = 0, progress: Progress = None) -> Path:
    from PIL import Image, ImageOps
    s = require_file(src, (".png", ".jpg", ".jpeg", ".webp"))
    im = ImageOps.exif_transpose(_open(s))
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    ext = ".webp" if s.suffix.lower() == ".webp" else ".jpg"
    if s.suffix.lower() == ".png":
        out = unique_path(out_dir, f"{s.stem}-small", ".png")
        if im.mode in ("RGB", "RGBA"):
            im = im.quantize(256, method=Image.Quantize.FASTOCTREE) if im.mode == "RGB" else \
                im.quantize(256, method=Image.Quantize.FASTOCTREE)
        _save(im, out, "png")
    else:
        out = unique_path(out_dir, f"{s.stem}-small", ext)
        _save(im, out, ext.lstrip("."), quality)
    return out


# ------------------------------------------------------------------------------------------ GIF
def _frames(im) -> tuple[list, list[int]]:
    from PIL import ImageSequence
    frames, durs = [], []
    for fr in ImageSequence.Iterator(im):
        durs.append(int(fr.info.get("duration", 80)) or 80)
        frames.append(fr.convert("RGBA"))
    return frames, durs


def _save_gif(frames, durs, out: Path, loop: int = 0) -> None:
    pal = [f.convert("RGB").convert("P", palette=1, colors=256) for f in frames]
    pal[0].save(out, "GIF", save_all=True, append_images=pal[1:], duration=durs, loop=loop, disposal=2, optimize=False)


def images_to_gif(files, out_dir, *, delay_ms: int = 200, loop: int = 0, width: int = 0, name: str = "animation",
                  progress: Progress = None) -> Path:
    from PIL import Image
    if len(files) < 2:
        raise ConvertError("Add at least two pictures to make an animation.")
    imgs = []
    for f in files:
        im = _open(require_file(f, IMAGE_EXTS)).convert("RGBA")
        imgs.append(im)
    w0, h0 = imgs[0].size
    w = width or w0
    h = round(h0 * w / w0)
    frames = []
    for im in imgs:
        bg = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        fit = im.copy()
        fit.thumbnail((w, h), Image.Resampling.LANCZOS)
        bg.paste(fit, ((w - fit.width) // 2, (h - fit.height) // 2), fit)
        frames.append(bg)
    out = unique_path(out_dir, name, ".gif")
    _save_gif(frames, [max(int(delay_ms), 20)] * len(frames), out, loop)
    return out


def gif_to_frames(src, out_dir, *, fmt: str = "png", progress: Progress = None) -> list[Path]:
    s = require_file(src, (".gif", ".webp", ".png"))
    im = _open(s)
    frames, _d = _frames(im)
    width = max(len(str(len(frames))), 3)
    outs = []
    for i, fr in enumerate(frames):
        p = unique_path(out_dir, f"{s.stem}-{str(i + 1).zfill(width)}", f".{fmt}")
        _save(fr, p, fmt)
        outs.append(p)
        if progress:
            progress(i + 1, len(frames))
    return outs


def gif_edit(src, out_dir, *, speed_pct: int = 100, reverse: bool = False, width: int = 0,
             colors: int = 256, progress: Progress = None) -> Path:
    from PIL import Image
    s = require_file(src, (".gif",))
    im = _open(s)
    frames, durs = _frames(im)
    if len(frames) < 2:
        raise ConvertError("This GIF is not animated.")
    if reverse:
        frames, durs = frames[::-1], durs[::-1]
    if not 10 <= speed_pct <= 1000:
        raise ConvertError("Speed must be between 10% and 1000%.")
    durs = [max(int(d * 100 / speed_pct), 20) for d in durs]
    if width and width != frames[0].width:
        h = round(frames[0].height * width / frames[0].width)
        frames = [f.resize((width, h), Image.Resampling.LANCZOS) for f in frames]
    colors = max(2, min(int(colors), 256))
    pal = [f.convert("RGB").convert("P", palette=1, colors=colors) for f in frames]
    out = unique_path(out_dir, f"{s.stem}-edited", ".gif")
    pal[0].save(out, "GIF", save_all=True, append_images=pal[1:], duration=durs, loop=0, disposal=2, optimize=True)
    return out


# ------------------------------------------------------------------------------------------ video (FFmpeg)
def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def _ffmpeg(args: list[str], cancel: threading.Event | None = None, timeout: int = 1800) -> None:
    exe = find_ffmpeg()
    if not exe:
        raise ConvertError("Video tools need FFmpeg (free). Install it, then restart the app.")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except OSError as e:
        raise ConvertError(f"FFmpeg could not be started: {e}") from None
    import time
    t0 = time.time()
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise ConvertError("Cancelled.")
        if time.time() - t0 > timeout:
            proc.kill()
            raise ConvertError("The conversion took too long and was stopped.")
        time.sleep(0.1)
    if proc.returncode != 0:
        err = (proc.stderr.read() if proc.stderr else "").strip().splitlines()
        raise ConvertError("FFmpeg could not convert this file" + (f": {err[-1]}" if err else "."))


def _ts(v: float) -> list[str]:
    return ["-ss", f"{max(v, 0):.3f}"] if v else []


def video_to_gif(src, out_dir, *, start: float = 0, duration: float = 5, fps: int = 12, width: int = 480,
                 cancel=None, progress: Progress = None) -> Path:
    s = require_file(src, VIDEO_EXTS)
    out = unique_path(out_dir, s.stem, ".gif")
    fps, width = max(1, min(int(fps), 30)), max(64, min(int(width), 1920))
    vf = f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    args = [*_ts(start), *(["-t", f"{duration}"] if duration else []), "-i", str(s), "-vf", vf, "-loop", "0", str(out)]
    try:
        _ffmpeg(args, cancel)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    return out


def gif_to_video(src, out_dir, *, fmt: str = "mp4", cancel=None, progress: Progress = None) -> Path:
    s = require_file(src, (".gif",))
    out = unique_path(out_dir, s.stem, f".{fmt}")
    codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34"] if fmt == "webm" else \
        ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    try:
        _ffmpeg(["-i", str(s), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", *codec, str(out)], cancel)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    return out


def convert_video(src, out_dir, *, fmt: str = "mp4", crf: int = 26, max_height: int = 0, cancel=None,
                  progress: Progress = None) -> Path:
    s = require_file(src, VIDEO_EXTS)
    if fmt not in ("mp4", "webm", "mkv", "mov"):
        raise ConvertError("Choose MP4, WebM, MKV or MOV.")
    out = unique_path(out_dir, f"{s.stem}-converted" if s.suffix.lower() == f".{fmt}" else s.stem, f".{fmt}")
    vf = ["-vf", f"scale=-2:{int(max_height)}"] if max_height else []
    if fmt == "webm":
        codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(max(10, min(crf + 6, 50))), "-c:a", "libopus"]
    else:
        codec = ["-c:v", "libx264", "-crf", str(max(14, min(int(crf), 40))), "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart"]
    try:
        _ffmpeg(["-i", str(s), *vf, *codec, str(out)], cancel)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    return out


def extract_audio(src, out_dir, *, fmt: str = "mp3", cancel=None, progress: Progress = None) -> Path:
    s = require_file(src, VIDEO_EXTS)
    if fmt not in ("mp3", "m4a", "wav"):
        raise ConvertError("Choose MP3, M4A or WAV.")
    out = unique_path(out_dir, s.stem, f".{fmt}")
    codec = {"mp3": ["-c:a", "libmp3lame", "-q:a", "2"], "m4a": ["-c:a", "aac", "-b:a", "192k"], "wav": ["-c:a", "pcm_s16le"]}[fmt]
    try:
        _ffmpeg(["-i", str(s), "-vn", *codec, str(out)], cancel)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    return out


def trim_video(src, out_dir, *, start: float = 0, end: float = 0, cancel=None, progress: Progress = None) -> Path:
    s = require_file(src, VIDEO_EXTS)
    if end and end <= start:
        raise ConvertError("The end time must be after the start time.")
    out = unique_path(out_dir, f"{s.stem}-trim", s.suffix.lower())
    args = [*_ts(start), "-i", str(s), *(["-t", f"{end - start:.3f}"] if end else []), "-c:v", "libx264", "-preset",
            "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)] if s.suffix.lower() != ".gif" else \
        [*_ts(start), "-i", str(s), *(["-t", f"{end - start:.3f}"] if end else []), str(out)]
    try:
        _ffmpeg(args, cancel)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    return out


def video_to_frames(src, out_dir, *, fps: float = 1, fmt: str = "png", cancel=None, progress: Progress = None) -> list[Path]:
    s = require_file(src, VIDEO_EXTS)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="tlframes-") as tmp:
        _ffmpeg(["-i", str(s), "-vf", f"fps={fps}", str(Path(tmp) / f"f-%04d.{fmt}")], cancel)
        outs = []
        for i, f in enumerate(sorted(Path(tmp).glob(f"f-*.{fmt}"))):
            p = unique_path(out_dir, f"{s.stem}-frame-{i + 1:04d}", f".{fmt}")
            f.replace(p) if f.stat().st_dev == p.parent.stat().st_dev else p.write_bytes(f.read_bytes())
            outs.append(p)
            if len(outs) > 2000:
                raise ConvertError("That would create too many frames. Lower the frames per second.")
    if not outs:
        raise ConvertError("No frames were produced.")
    return outs
