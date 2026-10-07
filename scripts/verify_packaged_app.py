"""Launch the native packaged app and verify its offscreen editing workflow."""
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.platform == "darwin":
    executable = root / "dist/Sol PDF.app/Contents/MacOS/Sol PDF"
elif sys.platform == "win32":
    executable = root / "dist/Sol PDF/Sol PDF.exe"
else:
    executable = root / "dist/Sol PDF/Sol PDF"
output = root / "tmp/packaged-smoke"
output.mkdir(parents=True, exist_ok=True)
result_file = output / "result.json"
result_file.unlink(missing_ok=True)
environment = dict(os.environ, SOL_PDF_SMOKE_OUTPUT=str(output))
subprocess.run([str(executable)], env=environment, check=True, timeout=60)
result = json.loads(result_file.read_text())
if not result.get("success"):
    raise RuntimeError(f"Packaged application checks failed: {result}")
print("Packaged application passed:", ", ".join(result["checks"]))
