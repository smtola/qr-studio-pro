"""Write packaging/version_info.txt (Windows file properties) from src/version.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.version import APP_NAME, COPYRIGHT, ORG_NAME, VERSION  # noqa: E402


def main() -> None:
    parts = [int(x) for x in VERSION.split(".")[:3]] + [0] * 4
    v = tuple(parts[:4])
    text = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{ORG_NAME}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'QRStudioPro'),
      StringStruct('LegalCopyright', '{COPYRIGHT}'),
      StringStruct('OriginalFilename', 'QRStudioPro.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    out = ROOT / "packaging" / "version_info.txt"
    out.write_text(text, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
