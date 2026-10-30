# QR Studio Pro

Offline desktop app for designing QR codes with a **centre logo**, **custom colours / finder eyes** and a **frame designer**.
Everything runs locally – no server, account, subscription or database. Python 3.12+, PySide6, `qrcode`, Pillow, ReportLab.

| | |
|---|---|
| Content | URL, text, e-mail, phone, SMS, Wi-Fi, vCard, map location, calendar event, WhatsApp, Telegram · error correction L/M/Q/H · quiet zone 1–10 modules · Unicode & Khmer |
| Logo | **Upload Center Logo** (PNG, JPG, SVG, transparent PNG) · aspect ratio preserved · 10–25 % size · square / rounded / circle / no backing + colour · on/off · auto level H |
| Colours | picker + HEX · presets (Classic, Corporate Blue, Emerald, Crimson, Purple, Dark Premium, Custom) · transparent background · optional gradient · contrast warnings |
| Finder eyes | outer / pupil colour and style (square, rounded, circle) independent of the modules |
| Frame Designer | none, rectangle, rounded, card, circle/badge, double line, corporate bar, call-to-action · colours, thickness, radius, padding, margin, dashed · title, company, caption (top/bottom) · font family/size/weight/colour |
| Export | PNG, JPG, SVG, PDF (vector) · native Save dialog · size / dpi · overwrite warning |
| Scan check | live **✓ Scans OK / ⚠ May not scan** badge: the rendered code is decoded by an independent decoder (OpenCV). A pass is not a guarantee – still test with a phone at print size |
| Batch | **File ▸ Batch Generate from CSV…** – one file per row (columns `content`, `filename`, `title`, `caption`, `company`), progress, cancel, `batch-report.csv` |
| Print sheets | **File ▸ Create Print Sheet…** – A4 / Letter PDF with N copies or one code per CSV row, sticker size, margins, cut guides |
| Templates | **Presets ▸ Design Templates…** – 10 ready-made looks with thumbnails (applies as one undo step) |
| Modules | square, rounded, dots, small dots, gapped squares, vertical bars · gradient fill |
| Languages | English and Khmer (**View ▸ Language**); needs a Khmer system font (built into Windows and macOS) |
| Projects | save/load `.qrsp` project JSON · brand presets · recent projects (File ▸ Recent Projects… with thumbnails) · drag & drop (logo, project, CSV) · remembered folders · light/dark theme · undo/redo |

Preview and every export format are drawn from **one shared scene description** (`src/core/scene.py`), so what you see is what you export.

## Run from source

macOS / Linux:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py                 # start the app
python app.py --selftest      # headless check: renders + exports PNG/JPG/SVG/PDF, scans the PNG
QT_QPA_PLATFORM=offscreen python -m pytest      # test suite
```
Windows (PowerShell):
```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python app.py
python -m pytest
```

## Build installers (must be done on the target OS)

| Platform | Command | Output (`dist/`) |
|---|---|---|
| Windows 10/11 | `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 [-Portable]` | `QRStudioPro\` app folder, `QRStudioPro-<ver>-Setup.exe` (Inno Setup 6 required), optional `QRStudioPro-portable.exe` |
| macOS 11+ | `scripts/build_macos.sh` | `QR Studio Pro.app`, `QRStudioPro-<ver>-<arch>.dmg` |

Each script checks Python, creates `.venv-build`, runs the tests, builds with PyInstaller, runs `--selftest` **on the built
app**, then packages. Apple Silicon and Intel DMGs are built separately (`macos-14` / `macos-13` runners in
`.github/workflows/build.yml`). Details, signing and notarization: [docs/PACKAGING.md](docs/PACKAGING.md).

End users do not need Python. The installer is per-user (no administrator rights), adds a Start-menu entry, optional
desktop shortcut and a clean uninstaller; settings in `%APPDATA%\QRStudioPro` are kept on uninstall.

## Using the app

1. **Content** – choose the type and enter the data. Invalid input is explained under the field and in the preview.
2. **Logo** – *Upload Center Logo* (or drop an image on the window). Size, backing shape/colour and padding are live. With a logo the
   code is rendered at level H unless you untick the option. The logo is drawn on top – it is never encoded in the data.
3. **QR Colors / Finder Eyes** – presets or custom HEX; contrast is checked as you type.
4. **Frame Designer** – pick a type, then colours, spacing and text. Text sits outside the code and its quiet zone.
5. **Export** – format, width, dpi; *Export…* opens the native Save dialog. SVG/PDF keep modules and frame as vectors (the logo is an embedded PNG).
6. **File ▸ Save** stores a `.qrsp` project (settings + logo reference, relative and absolute); **Presets ▸ Save Preset** stores only the style for reuse.

Shortcuts: Ctrl/Cmd+B batch · +Shift+T templates · +Shift+L print sheet · +Alt+O recent projects · Ctrl/Cmd+N/O/S new/open/save · +E export · +L logo · +Z/Shift+Z undo/redo · +T theme · +0 fit · +/- zoom.

## Updates

The version is shown in the window title, the status bar and **Help ▸ About**. **Help ▸ Check for Updates…** installs new versions over the old
one – no uninstall needed. This needs a feed address configured once; see [docs/UPDATES.md](docs/UPDATES.md).

## Troubleshooting

- **"Logo not found" on opening a project** – the file moved; the app offers to pick it again. A changed file is reported too.
- **Preview shows an error banner** – the content is invalid (e.g. malformed URL); the last good image is dimmed.
- **Code does not scan** – read the *Scan reliability* card: low contrast, inverted colours, circle eyes, dots, big logos, tiny modules or a small quiet zone all reduce reliability. No QR code is guaranteed to scan everywhere; test with several phones at the real print size.
- **Text in a frame shows a different font** – the chosen font is not installed; a similar one is substituted (a hint appears under the font box). Khmer text uses a Khmer-capable font when one is installed.
- **Logs** – `%APPDATA%\QRStudioPro\logs`, `~/Library/Logs/QR Studio Pro`, or `~/.config/qr-studio-pro/logs` (JSON lines).
- **Windows SmartScreen / macOS Gatekeeper warnings** – expected for unsigned builds; see docs/PACKAGING.md.

## Security & privacy

Local-only processing; URLs are never opened. Logos are validated (type, size, pixel limits, decompression-bomb guard); SVGs with
scripts or external references are refused and are rasterised by Qt, not executed. Exports contain no local paths; files are written
atomically and temp files removed. No secrets, no admin rights.

## Project layout

```
app.py                  entry point (--selftest, --version)
src/core/               qr_generator · logo_composer · frame_renderer (layout → Scene) · render_raster/svg/pdf · export_manager · scan_advisor · scan_check · batch · print_sheet · color_manager · fonts
src/models/             project_settings (serialisable dataclasses, sanitising)
src/services/           project_service · preset_service · templates · app_prefs · history (undo/redo)
src/ui/                 PySide6 window, panels, dialogs (tools_dialogs), theme, icons
src/i18n.py             English / Khmer interface translation
src/utils/              validation · paths · logging
tests/                  pytest (unit, export, UI offscreen) – decodes exports with OpenCV as an independent scanner
packaging/ scripts/ docs/
```
