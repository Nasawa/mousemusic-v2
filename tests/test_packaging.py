"""`pip install` ships the runtime assets (icons, curation data) and the lookup finds them.

Regression: assets/ and data/ lived at the repo root, outside the package, so a wheel had
only .py files and an installed copy lost its icons and curation.json.
"""

import importlib.util
import sys
import tomllib
import zipfile
from pathlib import Path

from mousemusic import app, instruments

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "mousemusic"
_spec = importlib.util.spec_from_file_location("cwa", ROOT / "tools" / "check_wheel_assets.py")
cwa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cwa)


def test_package_data_globs_cover_every_asset():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = cfg["tool"]["setuptools"]["package-data"]["mousemusic"]
    covered = {p for g in globs for p in PKG.glob(g) if p.is_file()}
    files = {p for d in cwa.DATA_DIRS for p in (PKG / d).rglob("*") if p.is_file()}
    assert files, "no package data found"
    assert files <= covered, sorted(str(p.relative_to(PKG)) for p in files - covered)


def test_no_assets_left_outside_the_package():
    assert not (ROOT / "assets").exists()
    assert not (ROOT / "data").exists()


def test_lookup_resolves_inside_the_package(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    pkg = Path(app.__file__).resolve().parent
    assert app.assets_dir() == pkg / "assets"
    assert instruments.curation_path() == pkg / "data" / "curation.json"
    assert instruments.curation_path().is_file()


def test_wheel_check_flags_missing_assets(tmp_path):
    whl = tmp_path / "mousemusic-0-py3-none-any.whl"
    expected = sorted(cwa.expected_files())
    with zipfile.ZipFile(whl, "w") as zf:
        for name in expected[1:]:
            zf.writestr(name, b"")
    assert cwa.missing_from_wheel(whl) == expected[:1]
    with zipfile.ZipFile(whl, "a") as zf:
        zf.writestr(expected[0], b"")
    assert cwa.missing_from_wheel(whl) == []
