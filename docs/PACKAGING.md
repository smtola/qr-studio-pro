# Packaging, signing and release notes

PyInstaller cannot cross-compile: build the Windows installer on Windows and the macOS DMG on macOS (or use the GitHub Actions workflow
`.github/workflows/build.yml`, which runs both natively plus Apple Silicon and Intel macOS runners).

## Windows

Prerequisites: Python 3.12+ (64-bit, on PATH), [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1            # installer + app folder
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Portable  # + single-file portable exe
```
- `packaging/qr_studio.spec` – PyInstaller (one-folder; `QRSP_ONEFILE=1` for the portable build). Icon `assets/icons/app.ico`, file version info generated from `src/version.py`.
- `packaging/windows_installer.iss` – per-user install (no admin), Start-menu shortcut, optional desktop shortcut, `.qrsp` file association, clean uninstall.
- The single-file exe extracts to a temp folder at launch (slower start) and is flagged by antivirus heuristics more often than the installed build; prefer the installer.
- Verification: the script runs `TLStudioPro.exe --selftest` and fails the build unless `%APPDATA%\QRStudioPro\selftest.txt` says `RESULT: OK`. Then install on a clean VM, launch, export all four formats, uninstall.
- **Signing:** the output is *not* signed. Without an Authenticode certificate SmartScreen shows "Windows protected your PC". To sign, run
  `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /a dist\TLStudioPro\TLStudioPro.exe` before Inno Setup, and sign the setup exe afterwards (add `SignTool=` to the `.iss`).

## macOS

Prerequisites: Python 3.12+ (python.org or Homebrew), Xcode command-line tools.

```bash
scripts/build_macos.sh                          # host architecture
CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)" scripts/build_macos.sh
```
- Output: `dist/TL Studio Pro.app` and `dist/TLStudioPro-<version>-<arch>.dmg` (drag-to-Applications window via `dmgbuild`, `packaging/dmg_settings.py`).
- **Architectures:** build an arm64 DMG on an Apple Silicon Mac and an x86_64 DMG on an Intel Mac (or under Rosetta with an x86_64 Python). A universal2 build
  (`ARCH=universal2`) only works if every wheel (PySide6, Pillow, …) is universal2 – verify with `lipo -archs` before shipping.
- **Signing & notarization (required to distribute outside your own Mac without Gatekeeper warnings):**
  1. Enrol in the Apple Developer Program; create a *Developer ID Application* certificate.
  2. Build with `CODESIGN_IDENTITY` set (hardened runtime + timestamp are applied by the script).
  3. `xcrun notarytool submit dist/TLStudioPro-<ver>-<arch>.dmg --apple-id … --team-id … --password <app-specific> --wait`
  4. `xcrun stapler staple dist/TLStudioPro-<ver>-<arch>.dmg`
  Unsigned builds open via right-click ▸ Open (or System Settings ▸ Privacy & Security ▸ Open Anyway).
  The app needs no special entitlements: it reads/writes only files the user picks in native dialogs, plus its own settings folder.

## Status of this repository's builds (be accurate when releasing)

- Verified in development on Linux: full test suite, `--selftest`, and a PyInstaller build of the same spec that passes `--selftest` and starts the GUI.
- **Not yet run on real Windows or macOS** by the author of this repo snapshot: `build_windows.ps1`, the Inno Setup script, `build_macos.sh`, `dmgbuild`, signing and notarization. Run them natively (or via the workflow) and test the artifacts before distributing.

## Release checklist
1. Bump `VERSION` in `src/version.py`. 2. `pytest` green. 3. Build on each OS. 4. Install/launch/export/uninstall on clean machines. 5. Sign (+ notarize). 6. Scan sample exports with several phones.
