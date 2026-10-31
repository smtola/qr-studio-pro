#!/usr/bin/env bash
# Build TL Studio Pro on macOS: .app bundle and drag-and-drop .dmg.
#   scripts/build_macos.sh                 # host architecture (arm64 on Apple Silicon, x86_64 on Intel)
#   ARCH=x86_64 scripts/build_macos.sh     # only works with an x86_64 Python (e.g. under Rosetta)
#   SKIP_TESTS=1 scripts/build_macos.sh
# Output goes to dist/:  "TL Studio Pro.app" and TLStudioPro-<version>-<arch>.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "ERROR: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[[ "$(uname -s)" == "Darwin" ]] || fail "This script must run on macOS (PyInstaller cannot cross-compile)."
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || fail "python3 not found. Install Python 3.12+ (https://www.python.org or 'brew install python@3.12')."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || fail "Python 3.12 or newer is required."

HOST_ARCH=$(uname -m)
ARCH=${ARCH:-$HOST_ARCH}
PY_ARCH=$("$PY" -c 'import platform; print(platform.machine())')
[[ "$PY_ARCH" == "$ARCH" || "$ARCH" == "universal2" ]] || fail "Python is $PY_ARCH but ARCH=$ARCH was requested. Use a matching Python (e.g. 'arch -x86_64 ...')."
echo "Python $("$PY" -V | cut -d' ' -f2), target architecture: $ARCH"

step "Creating virtual environment (.venv-build)"
[[ -d .venv-build ]] || "$PY" -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements-dev.txt

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  step "Running tests"
  QT_QPA_PLATFORM=offscreen python -m pytest || fail "Tests failed (set SKIP_TESTS=1 to bypass)."
fi

step "Generating icons"
python scripts/make_icons.py
VERSION=$(python -c 'from src.version import VERSION; print(VERSION)')

step "Building .app with PyInstaller"
rm -rf build "dist/TL Studio Pro.app" dist/TLStudioPro
QRSP_TARGET_ARCH="$ARCH" python -m PyInstaller --noconfirm --distpath dist --workpath build packaging/qr_studio.spec
APP="dist/TL Studio Pro.app"
[[ -d "$APP" ]] || fail "PyInstaller did not produce $APP"

step "Self-test of the built app"
"$APP/Contents/MacOS/TLStudioPro" --selftest || fail "The built app failed its self-test."

step "Signing"
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$APP"
  codesign --verify --deep --strict "$APP" && echo "Signed with: $CODESIGN_IDENTITY"
  echo "Notarization is a separate step - see docs/PACKAGING.md."
else
  # PyInstaller on Apple Silicon applies an ad-hoc signature, which is enough to launch locally only.
  echo "CODESIGN_IDENTITY not set: the app is NOT signed with a Developer ID and NOT notarized."
fi

step "Building .dmg"
DMG="dist/TLStudioPro-${VERSION}-${ARCH}.dmg"
rm -f "$DMG"
dmgbuild -s packaging/dmg_settings.py -D app="$APP" "TL Studio Pro" "$DMG" || fail "dmgbuild failed"
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then codesign --force --sign "$CODESIGN_IDENTITY" "$DMG"; fi

step "Done"
ls -lh dist
echo "Unsigned/un-notarized builds trigger Gatekeeper warnings on other Macs (right-click > Open). See docs/PACKAGING.md."
