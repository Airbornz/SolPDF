# Build this specification separately on each supported operating system.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
is_mac = sys.platform == "darwin"
icon = str(root / "assets" / ("sol.icns" if is_mac else "sol.ico"))
source_data = [(str(root / filename), "source") for filename in
    ("launcher.py", "pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "Sol PDF.spec")]
source_data += [(str(root / "sol_pdf"), "source/sol_pdf"),
    (str(root / "scripts"), "source/scripts"), (str(root / "assets"), "source/assets"),
    (str(root / "licenses"), "licenses")]
a = Analysis([str(root / "launcher.py")], pathex=[str(root)],
    binaries=[], datas=source_data + copy_metadata("PyMuPDF") +
        copy_metadata("PySide6-Essentials") + copy_metadata("shiboken6"),
    hiddenimports=[], hookspath=[], runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork", "tkinter", "pytest"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Sol PDF",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=icon if Path(icon).exists() else None)
collect = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Sol PDF")
if is_mac:
    app = BUNDLE(collect, name="Sol PDF.app", icon=icon if Path(icon).exists() else None,
        bundle_identifier="com.solpdf.desktop",
        info_plist={"CFBundleDisplayName": "Sol PDF", "CFBundleShortVersionString": "0.1.1",
            "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0"})
