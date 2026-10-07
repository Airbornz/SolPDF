"""Verify bundled Windows architecture and direct runtime dependencies on any OS."""
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "tmp/windows-portable/Sol PDF"
files = [p for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe")]
available = {p.name.lower() for p in files}
imports = set()
dependencies = {}
for path in files:
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", path
    machine, count = struct.unpack_from("<HH", data, pe + 4)
    assert machine == 0x8664, f"Not x64: {path}"
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    assert struct.unpack_from("<H", data, optional)[0] == 0x20B
    table = optional + optional_size
    sections = []
    for number in range(count):
        header = table + number * 40
        size, rva, raw_size, offset = struct.unpack_from("<IIII", data, header + 8)
        sections.append((rva, max(size, raw_size), offset))
    def location(rva):
        for start, size, offset in sections:
            if start <= rva < start + size:
                return offset + rva - start
        return rva
    import_rva = struct.unpack_from("<I", data, optional + 120)[0]
    if not import_rva:
        continue
    descriptor = location(import_rva)
    direct = set()
    while any(data[descriptor:descriptor + 20]):
        name_rva = struct.unpack_from("<I", data, descriptor + 12)[0]
        name_offset = location(name_rva)
        name = data[name_offset:data.index(b"\0", name_offset)].decode("ascii").lower()
        imports.add(name)
        direct.add(name)
        descriptor += 20
    dependencies[path.name.lower()] = direct
missing = sorted(name for name in imports if name not in available and
    not name.startswith(("api-ms-", "ext-ms-")))
print(f"Verified x64 architecture of {len(files)} Windows binaries.")
roots = [p.name.lower() for p in files if p.name.lower() in
    ("pythonw.exe", "python313.dll", "python3.dll", "qtcore.pyd", "qtgui.pyd",
     "qtwidgets.pyd", "qwindows.dll") or (p.suffix == ".pyd" and "pymupdf" in str(p))
    or (p.suffix == ".pyd" and "shiboken6" in str(p))]
seen = set()
required_missing = set()
while roots:
    name = roots.pop()
    if name in seen:
        continue
    seen.add(name)
    for dependency in dependencies.get(name, set()):
        if dependency in available:
            roots.append(dependency)
        elif not dependency.startswith(("api-ms-", "ext-ms-")):
            required_missing.add(dependency)
system_dlls = {"advapi32.dll", "authz.dll", "bcrypt.dll", "comdlg32.dll", "crypt32.dll",
    "d2d1.dll", "d3d11.dll", "d3d12.dll", "d3d9.dll", "d3dcompiler_47.dll", "dnsapi.dll",
    "dwmapi.dll", "dwrite.dll", "dxgi.dll", "gdi32.dll", "imagehlp.dll", "imm32.dll",
    "iphlpapi.dll", "kernel32.dll", "mpr.dll", "ncrypt.dll", "netapi32.dll", "odbc32.dll",
    "ole32.dll", "oleaut32.dll", "propsys.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll",
    "shell32.dll", "shlwapi.dll", "uiautomationcore.dll", "user32.dll", "userenv.dll",
    "uxtheme.dll", "version.dll", "winhttp.dll", "winmm.dll", "winspool.drv", "ws2_32.dll", "wtsapi32.dll"}
assert required_missing <= system_dlls, f"Required DLLs missing: {required_missing - system_dlls}"
print(f"Checked dependency closure of {len(seen)} binaries needed by the editor.")
print("Required non-system DLLs are present. Runtime testing on Windows is still required.")
