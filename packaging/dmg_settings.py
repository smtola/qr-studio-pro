"""dmgbuild settings: drag-and-drop installer window.

    dmgbuild -s packaging/dmg_settings.py -D app="dist/QR Studio Pro.app" "QR Studio Pro" dist/QRStudioPro-1.1.0-<arch>.dmg
"""
import os

app_path = defines.get("app", "dist/QR Studio Pro.app")  # noqa: F821 - `defines` is injected by dmgbuild
app_name = os.path.basename(app_path)

format = "UDZO"
size = None
files = [app_path]
symlinks = {"Applications": "/Applications"}
icon = "assets/icons/app.icns"
icon_locations = {app_name: (160, 180), "Applications": (480, 180)}
background = "builtin-arrow"
window_rect = ((200, 200), (640, 380))
icon_size = 112
text_size = 13
