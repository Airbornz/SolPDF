"""Assemble Windows x64 using official binaries; run on Windows before release."""
import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tmp" / "windows-wheels"
DEST = ROOT / "tmp" / "windows-portable" / "Sol PDF"
VERSION = "3.13.16"
PYTHON_SHA256 = "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"

CACHE.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
    "--platform", "win_amd64", "--python-version", "313", "--implementation", "cp",
    "--abi", "cp313", "--dest", str(CACHE), "PySide6-Essentials==6.8.3",
    "PyMuPDF==1.26.7"], check=True)
archive = CACHE / f"python-{VERSION}-embed-amd64.zip"
if not archive.exists():
    with urllib.request.urlopen(f"https://www.python.org/ftp/python/{VERSION}/{archive.name}", timeout=60) as response:
        archive.write_bytes(response.read())
if hashlib.sha256(archive.read_bytes()).hexdigest() != PYTHON_SHA256:
    raise RuntimeError("Python archive checksum does not match its official release page.")
if DEST.exists():
    shutil.rmtree(DEST)
runtime = DEST / "runtime"
site = runtime / "Lib" / "site-packages"
site.mkdir(parents=True)
with zipfile.ZipFile(archive) as source:
    source.extractall(runtime)
for wheel in CACHE.glob("*.whl"):
    with zipfile.ZipFile(wheel) as source:
        source.extractall(site)
(runtime / "python313._pth").write_text("python313.zip\n.\n../app\nLib/site-packages\nimport site\n")
shutil.copytree(ROOT / "sol_pdf", DEST / "app" / "sol_pdf", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(ROOT / "examples", DEST / "examples")
shutil.copytree(ROOT / "licenses", DEST / "licenses")
shutil.copytree(ROOT / "assets", DEST / "assets")
for filename in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
    shutil.copy2(ROOT / filename, DEST / filename)
(DEST / "launcher.pyw").write_text('''import ctypes
import sys
import traceback
try:
    from sol_pdf.app import main
    raise SystemExit(main())
except Exception:
    ctypes.windll.user32.MessageBoxW(None, traceback.format_exc(), "Sol PDF could not start", 0x10)
''')
(DEST / "Launch Sol PDF.cmd").write_text('@echo off\r\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0launcher.pyw" %*\r\n')
(DEST / "Start here.txt").write_text("Sol PDF for Windows 10/11, 64-bit Intel/AMD\n\n"
    "Extract the entire ZIP. Double-click Launch Sol PDF.cmd.\n"
    "Keep runtime, app, and all other folders together. No Python installation is needed.\n\n"
    "This portable package was assembled on Mac from official Windows binaries.\n"
    "It has not been run on Windows yet. Please test on a Windows PC before relying on it.\n"
    "The GitHub Actions workflow can build and test a conventional standalone EXE.\n")
manifest = "\n".join(f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}"
    for item in [archive, *sorted(CACHE.glob("*.whl"))])
(DEST / "download-checksums.txt").write_text(manifest + "\n")
(ROOT / "dist").mkdir(exist_ok=True)
output = shutil.make_archive(str(ROOT / "dist" / "Sol-PDF-Windows-x64-portable"),
    "zip", DEST.parent, DEST.name)
print(output)
