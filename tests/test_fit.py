from mousemusic.mapping import Rect
from mousemusic.platform.win_a11y import (
    CHILDID_SELF,
    EVENT_OBJECT_NAMECHANGE,
    OBJID_CLIENT,
    Announcer,
)
from mousemusic.ui import fit

M = len  # 1 px per character


def test_fit_height():
    assert fit.fit_height(300, 360, 1000) == 360
    assert fit.fit_height(500, 360, 1000) == 500
    assert fit.fit_height(1500, 360, 1000) == 1000
    assert fit.fit_height(500, 360, 200) == 200  # tiny work area: the cap wins


def test_wrap_and_truncate():
    assert fit.wrap("aa bb cc", 5, M) == ["aa bb", "cc"]
    assert fit.wrap("x\ny", 9, M) == ["x", "y"]
    assert fit.wrap("longword a", 3, M) == ["longword", "a"]
    assert fit.truncate("aa bb", 5, 1, M) == "aa bb"
    assert fit.truncate("aa bb cc dd", 5, 1, M) == "aa b…"
    assert fit.truncate("aa bb cc dd ee", 5, 2, M) == "aa bb\ncc d…"
    assert fit.truncate("aa bb cc", 5, 0, M).endswith("…")


def test_work_area_for():
    a, b = Rect(0, 0, 100, 100), Rect(100, 0, 100, 50)
    assert fit.work_area_for((120, 10), (20, 20), [a, b], a) is b
    assert fit.work_area_for((5000, 0), (20, 20), [a, b], a) is a
    assert fit.work_area_for((5, 5), (5, 5), [], b) is b


def test_home_position():
    area = Rect(0, 0, 400, 500)
    h = fit.HomePosition((10, 300))
    assert h.position((100, 100), [area], area) == (10, 300) and not h.clamped
    assert h.position((100, 400), [area], area) == (10, 100) and h.clamped
    assert not h.user_moved((10, 100))  # our own move
    assert h.position((100, 100), [], area) == (10, 300)  # shrinks: back home
    h.position((100, 400), [area], area)
    assert h.user_moved((50, 20))  # user moved after the clamp: new home, saved
    assert h.home == (50, 20) and not h.clamped
    assert h.position((100, 100), [area], area) == (50, 20)


class U:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def SetWindowTextW(self, hwnd, text):
        if self.fail:
            raise OSError("x")
        self.calls.append(("text", hwnd, text))

    def NotifyWinEvent(self, *a):
        self.calls.append(("event", *a))


def test_announcer_once_per_message():
    u = U()
    a = Announcer(u)
    assert a(5, "Playing")
    assert not a(5, "Playing")  # re-wrap/resize/theme: no repeat
    assert not a(0, "x")
    assert a(5, "Stopped")
    assert u.calls == [
        ("text", 5, "Playing"), ("event", EVENT_OBJECT_NAMECHANGE, 5, OBJID_CLIENT, CHILDID_SELF),
        ("text", 5, "Stopped"), ("event", EVENT_OBJECT_NAMECHANGE, 5, OBJID_CLIENT, CHILDID_SELF),
    ]  # fmt: skip
    assert not Announcer(U(fail=True))(5, "x")
