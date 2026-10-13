"""platform/win_cursor.py and platform/win_timer.py against fake DLLs (runs on any OS)."""

import ctypes

import pytest

from mousemusic.mapping import Rect
from mousemusic.platform import win_cursor, win_timer
from mousemusic.platform.win_cursor import WinCursor, set_dpi_awareness
from mousemusic.platform.win_timer import TimerPeriod


class FakeUser32:
    def __init__(self, metrics=None, pos=(-1500, -100), ok=True, ctx=True, legacy=True):
        self.metrics = metrics or {0: 1920, 1: 1080, 76: -1920, 77: -200, 78: 3840, 79: 1280}
        self.pos, self.ok, self.ctx, self.legacy = pos, ok, ctx, legacy
        self.calls = []

    def GetCursorPos(self, ppt):
        if not self.ok:
            return 0
        ppt._obj.x, ppt._obj.y = self.pos
        return 1

    def GetSystemMetrics(self, i):
        return self.metrics[i]

    def SetProcessDpiAwarenessContext(self, ctx):
        self.calls.append(("ctx", ctx.value))
        return 1 if self.ctx else 0

    def SetProcessDPIAware(self):
        self.calls.append("legacy")
        return 1 if self.legacy else 0


class FakeShcore:
    def __init__(self, hr=0):
        self.hr = hr

    def SetProcessDpiAwareness(self, level):
        assert level == 2
        return self.hr


def test_cursor_negative_coords_and_virtual_rect():
    c = WinCursor(FakeUser32())
    assert c.position() == (-1500, -100)
    assert c.virtual_rect() == Rect(-1920, -200, 3840, 1280)
    assert c.primary_rect() == Rect(0, 0, 1920, 1080)


def test_cursor_failure_returns_none():
    assert WinCursor(FakeUser32(ok=False)).position() is None


def test_zero_size_metrics_ignored(caplog):
    u = FakeUser32(metrics={0: 0, 1: 0, 76: 0, 77: 0, 78: 0, 79: 0})
    c = WinCursor(u)
    assert c.virtual_rect() is None and c.primary_rect() is None
    assert "empty screen rect" in caplog.text


def test_dpi_per_monitor_v2_first():
    u = FakeUser32()
    assert set_dpi_awareness(u) == "per_monitor_v2"
    assert u.calls == [("ctx", ctypes.c_void_p(-4).value)]


@pytest.mark.parametrize(("hr", "expected"), [(0, "per_monitor"), (-2147024891, "already_set")])
def test_dpi_falls_back_to_shcore(hr, expected):
    u = FakeUser32(ctx=False)
    assert set_dpi_awareness(u, lambda: FakeShcore(hr)) == expected


def test_dpi_falls_back_to_system_aware():
    u = FakeUser32(ctx=False)
    del FakeUser32.SetProcessDpiAwarenessContext  # older Windows: function missing
    try:

        def no_shcore():
            raise OSError("no shcore")

        assert set_dpi_awareness(u, no_shcore) == "system"
        assert set_dpi_awareness(FakeUser32(legacy=False), lambda: FakeShcore(1)) == "unaware"
    finally:
        FakeUser32.SetProcessDpiAwarenessContext = _ctx


_ctx = FakeUser32.SetProcessDpiAwarenessContext


def test_dpi_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(win_cursor.sys, "platform", "linux")
    assert set_dpi_awareness() == "unavailable"
    with pytest.raises(OSError):
        win_cursor.load_shcore()


def test_point_struct_is_two_longs():
    from ctypes import wintypes

    assert ctypes.sizeof(wintypes.POINT) == 2 * ctypes.sizeof(wintypes.LONG)


class FakeTimerLib:
    def __init__(self, code=0):
        self.code = code
        self.calls = []

    def timeBeginPeriod(self, ms):
        self.calls.append(("begin", ms))
        return self.code

    def timeEndPeriod(self, ms):
        self.calls.append(("end", ms))
        return 0


def test_timer_period_idempotent():
    lib = FakeTimerLib()
    t = TimerPeriod(lib)
    t.begin()
    t.begin()
    t.end()
    t.end()
    assert lib.calls == [("begin", 1), ("end", 1)]


def test_timer_period_failure_not_active(caplog):
    lib = FakeTimerLib(code=97)
    t = TimerPeriod(lib)
    t.begin()
    t.end()
    assert lib.calls == [("begin", 1)] and "failed" in caplog.text


def test_timer_period_noop_without_lib(monkeypatch):
    monkeypatch.setattr(win_timer.sys, "platform", "linux")
    t = TimerPeriod()
    t.begin()
    t.end()
    assert not t.active
