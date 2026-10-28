"""Single source of truth for version / identity. Read by the app, PyInstaller spec and build scripts."""
APP_NAME = "QR Studio Pro"
APP_SLUG = "qr-studio-pro"
ORG_NAME = "QR Studio"
APP_ID = "com.qrstudio.qrstudiopro"
VERSION = "1.0.0"
COPYRIGHT = "Copyright (c) 2026 QR Studio"
PROJECT_EXT = ".qrsp"

# ---- In-app updates ------------------------------------------------------------------------------
# HTTPS address of the update feed (update.json, see docs/UPDATES.md). Leave empty to disable update
# checks. It can also be overridden at run time with the QRSP_UPDATE_URL environment variable.
# Example: "https://github.com/<you>/<repo>/releases/latest/download/update.json"
UPDATE_MANIFEST_URL = ""
