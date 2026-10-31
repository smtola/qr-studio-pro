from pathlib import Path

import pytest
from PIL import Image

from src.convert.common import ConvertError, find_ffmpeg
from src.convert import media as m

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="FFmpeg not installed")


def _img(path: Path, size=(200, 120), color="red", mode="RGB"):
    Image.new(mode, size, color).save(path)
    return path


def _gif(path: Path, n=4):
    frames = [Image.new("RGB", (80, 60), c) for c in ("red", "green", "blue", "yellow")[:n]]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return path


def test_convert_formats(tmp_path):
    src = _img(tmp_path / "a.png", mode="RGBA", color=(255, 0, 0, 100))
    for fmt in ("jpg", "webp", "gif", "bmp", "tiff", "ico", "png"):
        out = m.convert_image(src, tmp_path, fmt=fmt)
        assert out.suffix == f".{fmt}" and out.stat().st_size > 0
        Image.open(out).load()
    with pytest.raises(ConvertError):
        m.convert_image(src, tmp_path, fmt="xyz")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"nope")
    with pytest.raises(ConvertError):
        m.convert_image(bad, tmp_path)


def test_resize_crop_transform_compress(tmp_path):
    src = _img(tmp_path / "p.jpg", (400, 200))
    assert Image.open(m.resize_image(src, tmp_path, width=100)).size == (100, 50)
    assert Image.open(m.resize_image(src, tmp_path, percent=50)).size == (200, 100)
    assert Image.open(m.resize_image(src, tmp_path, width=50, height=50, keep_aspect=False)).size == (50, 50)
    assert Image.open(m.resize_image(src, tmp_path, width=100, height=100)).size == (100, 50)
    with pytest.raises(ConvertError):
        m.resize_image(src, tmp_path)
    assert Image.open(m.crop_image(src, tmp_path, left=10, top=10, width=100, height=50)).size == (100, 50)
    with pytest.raises(ConvertError):
        m.crop_image(src, tmp_path, left=350, top=0, width=100, height=50)
    assert Image.open(m.transform_image(src, tmp_path, rotate=90)).size == (200, 400)
    with pytest.raises(ConvertError):
        m.transform_image(src, tmp_path, rotate=45)
    big = _img(tmp_path / "big.jpg", (1500, 1000))
    small = m.compress_image(big, tmp_path, quality=40, max_side=600)
    assert max(Image.open(small).size) == 600 and small.stat().st_size < big.stat().st_size
    png = _img(tmp_path / "x.png", (300, 300))
    assert m.compress_image(png, tmp_path).suffix == ".png"


def test_gif_pipeline(tmp_path):
    files = [_img(tmp_path / f"f{i}.png", (100, 80), c) for i, c in enumerate(("red", "green", "blue"))]
    g = m.images_to_gif(files, tmp_path, delay_ms=150, width=60)
    im = Image.open(g)
    assert im.n_frames == 3 and im.size[0] == 60
    frames = m.gif_to_frames(g, tmp_path)
    assert len(frames) == 3
    edited = m.gif_edit(g, tmp_path, speed_pct=200, reverse=True, width=30, colors=16)
    e = Image.open(edited)
    assert e.n_frames == 3 and e.size[0] == 30 and e.info["duration"] <= 80
    with pytest.raises(ConvertError):
        m.images_to_gif(files[:1], tmp_path)
    with pytest.raises(ConvertError):
        m.gif_edit(_img(tmp_path / "s.gif"), tmp_path)
    with pytest.raises(ConvertError):
        m.gif_edit(g, tmp_path, speed_pct=5)
    resized = m.resize_image(g, tmp_path, width=40)
    assert Image.open(resized).n_frames == 3


@needs_ffmpeg
def test_video_pipeline(tmp_path):
    g = _gif(tmp_path / "src.gif")
    mp4 = m.gif_to_video(g, tmp_path)
    assert mp4.suffix == ".mp4" and mp4.stat().st_size > 500
    back = m.video_to_gif(mp4, tmp_path, duration=1, fps=5, width=64)
    assert Image.open(back).n_frames >= 2
    webm = m.convert_video(mp4, tmp_path, fmt="webm", max_height=48)
    assert webm.stat().st_size > 0
    again = m.convert_video(mp4, tmp_path, fmt="mp4", crf=30)
    assert again.name != mp4.name
    trimmed = m.trim_video(mp4, tmp_path, start=0.1, end=0.3)
    assert trimmed.stat().st_size > 0
    frames = m.video_to_frames(mp4, tmp_path, fps=5)
    assert len(frames) >= 1
    with pytest.raises(ConvertError):
        m.trim_video(mp4, tmp_path, start=2, end=1)
    with pytest.raises(ConvertError):
        m.convert_video(mp4, tmp_path, fmt="exe")


def test_ffmpeg_missing_message(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "find_ffmpeg", lambda: None)
    g = _gif(tmp_path / "x.gif")
    with pytest.raises(ConvertError, match="FFmpeg"):
        m.gif_to_video(g, tmp_path)
