"""Update checking and installer download (no Qt, so it is unit-testable).

Privacy: the only network request made for a check is an HTTPS GET of the update manifest; no user data, content,
logos or identifiers are sent. Downloads are verified with SHA-256 before anything is started.

Manifest (update.json):
{
  "version": "1.1.0",
  "notes": "What is new ...",
  "page": "https://example.com/releases",            # optional, opened if no installer matches this computer
  "assets": {
    "windows":      {"url": "https://.../TLStudioPro-1.1.0-Setup.exe",        "sha256": "<hex>"},
    "macos-arm64":  {"url": "https://.../TLStudioPro-1.1.0-arm64.dmg",        "sha256": "<hex>"},
    "macos-x86_64": {"url": "https://.../TLStudioPro-1.1.0-x86_64.dmg",       "sha256": "<hex>"}
  }
}
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..utils.logging_config import get_logger
from ..version import APP_NAME, UPDATE_MANIFEST_URL, VERSION

log = get_logger("updater")
MAX_MANIFEST_BYTES = 256 * 1024
MAX_DOWNLOAD_BYTES = 600 * 1024 * 1024
TIMEOUT = 15
SAFE_FILENAME = re.compile(r"^[\w][\w.\- ]{0,120}\.(exe|dmg)$")


def _urlopen(req, timeout):
    """urlopen with certifi's CA list when available (frozen macOS builds have no system-wide Python certificates)."""
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - fall back to the platform defaults
        pass
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


class UpdateError(RuntimeError):
    """User-facing update problem."""


# ----------------------------------------------------------------------------------------- versions
def parse_version(v: str) -> tuple:
    """'1.10.2' -> (1, 10, 2, 1); '1.2.0-beta' sorts before '1.2.0' (final releases get a trailing 1)."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})(-[0-9A-Za-z.\-]+)?(?:\+[0-9A-Za-z.\-]+)?\s*$", str(v))
    if not m:
        raise UpdateError(f"Invalid version number: {v!r}")
    nums = tuple(int(x) for x in m.group(1).split("."))
    nums += (0,) * (4 - len(nums))
    return nums + (0 if m.group(2) else 1,)


def is_newer(candidate: str, current: str = VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)


# ----------------------------------------------------------------------------------------- manifest
@dataclass
class Asset:
    url: str
    sha256: str


@dataclass
class UpdateInfo:
    version: str
    notes: str = ""
    page: str = ""
    assets: dict[str, Asset] = field(default_factory=dict)

    def asset_for_this_computer(self) -> Asset | None:
        return self.assets.get(platform_key())


def platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        m = platform.machine().lower()
        return "macos-arm64" if m in ("arm64", "aarch64") else "macos-x86_64"
    return "linux"


def _check_url(url: str, allow_insecure: bool = False) -> str:
    p = urllib.parse.urlparse(url)
    ok = p.scheme == "https" or (allow_insecure and p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost"))
    if not ok or not p.netloc:
        raise UpdateError("Update addresses must start with https://")
    return url


def manifest_url() -> str:
    return os.environ.get("QRSP_UPDATE_URL", "").strip() or UPDATE_MANIFEST_URL.strip()


def parse_manifest(data: bytes | str, allow_insecure: bool = False) -> UpdateInfo:
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("The update information is not valid.") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("version"), str):
        raise UpdateError("The update information is incomplete.")
    parse_version(obj["version"])
    info = UpdateInfo(obj["version"], str(obj.get("notes", ""))[:4000])
    page = obj.get("page", "")
    if isinstance(page, str) and page:
        info.page = _check_url(page, allow_insecure)
    assets = obj.get("assets", {})
    if isinstance(assets, dict):
        for key, a in assets.items():
            if not isinstance(a, dict):
                continue
            url, sha = str(a.get("url", "")), str(a.get("sha256", "")).lower()
            if re.fullmatch(r"[0-9a-f]{64}", sha):
                info.assets[str(key)] = Asset(_check_url(url, allow_insecure), sha)
    return info


def _read(url: str, limit: int, allow_insecure: bool, opener=None) -> bytes:
    req = urllib.request.Request(_check_url(url, allow_insecure), headers={"User-Agent": f"{APP_NAME}/{VERSION}"})
    try:
        with (opener or _urlopen)(req, timeout=TIMEOUT) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"The update server answered with an error ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("Could not reach the update server. Check your internet connection.") from None
    if len(data) > limit:
        raise UpdateError("The update information is too large.")
    return data


def check_for_update(url: str | None = None, current: str = VERSION, allow_insecure: bool = False,
                     opener=None) -> UpdateInfo | None:
    """Return the newer release, or None when this version is current. Raises UpdateError on problems."""
    url = url or manifest_url()
    if not url:
        raise UpdateError("Update checking is not set up for this build.")
    info = parse_manifest(_read(url, MAX_MANIFEST_BYTES, allow_insecure, opener), allow_insecure)
    return info if is_newer(info.version, current) else None


# ----------------------------------------------------------------------------------------- download
def download_asset(asset: Asset, progress: Callable[[int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None, allow_insecure: bool = False, opener=None) -> Path:
    """Download into a private temp folder and verify SHA-256. Returns the verified file's path."""
    name = Path(urllib.parse.urlparse(asset.url).path).name
    if not SAFE_FILENAME.match(name):
        raise UpdateError("The update file has an unexpected name and was not downloaded.")
    folder = Path(tempfile.mkdtemp(prefix="qrsp-update-"))
    dest = folder / name
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(_check_url(asset.url, allow_insecure), headers={"User-Agent": f"{APP_NAME}/{VERSION}"})
        with (opener or _urlopen)(req, timeout=TIMEOUT) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            if total > MAX_DOWNLOAD_BYTES:
                raise UpdateError("The update file is unexpectedly large and was not downloaded.")
            done = 0
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Download cancelled.")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_DOWNLOAD_BYTES:
                    raise UpdateError("The update file is unexpectedly large and was not downloaded.")
                f.write(chunk)
                h.update(chunk)
                if progress:
                    progress(done, total)
        if h.hexdigest() != asset.sha256:
            raise UpdateError("The downloaded file failed its integrity check and was discarded. Please try again.")
        return dest
    except UpdateError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise UpdateError(f"The download failed: {getattr(e, 'reason', e)}") from None


# ----------------------------------------------------------------------------------------- install
def start_installer(path: Path) -> str:
    """Start the verified installer. Returns 'quit' when the app should exit now (Windows silent upgrade),
    or 'opened' when the user finishes the install themselves (macOS disk image)."""
    if sys.platform == "win32" and path.suffix.lower() == ".exe":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        # Same AppId as the installed version -> Inno Setup upgrades in place (no uninstall needed)
        # and starts the new version when it is done.
        subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         creationflags=flags, close_fds=True)
        return "quit"
    if sys.platform == "darwin" and path.suffix.lower() == ".dmg":
        subprocess.Popen(["open", str(path)])
        return "opened"
    raise UpdateError("This update cannot be installed automatically on this system.")
