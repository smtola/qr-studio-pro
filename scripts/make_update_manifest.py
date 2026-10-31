"""Create dist/update.json (the update feed) from the installers found in dist/.

    python scripts/make_update_manifest.py --base-url https://github.com/you/repo/releases/download/v1.1.0 \
        --notes "Faster preview. New frame styles."

Upload update.json AND the installers to the same place, and point UPDATE_MANIFEST_URL (src/version.py) at the
update.json address. Run it after building on every OS; use --merge to add assets to an existing update.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.version import VERSION  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="https:// folder that will hold the installers")
    ap.add_argument("--version", default=VERSION)
    ap.add_argument("--notes", default="")
    ap.add_argument("--page", default="", help="optional https:// release page")
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    ap.add_argument("--merge", action="store_true", help="keep assets already in dist/update.json")
    a = ap.parse_args()
    if not a.base_url.startswith("https://"):
        print("ERROR: --base-url must start with https://")
        return 1
    dist = Path(a.dist)
    out = dist / "update.json"
    data = {"version": a.version, "notes": a.notes, "assets": {}}
    if a.page:
        data["page"] = a.page
    if a.merge and out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        if old.get("version") == a.version:
            data["assets"].update(old.get("assets", {}))
            data["notes"] = data["notes"] or old.get("notes", "")
    found = {
        "windows": dist / f"TLStudioPro-{a.version}-Setup.exe",
        "macos-arm64": dist / f"TLStudioPro-{a.version}-arm64.dmg",
        "macos-x86_64": dist / f"TLStudioPro-{a.version}-x86_64.dmg",
    }
    for key, path in found.items():
        if path.is_file():
            data["assets"][key] = {"url": f"{a.base_url.rstrip('/')}/{path.name}", "sha256": sha256(path)}
            print(f"  {key}: {path.name}")
    if not data["assets"]:
        print(f"ERROR: no installers for version {a.version} found in {dist}")
        return 1
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
