"""Download a video, audio track or picture from a public link (YouTube, TikTok, Facebook, Instagram, X ...).

Built on yt-dlp. Only public links work; this never bypasses logins, DRM or paywalls. The caller is responsible
for having the right to keep the content (the UI shows a notice). Errors become `ConvertError` with plain wording."""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .common import ConvertError, find_ffmpeg

RIGHTS_NOTICE = ("Only download content that you own, that is in the public domain, or that you have permission to "
                 "keep. Platform terms of service may forbid downloads, and copyright law applies.")

PLATFORMS = {
    "YouTube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "TikTok": ("tiktok.com",),
    "Facebook": ("facebook.com", "fb.watch", "fb.com"),
    "Instagram": ("instagram.com",),
    "X": ("x.com", "twitter.com", "t.co"),
}

KINDS = ("video", "audio", "image")
QUALITIES = ("best", "1080", "720", "480", "360")
AUDIO_FORMATS = ("mp3", "m4a")


def clean_url(text: str) -> str:
    """Normalise one pasted link. Raises ConvertError if it is not an http(s) link."""
    t = (text or "").strip().strip("<>\"'")
    if t and "://" not in t and "." in t.split("/")[0]:
        t = "https://" + t
    u = urlparse(t)
    if u.scheme not in ("http", "https") or not u.netloc or " " in t:
        raise ConvertError("This does not look like a web link. Paste a full link that starts with https://")
    return t


def split_urls(text: str) -> list[str]:
    """All distinct links in a block of text (one per line or separated by spaces/commas)."""
    out: list[str] = []
    for tok in re.split(r"[\s,;]+", text or ""):
        if not tok:
            continue
        try:
            u = clean_url(tok)
        except ConvertError:
            continue
        if u not in out:
            out.append(u)
    return out


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, doms in PLATFORMS.items():
        if any(host == d or host.endswith("." + d) for d in doms):
            return name
    return "Web"


def _friendly(msg: str) -> str:
    m = msg.lower()
    rules = [
        (("private", "login required", "log in", "sign in", "cookies", "members-only", "age-restricted", "confirm your age"),
         "This link needs a sign-in (it is private, members-only or age-restricted), so it cannot be downloaded."),
        (("drm",), "This video is protected by DRM and cannot be downloaded."),
        (("unsupported url", "no video could be found", "no media found", "there is no video"),
         "No video or picture could be found at this link. Check that it points to a public post."),
        (("unavailable", "removed", "deleted", "not available", "404", "does not exist"),
         "This content is unavailable. It may have been removed or is not available in your country."),
        (("urlopen error", "getaddrinfo", "timed out", "connection", "network", "unable to download webpage"),
         "Could not reach the website. Check your internet connection and try again."),
        (("ffmpeg", "ffprobe"), "FFmpeg is needed to finish this download but could not be found."),
        (("429", "too many requests", "rate"), "The website is limiting requests right now. Wait a few minutes and try again."),
    ]
    for keys, text in rules:
        if any(k in m for k in keys):
            return text
    return "The download failed. The website may have changed or blocks downloads for this link."


class Cancelled(Exception):
    pass


def _ydl_class():
    try:
        import yt_dlp
    except ImportError as e:                      # pragma: no cover
        raise ConvertError("The downloader component (yt-dlp) is missing from this installation.") from e
    return yt_dlp.YoutubeDL


def _base_opts(quiet_hook=None) -> dict:
    o = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20, "retries": 3,
         "noprogress": True, "overwrites": False, "restrictfilenames": False, "windowsfilenames": True,
         "ignoreerrors": False}
    ff = find_ffmpeg()
    if ff:
        o["ffmpeg_location"] = ff
    if quiet_hook:
        o["progress_hooks"] = [quiet_hook]
    return o


def get_info(url: str, ydl_cls=None) -> dict:
    """Title, uploader, duration, thumbnail and platform for a link (no download)."""
    url = clean_url(url)
    cls = ydl_cls or _ydl_class()
    try:
        with cls(_base_opts()) as y:
            d = y.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        raise ConvertError(_friendly(str(e))) from e
    if not d:
        raise ConvertError(_friendly("no media found"))
    if d.get("_type") == "playlist" and d.get("entries"):
        entries = [e for e in d["entries"] if e]
        d = entries[0] if entries else d
    return {"title": d.get("title") or "Untitled", "uploader": d.get("uploader") or d.get("channel") or "",
            "duration": d.get("duration"), "thumbnail": d.get("thumbnail") or "", "platform": detect_platform(url),
            "has_video": any((f.get("vcodec") or "none") != "none" for f in d.get("formats") or []) or bool(d.get("url")),
            "id": d.get("id") or ""}


def format_selector(kind: str, quality: str) -> str:
    if kind == "audio":
        return "bestaudio/best"
    if kind == "image":
        return "best"
    if quality in ("1080", "720", "480", "360"):
        h = int(quality)
        return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"
    return "bv*+ba/b"


def download(url: str, out_dir: str | Path, kind: str = "video", quality: str = "best", audio_format: str = "mp3",
             progress: Callable[[float, str], None] | None = None, cancel: threading.Event | None = None,
             ydl_cls=None) -> list[Path]:
    """Download one link into `out_dir`; returns the files written. Never overwrites an existing file (a repeat download
    of the same item is skipped and the existing file is returned)."""
    url = clean_url(url)
    if kind not in KINDS:
        raise ConvertError("Unknown download type.")
    out = Path(out_dir)
    if not out.is_dir():
        raise ConvertError(f"The folder '{out}' does not exist.")
    cls = ydl_cls or _ydl_class()

    def hook(d: dict) -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress and d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes") or 0) / tot if tot else 0.0
            progress(min(frac, 1.0), (d.get("_speed_str") or "").strip())
        elif progress and d.get("status") == "finished":
            progress(1.0, "")

    opts = _base_opts(hook)
    opts["outtmpl"] = str(out / "%(title).120B [%(id)s].%(ext)s")
    opts["format"] = format_selector(kind, quality)
    if kind == "video":
        opts["merge_output_format"] = "mp4"
    elif kind == "audio":
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": audio_format if audio_format in AUDIO_FORMATS else "mp3",
                                   "preferredquality": "192"}]
    before = {p for p in out.iterdir()}
    try:
        with cls(opts) as y:
            info = y.extract_info(url, download=True)
            if info and info.get("_type") == "playlist" and info.get("entries"):
                info = next((e for e in info["entries"] if e), info)
            reported = []
            for rd in (info or {}).get("requested_downloads") or []:
                fp = rd.get("filepath") or rd.get("_filename")
                if fp:
                    reported.append(Path(fp))
    except Cancelled:
        _cleanup_partial(out, before)
        raise ConvertError("Download cancelled.")
    except Exception as e:  # noqa: BLE001
        if cancel is not None and cancel.is_set():
            _cleanup_partial(out, before)
            raise ConvertError("Download cancelled.") from e
        raise ConvertError(_friendly(str(e))) from e
    files = [p for p in reported if p.is_file()]
    if not files:
        files = sorted((p for p in out.iterdir() if p not in before and p.suffix not in (".part", ".ytdl")),
                       key=lambda p: p.stat().st_mtime)
    if not files:
        raise ConvertError("Nothing was downloaded. The file may already exist in the folder, or the post has no media.")
    return files


def _cleanup_partial(out: Path, before: set[Path]) -> None:
    for p in out.iterdir():
        if p not in before and (p.suffix in (".part", ".ytdl") or p.name.endswith(".part-Frag0")):
            try:
                p.unlink()
            except OSError:
                pass
