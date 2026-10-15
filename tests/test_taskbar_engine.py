"""CG-S3: taskbar zones in the engine, scheduler velocity, controller wiring, status text."""

from mousemusic import engine as eng
from mousemusic.config import DEFAULTS
from mousemusic.engine import Event
from mousemusic.mapping import APPS, TRAY, Rect, ZoneCell, zone_fixed
from mousemusic.platform.hotkey import SPI_SETWORKAREA, WM_SETTINGCHANGE, translate_message
from mousemusic.taskbar import TaskbarSnapshot
from mousemusic.ui import strings
from mousemusic.ui.status import StatusModel
from test_controller import GS as CGS
from test_controller import make as make_ctl
from test_engine import CC, OFF, ON, PC, TICK, make

# VIRT in test_engine is Rect(-1920, -200, 3840, 1280); put the primary bar at the bottom.
BAR = Rect(0, 1032, 1920, 48)
TRAY_RECT = Rect(1700, 1032, 220, 48)
ZONE = zone_fixed(BAR, 1.0, slot_dip=44, offset_dip=44, tray=TRAY_RECT, tray_slot_dip=32)
SEC = zone_fixed(Rect(-1920, 1008, 1920, 72), 1.5, slot_dip=44, order=1, monitor=2)
SNAP = TaskbarSnapshot((ZONE, SEC), ("fixed", "fixed"))


def started(settings):
    e, fake, cur, events, _ = make(settings)
    e.post("start")
    e.post(eng.TASKBAR, SNAP)
    cur.pos = (500, 500)
    e.step(0.0)
    return e, fake, cur, events


def at(e, cur, pos, t):
    cur.pos = pos
    e.step(t)


def test_zone_program_change_before_note_on_and_restore_on_leave():
    e, fake, cur, events = started(DEFAULTS.replace(taskbar_mode=True))
    desk_prog = [m for m in fake.messages if m[0] == PC][-1][1]
    fake.messages.clear()
    at(e, cur, (44 + 44 * 2 + 10, 1050), 1.0)  # app slot 2
    pc = fake.messages.index((PC, 13, 0))
    on = next(i for i, m in enumerate(fake.messages) if m[0] == ON)
    assert pc < on  # instrument before the note
    notes = e.taskbar_sound.notes
    assert fake.messages[on] == (ON, notes[2], DEFAULTS.velocity)
    ev = events[-1]
    assert ev.data["zone"] == ZoneCell(0, 1, APPS, 2) and ev.data["program"] == 13
    fake.messages.clear()
    at(e, cur, (500, 500), 2.0)  # back on the desktop: the row's program before its note
    msgs = [m for m in fake.messages if m[0] in (PC, ON)]
    assert msgs[0] == (PC, desk_prog, 0) and msgs[1][0] == ON


def test_silent_offset_secondary_program_tray_and_wrap_velocity():
    e, fake, cur, events = started(DEFAULTS.replace(taskbar_mode=True, taskbar_high_note=60,
                                                    taskbar_low_note=48))  # fmt: skip
    n0 = len([m for m in fake.messages if m[0] == ON])
    at(e, cur, (10, 1050), 1.0)  # offset: silent cell
    assert len([m for m in fake.messages if m[0] == ON]) == n0
    assert events[-1].data == {"note": None, "program": None, "zone": ZoneCell(0, 1, APPS, -1)}
    at(e, cur, (-1920 + 66 * 3 + 5, 1040), 2.0)  # secondary, slot 3 → Celesta
    assert (PC, 8, 0) in fake.messages and events[-1].data["zone"].order == 1
    at(e, cur, (1919, 1050), 3.0)  # tray slot 0 = high note
    assert events[-1].data["note"] == 60 and events[-1].data["zone"].part == TRAY
    n = len(e.taskbar_sound.notes)  # pentatonic C3..C4 = 6 notes
    at(e, cur, (44 + 44 * n + 10, 1050), 4.0)  # past the range: wraps, softer
    on = [m for m in fake.messages if m[0] == ON][-1]
    assert on == (ON, 48, round(DEFAULTS.velocity * 0.7))


def test_mode_off_ignores_zones_and_toggles_live():
    e, _fake, cur, events = started(DEFAULTS)
    at(e, cur, (200, 1050), 1.0)
    assert "zone" not in events[-1].data
    e.post("set_settings", e.settings.replace(taskbar_mode=True))
    at(e, cur, (200, 1051), 2.0)
    assert events[-1].data["zone"].part == APPS
    e.post("set_settings", e.settings.replace(taskbar_program=20))
    at(e, cur, (250, 1051), 3.0)
    assert events[-1].data["program"] == 20
    e.post(eng.TASKBAR, TaskbarSnapshot())  # Explorer restart: no zones → desktop mapping
    at(e, cur, (250, 1050), 4.0)
    assert "zone" not in events[-1].data


def test_taskbar_snapshot_before_start_is_kept():
    e, _fake, cur, events, _ = make(DEFAULTS.replace(taskbar_mode=True))
    e.post(eng.TASKBAR, SNAP)
    e.step(0.0)
    e.post("start")
    cur.pos = (200, 1050)
    e.step(TICK)
    assert events[-1].data["zone"].part == APPS


def test_slow_sweep_20_slots_ascending_and_jitter():
    zone = zone_fixed(Rect(0, 1032, 20 * 44, 48), 1.0, slot_dip=44)
    e, fake, cur, _, _ = make(DEFAULTS.replace(taskbar_mode=True, taskbar_low_note=36))
    e.post("start")
    e.post(eng.TASKBAR, TaskbarSnapshot((zone,), ("uia",)))
    t = 0.0
    for x in range(0, 20 * 44, 4):  # slow: 4 px per tick
        cur.pos = (x, 1050)
        e.step(t)
        t += TICK * 10
    ons = [m[1] for m in fake.messages if m[0] == ON]
    assert len(ons) == 20 and ons == sorted(ons)
    cur.pos = (44 * 5 - 5, 1050)  # settle in slot 4 next to its edge
    e.step(t)
    t += 1.0
    before = len(fake.messages)
    for dx in (1, -1, 1, -1):  # ±1 px at a slot edge
        cur.pos = (44 * 5 + dx, 1050)
        e.step(t)
        t += TICK
    assert not [m for m in fake.messages[before:] if m[0] == ON]


# --- controller / status / messages -----------------------------------------------------


class FakeScan:
    def __init__(self):
        self.active, self.refreshes = [], 0

    def activate(self, on):
        self.active.append(on)

    def refresh(self):
        self.refreshes += 1


def test_controller_activates_scan_only_while_playing_with_mode_on():
    scan = FakeScan()
    ctl, e, *_ = make_ctl(taskbar_scan=scan)
    ctl.startup()
    ctl.set_taskbar_mode(True)
    assert scan.active[-1] is False and ctl.settings.taskbar_mode
    assert e.posted[-1][0] == "set_settings"
    ctl.handle_event(Event("started", {"device": CGS}))
    assert scan.active[-1] is True
    ctl.set_taskbar_mode(False)
    assert scan.active[-1] is False
    ctl.set_taskbar_mode(True)
    ctl.handle_event(Event("stopped"))
    assert scan.active[-1] is False
    ctl.dispatch(("taskbar_changed", None))
    ctl.dispatch(("display_changed", None))
    assert scan.refreshes == 2
    ctl2, *_ = make_ctl()
    ctl2.set_taskbar_mode(True)
    ctl2.dispatch(("taskbar_changed", None))
    ctl2.dispatch(("display_changed", None))


def test_zone_status_text():
    s = StatusModel(hotkey="Ctrl+Alt+M", hotkey_ok=True, first_run=False, root="C")
    s.on_started(CGS)
    s.on_note(64, 13, ZoneCell(0, 1, APPS, 6))
    assert s.current(0).text == "E4 · Taskbar 7 · Xylophone"
    s.on_note(64, 8, ZoneCell(1, 2, APPS, 6))
    assert s.current(0).text == "E4 · Taskbar 2/7 · Celesta"
    s.on_note(96, 13, ZoneCell(0, 1, TRAY, 0))
    assert s.current(0).text == "C7 · Tray 1 · Xylophone"
    s.on_note(None, None, ZoneCell(0, 1, APPS, -1))
    assert s.current(0).text == strings.STATUS_TASKBAR_SILENT
    s.on_note(64, 13)
    assert CGS[:10] in s.current(0).text  # back on the desktop: device returns


def test_translate_taskbar_messages():
    assert translate_message(WM_SETTINGCHANGE, SPI_SETWORKAREA) == "taskbar_changed"
    assert translate_message(WM_SETTINGCHANGE, 0, None, "TraySettings") == "taskbar_changed"
    assert translate_message(0xC123, 0, None, None, 0xC123) == "taskbar_changed"
    assert translate_message(0xC124, 0, None, None, 0xC123) is None


def test_scheduler_velocity_override():
    from mousemusic.scheduler import NoteParams, Scheduler

    class Out:
        def __init__(self):
            self.sent = []

        def send(self, *m):
            self.sent.append(m)

        def silence(self, n=None):
            pass

    o = Out()
    s = Scheduler(o, NoteParams(velocity=100))
    s.request(60, 1, 0.0, 70)
    s.request(62, 1, 1.0)
    assert (ON, 60, 70) in o.sent and (ON, 62, 100) in o.sent
    assert (OFF, 60, 0) in o.sent and CC not in [m[0] for m in o.sent]
