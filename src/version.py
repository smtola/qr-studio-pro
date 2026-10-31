"""Single source of truth for version / identity. Read by the app, PyInstaller spec and build scripts."""
APP_NAME = "TL Studio Pro"
APP_SLUG = "tl-studio-pro"
ORG_NAME = "TL Studio"
# Folder names of the per-user data (settings, presets, logs). Kept from the old "QR Studio Pro" so upgrades keep
# everything; do not rename.
DATA_DIR_WIN = "QRStudioPro"
DATA_DIR_MAC = "QR Studio Pro"
DATA_DIR_LINUX = "qr-studio-pro"
APP_ID = "com.qrstudio.qrstudiopro"
VERSION = "1.2.0"
COPYRIGHT = "Copyright (c) 2026 TL Studio"
PROJECT_EXT = ".qrsp"

# ---- In-app updates ------------------------------------------------------------------------------
# HTTPS address of the update feed (update.json, see docs/UPDATES.md). Leave empty to disable update
# checks. It can also be overridden at run time with the QRSP_UPDATE_URL environment variable.
# Example: "https://github.com/<you>/<repo>/releases/latest/download/update.json"
UPDATE_MANIFEST_URL = ""
