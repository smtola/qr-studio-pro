from __future__ import annotations

import hashlib
import http.server
import json
import threading

import pytest

from src.services import updater
from src.services.updater import Asset, UpdateError, check_for_update, download_asset, is_newer, parse_manifest, parse_version


def test_version_ordering():
    assert is_newer("1.10.0", "1.9.9")
    assert not is_newer("1.0.0", "1.0.0")
    assert is_newer("1.0.1", "1.0")
    assert not is_newer("1.2.0-beta", "1.2.0")
    assert is_newer("1.2.0", "1.2.0-beta")
    assert parse_version("v2.0") == (2, 0, 0, 0, 1)
    with pytest.raises(UpdateError):
        parse_version("banana")


def manifest(version="9.0.0", **kw):
    d = {"version": version, "notes": "n", "assets": kw.get("assets", {})}
    return json.dumps(d)


def test_manifest_rejects_bad_input():
    for bad in ("not json", "[]", json.dumps({"version": 3}), json.dumps({"version": "x.y"})):
        with pytest.raises(UpdateError):
            parse_manifest(bad)
    with pytest.raises(UpdateError):   # plain http for an installer is refused
        parse_manifest(manifest(assets={"windows": {"url": "http://example.com/a.exe", "sha256": "0" * 64}}))
    # assets without a valid checksum are ignored, never trusted
    info = parse_manifest(manifest(assets={"windows": {"url": "https://example.com/a.exe", "sha256": "zz"}}))
    assert info.assets == {}


def test_check_requires_https_and_url(monkeypatch):
    monkeypatch.setattr(updater, "manifest_url", lambda: "")    # independent of the configured feed
    with pytest.raises(UpdateError):
        check_for_update("http://example.com/update.json")
    with pytest.raises(UpdateError, match="not set up"):
        check_for_update("")


@pytest.fixture
def server(tmp_path):
    payload = b"MZ" + b"installer-bytes" * 5000
    files = {"/QRStudioPro-9.0.0-Setup.exe": payload}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path == "/update.json":
                body = json.dumps({"version": "9.0.0", "notes": "New", "assets": {updater.platform_key(): {
                    "url": f"http://127.0.0.1:{self.server.server_port}/QRStudioPro-9.0.0-Setup.exe",
                    "sha256": hashlib.sha256(payload).hexdigest()}}}).encode()
            elif self.path in files:
                body = files[self.path]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, payload
    srv.shutdown()


def test_check_download_and_verify(server):
    srv, payload = server
    base = f"http://127.0.0.1:{srv.server_port}"
    assert check_for_update(f"{base}/update.json", current="9.0.0", allow_insecure=True) is None
    info = check_for_update(f"{base}/update.json", current="1.0.0", allow_insecure=True)
    assert info and info.version == "9.0.0"
    seen = []
    path = download_asset(info.asset_for_this_computer(), progress=lambda d, t: seen.append(d), allow_insecure=True)
    try:
        assert path.read_bytes() == payload and seen
    finally:
        path.unlink()
        path.parent.rmdir()


def test_tampered_download_is_discarded(server):
    srv, _ = server
    a = Asset(f"http://127.0.0.1:{srv.server_port}/QRStudioPro-9.0.0-Setup.exe", "0" * 64)
    with pytest.raises(UpdateError, match="integrity"):
        download_asset(a, allow_insecure=True)


def test_unsafe_filename_and_missing_file(server):
    srv, _ = server
    with pytest.raises(UpdateError):
        download_asset(Asset(f"http://127.0.0.1:{srv.server_port}/evil.sh", "0" * 64), allow_insecure=True)
    with pytest.raises(UpdateError):
        download_asset(Asset(f"http://127.0.0.1:{srv.server_port}/nope.exe", "0" * 64), allow_insecure=True)


def test_unreachable_server_message():
    with pytest.raises(UpdateError, match="Could not reach"):
        check_for_update("http://127.0.0.1:9/update.json", allow_insecure=True)
