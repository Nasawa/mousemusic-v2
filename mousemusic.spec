# PyInstaller spec (ARCHITECTURE.md §7). Build from the repo root:
#   python tools/release.py version-info      # or `stamp vX.Y.Z` in release.yml
#   pyinstaller --noconfirm mousemusic.spec                 -> dist/MouseMusic.exe (onefile)
#   MM_ONEDIR=1 pyinstaller --noconfirm mousemusic.spec     -> dist/MouseMusic/ (portable zip)
# UPX is off on purpose: UPX-packed exes trip far more AV heuristics (§9, SD-07).
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
ONEDIR = os.environ.get("MM_ONEDIR") == "1"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"
ICON = ROOT / "assets" / "icon.ico"
MANIFEST = ROOT / "packaging" / "mousemusic.manifest"  # DPI awareness (PerMonitorV2)

a = Analysis(
    [str(ROOT / "src" / "mousemusic" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "data"), "data"), (str(ROOT / "assets"), "assets")],
    hiddenimports=["pystray._win32"] if sys.platform == "win32" else [],
    excludes=["pytest", "_pytest", "coverage"],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = dict(
    name="MouseMusic",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # --windowed
    icon=str(ICON),
    manifest=str(MANIFEST),
    version=str(VERSION_INFO) if sys.platform == "win32" and VERSION_INFO.is_file() else None,
)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MouseMusic")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
