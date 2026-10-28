# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for QR Studio Pro (Windows one-folder + optional portable one-file, macOS .app).

Run from the project root through scripts/build_windows.ps1 or scripts/build_macos.sh.
Environment switches:
    QRSP_ONEFILE=1      build a single-file portable .exe instead of a one-folder app (Windows)
    QRSP_TARGET_ARCH=   macOS only: arm64 | x86_64 | universal2 (default: the host architecture;
                        universal2 only works when every dependency wheel is universal2)
"""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from src.version import APP_ID, APP_NAME, COPYRIGHT, VERSION  # noqa: E402

ONEFILE = os.environ.get("QRSP_ONEFILE") == "1"
IS_WIN, IS_MAC = sys.platform == "win32", sys.platform == "darwin"
NAME = "QRStudioPro"

datas = [(str(ROOT / "assets"), "assets")]
hiddenimports = ["PySide6.QtSvg", "reportlab.pdfbase._fontdata", "reportlab.graphics.barcode"]
excludes = [
    "cv2", "numpy", "pytest", "tkinter", "unittest", "matplotlib", "scipy", "pandas",   # dev / unused
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtPdf",
]

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = str(ROOT / "assets" / "icons" / ("app.ico" if IS_WIN else "app.icns"))
version_file = str(ROOT / "packaging" / "version_info.txt") if IS_WIN and (ROOT / "packaging" / "version_info.txt").exists() else None

if ONEFILE:
    # Portable single file. It unpacks to a temp folder at start-up (a second or two slower) and
    # single-file executables are more often flagged by antivirus heuristics than installed builds.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=f"{NAME}-portable", console=False, upx=False,
              icon=icon, version=version_file, runtime_tmpdir=None)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, upx=False,
              icon=icon, version=version_file,
              target_arch=os.environ.get("QRSP_TARGET_ARCH") or None if IS_MAC else None)
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)
    if IS_MAC:
        app = BUNDLE(
            coll,
            name=f"{APP_NAME}.app",
            icon=icon,
            bundle_identifier=APP_ID,
            version=VERSION,
            info_plist={
                "CFBundleName": APP_NAME,
                "CFBundleDisplayName": APP_NAME,
                "CFBundleShortVersionString": VERSION,
                "CFBundleVersion": VERSION,
                "NSHumanReadableCopyright": COPYRIGHT,
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "11.0",
                "LSApplicationCategoryType": "public.app-category.graphics-design",
                "CFBundleDocumentTypes": [{
                    "CFBundleTypeName": "QR Studio Project",
                    "CFBundleTypeExtensions": ["qrsp"],
                    "CFBundleTypeRole": "Editor",
                }],
            },
        )
