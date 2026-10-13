"""App icon resolves (source + frozen) and is packaged. Regression: Tk default feather icon."""

import ast
import sys
from pathlib import Path

import pytest

from mousemusic import app
from mousemusic.ui import appicon

ROOT = Path(__file__).resolve().parents[1]


def test_assets_dir_resolves_from_source():
    d = app.assets_dir()
    assert (d / "icon.ico").is_file()
    assert len(appicon.png_paths(d)) == len(appicon.PHOTO_SIZES)
    for state in ("idle", "playing", "error"):
        assert (d / "icons" / f"tray-{state}.ico").is_file()


def test_ico_has_all_frames():
    from PIL import Image

    im = Image.open(app.assets_dir() / "icon.ico")
    assert {16, 32, 48, 256} <= {w for w, _ in im.info["sizes"]}


def test_frozen_meipass_wins(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "icon.ico").write_bytes(b"x")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert appicon.find_assets_dir() == tmp_path / "assets"


def test_missing_assets_falls_back_without_raising(tmp_path):
    assert appicon.find_assets_dir([tmp_path / "a", tmp_path / "b"]) == tmp_path / "b"


def test_pyinstaller_spec_bundles_assets_and_exe_icon():
    src = (ROOT / "mousemusic.spec").read_text()
    tree = ast.parse(src)
    assert 'ICON = ROOT / "assets" / "icon.ico"' in src
    assert "icon=str(ICON)" in src
    datas = [kw.value for n in ast.walk(tree) if isinstance(n, ast.Call)
             for kw in n.keywords if kw.arg == "datas"]  # fmt: skip
    assert datas and "'assets'" in ast.unparse(datas[0]).replace('"', "'")


class FakeRoot:
    def __init__(self):
        self.calls = []

    def iconbitmap(self, *a, **k):
        self.calls.append(("iconbitmap", a, k))

    def iconphoto(self, *a):
        self.calls.append(("iconphoto", a))


def test_apply_icon_windows_sets_default_bitmap(monkeypatch):
    tk = pytest.importorskip("tkinter")

    monkeypatch.setattr(tk, "PhotoImage", lambda master=None, file="": file)
    root = FakeRoot()
    applied = appicon.apply_window_icon(root, app.assets_dir(), windows=True)
    assert applied == ["iconbitmap", "iconphoto"]
    assert root.calls[0][2] == {"default": str(app.assets_dir() / "icon.ico")}
    assert root.calls[1][1][0] is True  # applies to future Toplevels too


def test_apply_icon_falls_back_to_iconphoto_when_bitmap_fails(monkeypatch):
    tk = pytest.importorskip("tkinter")

    monkeypatch.setattr(tk, "PhotoImage", lambda master=None, file="": file)
    root = FakeRoot()
    root.iconbitmap = lambda *a, **k: (_ for _ in ()).throw(tk.TclError("bad"))
    assert appicon.apply_window_icon(root, app.assets_dir(), windows=True) == ["iconphoto"]


def test_apply_icon_real_tk():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        assert "iconphoto" in appicon.apply_window_icon(root, app.assets_dir())
    finally:
        root.destroy()
