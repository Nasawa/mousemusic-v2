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
PKG = ROOT / "src" / "mousemusic"
ICON = PKG / "assets" / "icon.ico"
MANIFEST = ROOT / "packaging" / "mousemusic.manifest"  # DPI awareness (PerMonitorV2)

HIDDEN = []
if sys.platform == "win32":
    HIDDEN.append("pystray._win32")
    # CG-S2: generate the UI Automation wrapper at build time and bundle it, so the exe
    # doesn't depend on comtypes writing generated code to %TEMP% on first run.
    import comtypes.client
    from PyInstaller.utils.hooks import collect_submodules

    comtypes.client.GetModule("UIAutomationCore.dll")
    HIDDEN += collect_submodules("comtypes.gen")

a = Analysis(
    [str(ROOT / "src" / "mousemusic" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    # Package data lives in src/mousemusic/ (so `pip install` ships it); the bundle keeps it at
    # _MEIPASS/data and _MEIPASS/assets, where curation_path() and asset_candidates() look first.
    datas=[(str(PKG / "data"), "data"), (str(PKG / "assets"), "assets")],
    hiddenimports=HIDDEN,
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
