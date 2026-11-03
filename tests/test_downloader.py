"""Media downloader: link handling, error mapping, download flow with a fake yt-dlp (no network)."""
from __future__ import annotations

import threading

import pytest

from src.convert import downloader as DL
from src.convert.common import ConvertError


def test_clean_and_split_urls():
    assert DL.clean_url(" www.tiktok.com/@a/video/1 ") == "https://www.tiktok.com/@a/video/1"
    for bad in ("", "hello world", "javascript:alert(1)", "ftp://x.com/a", "file:///etc/passwd"):
        with pytest.raises(ConvertError):
            DL.clean_url(bad)
    text = "https://youtu.be/a, https://youtu.be/a\nhttps://x.com/u/status/1 junk"
    assert DL.split_urls(text) == ["https://youtu.be/a", "https://x.com/u/status/1"]


@pytest.mark.parametrize("url,name", [("https://www.youtube.com/watch?v=1", "YouTube"), ("https://youtu.be/1", "YouTube"),
                                      ("https://vm.tiktok.com/x", "TikTok"), ("https://fb.watch/x", "Facebook"),
                                      ("https://www.instagram.com/p/x", "Instagram"), ("https://twitter.com/a/status/1", "X"),
                                      ("https://x.com/a/status/1", "X"), ("https://evilyoutube.com/x", "Web"),
                                      ("https://example.com", "Web")])
def test_detect_platform(url, name):
    assert DL.detect_platform(url) == name


def test_format_selector():
    assert DL.format_selector("audio", "best") == "bestaudio/best"
    assert "height<=720" in DL.format_selector("video", "720")
    assert DL.format_selector("video", "best") == "bv*+ba/b"


class FakeYDL:
    mode = "ok"
    last_opts = None

    def __init__(self, opts):
        FakeYDL.last_opts = opts
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        if FakeYDL.mode == "private":
            raise Exception("ERROR: [Instagram] Login required to view this private video")
        if FakeYDL.mode == "net":
            raise Exception("<urlopen error [Errno -2] getaddrinfo failed>")
        if not download:
            return {"title": "Clip", "uploader": "me", "duration": 12, "thumbnail": "t", "id": "abc", "formats": [{"vcodec": "avc1"}]}
        from pathlib import Path
        out = Path(self.opts["outtmpl"]).parent / "Clip [abc].mp4"
        for h in self.opts["progress_hooks"]:
            h({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            h({"status": "finished"})
        out.write_bytes(b"data")
        return {"title": "Clip", "requested_downloads": [{"filepath": str(out)}]}


def test_download_ok_and_options(tmp_path):
    FakeYDL.mode = "ok"
    seen = []
    files = DL.download("https://youtu.be/abc", tmp_path, "video", "720", progress=lambda f, s: seen.append(f), ydl_cls=FakeYDL)
    assert [p.name for p in files] == ["Clip [abc].mp4"] and seen == [0.5, 1.0]
    o = FakeYDL.last_opts
    assert o["noplaylist"] and o["merge_output_format"] == "mp4" and "720" in o["format"] and o["overwrites"] is False
    DL.download("https://youtu.be/abc", tmp_path, "audio", ydl_cls=FakeYDL)
    assert FakeYDL.last_opts["postprocessors"][0]["preferredcodec"] == "mp3"


def test_download_errors_are_plain(tmp_path):
    FakeYDL.mode = "private"
    with pytest.raises(ConvertError, match="sign-in"):
        DL.download("https://www.instagram.com/p/x", tmp_path, ydl_cls=FakeYDL)
    FakeYDL.mode = "net"
    with pytest.raises(ConvertError, match="internet"):
        DL.download("https://youtu.be/abc", tmp_path, ydl_cls=FakeYDL)
    with pytest.raises(ConvertError, match="does not exist"):
        DL.download("https://youtu.be/abc", tmp_path / "nope", ydl_cls=FakeYDL)
    with pytest.raises(ConvertError):
        DL.download("https://youtu.be/abc", tmp_path, kind="zip", ydl_cls=FakeYDL)


def test_cancel_during_download(tmp_path):
    FakeYDL.mode = "ok"
    ev = threading.Event()
    ev.set()
    with pytest.raises(ConvertError, match="cancelled"):
        DL.download("https://youtu.be/abc", tmp_path, cancel=ev, ydl_cls=FakeYDL)
    assert not list(tmp_path.iterdir())


def test_get_info(tmp_path):
    FakeYDL.mode = "ok"
    i = DL.get_info("https://youtu.be/abc", ydl_cls=FakeYDL)
    assert i["title"] == "Clip" and i["platform"] == "YouTube" and i["has_video"]
