"""Verify a built wheel ships every runtime asset and the installed app finds them (CI).

python -m pip wheel --no-deps -w wheelhouse .
python tools/check_wheel_assets.py wheelhouse/mousemusic-*.whl

1. Every file under src/mousemusic/assets/ and src/mousemusic/data/ is in the wheel.
2. In a fresh venv (no checkout on sys.path), ``pip install --no-deps <wheel>``, then the
   asset lookup (``app.assets_dir()``, ``instruments.curation_path()``) must resolve inside
   site-packages and find every icon the app opens. Headless: no Tk window, no tray.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "mousemusic"
DATA_DIRS = ("assets", "data")

# Runs inside the fresh venv. Imports only the lookup code (no pystray/Pillow needed).
PROBE = r"""
import sys, sysconfig
from pathlib import Path
from mousemusic import app, instruments
from mousemusic.ui import appicon, tray

site = Path(sysconfig.get_paths()["purelib"]).resolve()
assets = app.assets_dir().resolve()
curation = instruments.curation_path().resolve()
print("assets:", assets)
print("curation:", curation)
assert assets.is_relative_to(site), f"assets resolved outside site-packages: {assets}"
assert curation.is_relative_to(site), f"curation resolved outside site-packages: {curation}"
assert curation.is_file(), f"missing {curation}"
assert (assets / "icon.ico").is_file(), "missing icon.ico"
assert len(appicon.png_paths(assets)) == len(appicon.PHOTO_SIZES), "missing app-*.png"
for state, p in tray.icon_paths(assets / "icons").items():
    assert p.is_file(), f"missing tray icon for {state}: {p}"
sets, default = instruments.load_instrument_sets()
assert default in sets
print("installed asset lookup OK")
"""


def expected_files(pkg: Path = PKG) -> set[str]:
    """Wheel paths (``mousemusic/assets/...``) for every file under the package data dirs."""
    return {
        f"mousemusic/{p.relative_to(pkg).as_posix()}"
        for d in DATA_DIRS
        for p in (pkg / d).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def missing_from_wheel(wheel: Path, pkg: Path = PKG) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    return sorted(expected_files(pkg) - names)


def probe_install(wheel: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="mm-wheel-") as tmp:
        env_dir = Path(tmp) / "venv"
        venv.create(env_dir, with_pip=True)
        py = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        pip = [str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-deps"]
        pip.append(str(wheel.resolve()))
        subprocess.run(pip, check=True, cwd=tmp)
        # cwd=tmp and -I: the checkout's src/ can't leak onto sys.path.
        return subprocess.run([str(py), "-I", "-c", PROBE], cwd=tmp).returncode


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    wheel = Path(argv[0])
    gaps = missing_from_wheel(wheel)
    if gaps:
        print(f"{wheel.name} is missing {len(gaps)} asset(s):", file=sys.stderr)
        for g in gaps:
            print(f"  {g}", file=sys.stderr)
        return 1
    print(f"{wheel.name}: all {len(expected_files())} asset files present", flush=True)
    return probe_install(wheel)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
