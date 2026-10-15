import contextlib
import types

import pytest

from mousemusic.platform import win_theme as wt
from mousemusic.ui import theme as th


@pytest.mark.parametrize(
    ("setting", "light", "hc", "want"),
    [
        ("system", True, False, "light"),
        ("system", False, False, "dark"),
        ("system", None, False, "light"),
        ("light", False, False, "light"),
        ("dark", True, False, "dark"),
        ("dark", None, True, "high_contrast"),
        ("system", False, True, "high_contrast"),
        ("light", True, True, "high_contrast"),
    ],
)
def test_resolve(setting, light, hc, want):
    assert th.resolve(setting, light, hc) == want


def test_palettes_complete_and_roles():
    assert set(th.PALETTES["light"]) == set(th.PALETTES["dark"])
    assert th.PALETTES["light"]["accent_hover"] == th.lighten("#4F46E5", 0.08)
    assert th.lighten("#000000", 1) == "#FFFFFF" and th.lighten("#123456", 0) == "#123456"
    assert th.role_color("dark", "ok") == "#4ADE80"
    assert th.role_color("light", "warn") == "#A14A06"
    assert th.role_color("high_contrast", "error") == "SystemWindowText"


class FakeReg:
    HKEY_CURRENT_USER = 1

    def __init__(self, value=None, fail=False):
        self.value, self.fail = value, fail

    def OpenKey(self, root, path):
        if self.fail:
            raise OSError("missing")
        assert path == wt.PERSONALIZE_KEY
        return contextlib.nullcontext("key")

    def QueryValueEx(self, key, name):
        assert name == "AppsUseLightTheme"
        return self.value, 4


def test_apps_use_light_theme():
    assert wt.apps_use_light_theme(FakeReg(1)) is True
    assert wt.apps_use_light_theme(FakeReg(0)) is False
    assert wt.apps_use_light_theme(FakeReg(fail=True)) is None


class FakeUser32:
    def __init__(self, flags=0, ok=True, parent=42, raise_=False):
        self.flags, self.ok, self.parent, self.raise_ = flags, ok, parent, raise_
        self.swp = []

    def SystemParametersInfoW(self, spi, size, ref, _):
        if self.raise_:
            raise OSError("boom")
        assert spi == wt.SPI_GETHIGHCONTRAST
        ref._obj.dwFlags = self.flags
        return self.ok

    def SetWindowPos(self, *args):
        self.swp.append(args)

    def GetParent(self, child):
        if self.raise_:
            raise OSError("boom")
        return self.parent


def test_high_contrast_on():
    assert wt.high_contrast_on(FakeUser32(flags=wt.HCF_HIGHCONTRASTON)) is True
    assert wt.high_contrast_on(FakeUser32(flags=0)) is False
    assert wt.high_contrast_on(FakeUser32(flags=1, ok=False)) is False
    assert wt.high_contrast_on(FakeUser32(raise_=True)) is False


class FakeDwm:
    def __init__(self, results):
        self.results, self.calls = dict(results), []

    def DwmSetWindowAttribute(self, hwnd, attr, ref, size):
        self.calls.append((hwnd, attr, ref._obj.value, size))
        return self.results.get(attr, -2147024809)  # E_INVALIDARG


def test_dark_title_bar_attr_20_then_19():
    u, d = FakeUser32(), FakeDwm({20: 0})
    assert wt.set_dark_title_bar(7, True, d, u) is True
    assert d.calls == [(7, 20, 1, 4)] and u.swp[0][-1] & wt.SWP_FRAMECHANGED
    d = FakeDwm({19: 0})
    assert wt.set_dark_title_bar(7, False, d, u) is True
    assert [c[1] for c in d.calls] == [20, 19] and d.calls[-1][2] == 0
    u2 = FakeUser32()
    assert wt.set_dark_title_bar(7, True, FakeDwm({}), u2) is False and u2.swp == []
    broken = types.SimpleNamespace(DwmSetWindowAttribute=None)
    assert wt.set_dark_title_bar(7, True, broken, u2) is False


def test_frame_hwnd_and_probe():
    root = types.SimpleNamespace(winfo_id=lambda: 5)
    assert wt.frame_hwnd(root, FakeUser32(parent=99)) == 99
    assert wt.frame_hwnd(root, FakeUser32(parent=0)) is None
    assert wt.frame_hwnd(root, FakeUser32(raise_=True)) is None
    if __import__("sys").platform != "win32":
        assert wt.probe() == (None, False)
