"""Build on the destination OS; no Python installation is needed to run the result."""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(ROOT / "tmp" / "pyinstaller-cache"))
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                "--workpath", str(ROOT / "build"), "Sol PDF.spec"], check=True)
system = platform.system()
if system == "Darwin":
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    "dist/Sol PDF.app", "dist/Sol-PDF-macOS-arm64.zip"], check=True)
elif system == "Windows":
    shutil.make_archive(str(ROOT / "dist/Sol-PDF-Windows-x64"), "zip", ROOT / "dist", "Sol PDF")
else:
    shutil.make_archive(str(ROOT / "dist/Sol-PDF-Linux-x64"), "gztar", ROOT / "dist", "Sol PDF")
