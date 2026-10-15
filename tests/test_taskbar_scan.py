import sys
import threading

import pytest

from mousemusic import config
from mousemusic.mapping import TRAY, Rect, zone_cell
from mousemusic.taskbar import (
    BASE_INTERVAL_S,
    DEBOUNCE_S,
    MAX_INTERVAL_S,
    SOURCE_FIXED,
    SOURCE_UIA,
    Element,
    Scanner,
    ScanPolicy,
    ScanThread,
    TaskbarInfo,
    TaskbarSnapshot,
    ZoneOptions,
    classify,
    infer_edge,
    ordered,
    zone_for,
)

MON = Rect(0, 0, 1920, 1080)
BAR = Rect(0, 1032, 1920, 48)
SEC_MON = Rect(-2560, 0, 2560, 1440)
SEC_BAR = Rect(-2560, 1368, 2560, 72)


def primary(**kw):
    a = dict(hwnd=1, rect=BAR, edge="bottom", monitor_rect=MON, scale=1.0, primary=True,
             monitor=1, tray=Rect(1700, 1032, 220, 48))  # fmt: skip
    a.update(kw)
    return TaskbarInfo(**a)


def secondary(hwnd=2, x=-2560, monitor=2):
    return TaskbarInfo(hwnd, Rect(x, 1368, 2560, 72), "bottom", Rect(x, 0, 2560, 1440), 1.5,
                       False, monitor)  # fmt: skip


def uia_elements(n=20, w=36, gap=4):
    els = [Element("Taskbar.TaskbarFrameAutomationPeer", "TaskbarFrame", BAR),
           Element("ToggleButton", "StartButton", Rect(0, 1032, 40, 48))]  # fmt: skip
    els += [Element("Taskbar.TaskListButtonAutomationPeer", f"app{i}",
                    Rect(50 + i * (w + gap), 1032, w, 48)) for i in range(n)]  # fmt: skip
    els += [Element("SystemTray.NormalButton", "SystemTrayIcon", Rect(1600 + i * 28, 1032, 28, 48))
            for i in range(8)]  # fmt: skip
    els += [
        Element("SystemTray.OmniButtonLeft", "SystemTrayIcon", Rect(1830, 1032, 80, 48)),
        Element("SystemTray.ShowDesktopButton", "SystemTrayIcon", Rect(1912, 1032, 8, 48)),
        Element("Taskbar.TaskListButtonAutomationPeer", "hidden", None),
        Element("Taskbar.TaskListButtonAutomationPeer", "elsewhere", Rect(0, 0, 40, 40)),
    ]
    return els


def test_infer_edge():
    assert infer_edge(SEC_BAR, SEC_MON) == "bottom"
    assert infer_edge(Rect(-2560, 0, 2560, 72), SEC_MON) == "top"
    assert infer_edge(Rect(-2560, 0, 72, 1440), SEC_MON) == "left"
    assert infer_edge(Rect(-72, 0, 72, 1440), SEC_MON) == "right"
    assert primary(edge="left").axis == "y"


def test_classify_filters_and_tables():
    apps, tray = classify(uia_elements() + uia_elements()[:3], BAR)  # duplicates dropped
    assert len(apps) == 21  # Start + 20 app buttons; frame and hidden/outside ignored
    assert len(tray) == 9  # 8 icons (chevron included) + clock; Show desktop silent
    assert classify([Element("Other", "WidgetsButton", Rect(40, 1032, 40, 48))], BAR)[0]


def test_ordered_primary_then_left_to_right():
    bars = [secondary(3, x=1920, monitor=3), primary(), secondary(2, x=-2560, monitor=2)]
    assert [b.hwnd for b in ordered(bars)] == [1, 2, 3]
    assert [b.hwnd for b in ordered(bars, "primary")] == [1]


def test_zone_for_sources():
    opts = ZoneOptions()
    z, src = zone_for(primary(), 0, uia_elements(), opts)
    assert src == SOURCE_UIA and len(z.app_slots) == 21 and len(z.tray_slots) == 9
    assert zone_cell(1870, 1050, (z,)) == zone_cell(1870, 1050, (z,))
    assert zone_cell(1870, 1050, (z,)).part == TRAY and zone_cell(1870, 1050, (z,)).slot == 0
    z, src = zone_for(primary(), 0, [], opts)  # zero matches → fixed
    assert src == SOURCE_FIXED and z.app_slots[0] == (0, 44)
    z, src = zone_for(primary(), 0, None, ZoneOptions(slot_source="uia"))
    assert z is None and src == "none"
    z, src = zone_for(primary(), 0, uia_elements(), ZoneOptions(slot_source="fixed"))
    assert src == SOURCE_FIXED
    z, _ = zone_for(primary(), 0, uia_elements(), ZoneOptions(tray=False))
    assert z.tray is None and z.tray_slots == ()
    z, _ = zone_for(primary(), 0, None, ZoneOptions(tray=False))
    assert z.tray is None
    z, _ = zone_for(secondary(), 1, None, opts)
    assert z.app_slots[0] == (-2560, -2560 + 66) and z.order == 1 and z.monitor == 2


def test_options_from_settings():
    s = config.DEFAULTS.replace(taskbar_slot_source="fixed", taskbar_monitors="primary",
                                taskbar_tray=False, taskbar_slot_dip=50)  # fmt: skip
    o = ZoneOptions.from_settings(s)
    assert (o.slot_source, o.monitors, o.tray, o.slot_dip, o.tray_slot_dip) == (
        "fixed", "primary", False, 50, 32)  # fmt: skip


def test_policy_backoff_and_recovery():
    p = ScanPolicy()
    assert p.record(0.01) == BASE_INTERVAL_S
    assert p.record(0.2) == 4.0 and p.record(0.2) == 8.0
    for _ in range(5):
        p.record(1.0)
    assert p.interval == MAX_INTERVAL_S
    p.record(0.01)
    p.record(0.01)
    assert p.interval == MAX_INTERVAL_S
    assert p.record(0.01) == BASE_INTERVAL_S  # 3 fast scans


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_scanner_fixed_never_calls_reader_and_auto_uia():
    calls = []
    clk = Clock()
    sc = Scanner(lambda: [primary(), secondary()], lambda h: calls.append(h) or uia_elements(),
                 clk, ZoneOptions(slot_source="fixed"))  # fmt: skip
    snap = sc.scan()
    assert calls == [] and snap.sources == ("fixed", "fixed") and len(snap.zones) == 2
    sc.opts = ZoneOptions()
    snap = sc.scan()
    assert calls == [1, 2] and snap.sources[0] == "uia"
    assert snap.sources[1] == "fixed"  # secondary returned no elements inside its rect
    assert snap.describe()[0].startswith("taskbar 1 (primary): source=uia, 21 app slot(s)")
    assert TaskbarSnapshot().describe() == ["no taskbar zone"]


@pytest.mark.parametrize("n", [1, 2, 4])
def test_scanner_n_taskbars(n):
    bars = [primary()] + [secondary(10 + k, x=1920 + k * 2560, monitor=2 + k) for k in range(n - 1)]
    snap = Scanner(lambda: list(reversed(bars)), None).scan()
    assert [z.order for z in snap.zones] == list(range(n))
    assert [z.monitor for z in snap.zones] == [1] + [2 + k for k in range(n - 1)]


def test_scanner_failures_keep_previous_then_fallback_and_timeout():
    clk = Clock()
    mode = {"v": "ok"}

    def reader(h):
        if mode["v"] == "err":
            raise OSError("UIA_E_ELEMENTNOTAVAILABLE")
        if mode["v"] == "slow":
            clk.t += 1.5
        return uia_elements()

    sc = Scanner(lambda: [primary()], reader, clk)
    good = sc.scan()
    assert good.sources == ("uia",)
    mode["v"] = "err"
    assert sc.scan().zones == good.zones  # 1st failure: previous zone kept
    assert sc.scan().sources == ("fixed",)  # 2nd in a row: fallback
    mode["v"] = "ok"
    assert sc.scan().sources == ("uia",)  # recovers
    mode["v"] = "slow"
    assert sc.scan().zones == good.zones  # timeout counts as a failure
    assert sc.policy.interval == 4.0  # slow scan backed off
    sc.opts = ZoneOptions(slot_source="uia")
    mode["v"] = "err"
    assert sc.scan().zones == ()  # uia only: 2 failures → zone dropped


def test_scanner_geometry_error_and_gone_taskbar():
    state = {"bars": [primary(), secondary()]}

    def geo():
        if state["bars"] is None:
            raise OSError("explorer restarting")
        return state["bars"]

    sc = Scanner(geo, None)
    assert len(sc.scan().zones) == 2
    state["bars"] = None
    assert sc.scan().zones == ()
    assert sc._state == {}


def test_scan_thread_schedule_with_fake_clock():
    clk = Clock()
    snaps = []
    th = ScanThread(Scanner(lambda: [primary()], None, clk), snaps.append)
    assert th.next_wait() is None and not th.step()  # inactive: never scans
    th.refresh()
    assert th.next_wait() is None
    th.activate(True)  # Start: scan now
    assert th.next_wait() == 0 and th.step() and len(snaps) == 1
    assert th.next_wait() == BASE_INTERVAL_S and not th.step()
    clk.t = 2.0
    assert th.step() and len(snaps) == 2
    th.refresh()  # display/setting change: debounced
    assert th.next_wait() == DEBOUNCE_S
    th.refresh()
    clk.t += DEBOUNCE_S
    assert th.step() and len(snaps) == 3
    th.set_options(ZoneOptions(slot_source="fixed"))
    assert th.scanner.opts.slot_source == "fixed"
    th.activate(False)
    assert th.next_wait() is None


def test_scan_thread_real_thread_and_callback_errors():
    done = threading.Event()
    calls = []

    def cb(s):
        calls.append(s)
        done.set()
        raise RuntimeError("engine gone")

    th = ScanThread(Scanner(lambda: [primary()], None), cb, setup=lambda: 1 / 0)
    th.start()
    th.activate(True)
    assert done.wait(2)
    th.stop()
    assert calls and not th._thread.is_alive()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskbar (A-win)")
def test_a_win_real_taskbar():
    from mousemusic.platform import win_taskbar, win_taskbar_uia

    bars = win_taskbar.find_taskbars()
    if not bars:
        pytest.skip("runner session has no taskbar")
    p = next(b for b in bars if b.primary)
    assert p.edge in ("bottom", "top", "left", "right") and 0.5 <= p.scale <= 5
    if p.tray is not None:
        assert p.rect.x <= p.tray.x and p.tray.x + p.tray.w <= p.rect.x + p.rect.w + 1
    reader = win_taskbar_uia.make_reader()
    snap = Scanner(win_taskbar.find_taskbars, reader).scan()
    assert snap.zones and snap.zones[0].order == 0
    print(snap.describe(), "%.1f ms" % (snap.duration_s * 1000))


def test_display_number_and_rect():
    from types import SimpleNamespace as NS

    from mousemusic.platform.win_taskbar import display_number, to_rect
    from mousemusic.platform.win_taskbar_uia import element_rect

    assert display_number("\\\\.\\DISPLAY3") == 3 and display_number("") == 1
    assert to_rect(NS(left=0, top=0, right=10, bottom=5)) == Rect(0, 0, 10, 5)
    assert to_rect(NS(left=0, top=0, right=0, bottom=5)) is None
    assert element_rect(NS(left=-5, top=1, right=5, bottom=2)) == Rect(-5, 1, 10, 1)
    assert element_rect(NS(left=0, top=0, right=0, bottom=0)) is None
