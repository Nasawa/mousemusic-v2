import sys
import threading
import time

import pytest

from mousemusic import engine as engine_mod
from mousemusic.config import DEFAULTS
from mousemusic.engine import Engine, Event, install_exit_handlers
from mousemusic.mapping import Rect
from mousemusic.midi import DeviceBusyError, DeviceLostError, NoDevicesError
from mousemusic.midi.fake import FakeMidiOut

GS = "Microsoft GS Wavetable Synth"
ON, OFF, PC, CC = 0x90, 0x80, 0xC0, 0xB0
TICK = 1 / 125
VIRT = Rect(-1920, -200, 3840, 1280)  # secondary monitor left of and above the primary
PRIMARY = Rect(0, 0, 1920, 1080)


class FakeCursor:
    def __init__(self, pos=(0, 0), virt=VIRT, primary=PRIMARY):
        self.pos, self.virt, self.primary = pos, virt, primary
        self.metric_reads = 0

    def position(self):
        return self.pos

    def virtual_rect(self):
        self.metric_reads += 1
        return self.virt

    def primary_rect(self):
        self.metric_reads += 1
        return self.primary


class FakeTimer:
    def __init__(self):
        self.active = False
        self.calls = []

    def begin(self):
        self.active = True
        self.calls.append("begin")

    def end(self):
        if self.active:
            self.calls.append("end")
        self.active = False


def make(settings=DEFAULTS, devices=(GS,), **fake_kw):
    fake = FakeMidiOut(devices, **fake_kw)
    cur = FakeCursor()
    events = []
    timer = FakeTimer()
    eng = Engine(fake, cur, settings, emit=events.append, timer=timer)
    return eng, fake, cur, events, timer


def kinds(events):
    return [e.kind for e in events]


def notes_on(fake):
    return [m for m in fake.messages if m[0] == ON]


def test_stopped_engine_sends_nothing():
    eng, fake, _cur, events, _ = make()
    for i in range(10):
        eng.step(i * TICK)
    assert fake.messages == [] and not fake.is_open and events == []


def test_start_opens_sends_cc7_and_begins_timer():
    eng, fake, _, events, timer = make()
    eng.post("start")
    eng.step(0.0)
    assert fake.messages[0] == (CC, 7, 102)
    assert kinds(events)[:2] == ["started", "note"]
    assert timer.active


def test_first_note_same_tick_as_cell_change_lt01():
    """LT-01: the note-on for a cell change goes out in the same tick (≤ 8 ms app latency)."""
    eng, fake, cur, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.step(1.0)  # let any rate window pass
    before = len(notes_on(fake))
    cur.pos = (1900, 1000)
    eng.step(1.0 + TICK)
    assert len(notes_on(fake)) == before + 1


def test_note_only_on_cell_change():
    eng, fake, cur, _, _ = make()
    cur.pos = (-1920, -200)
    eng.post("start")
    eng.step(0.0)
    for i in range(1, 50):
        cur.pos = (-1920 + (i % 3), -200)  # jitter inside one cell
        eng.step(i * TICK)
    assert len(notes_on(fake)) == 1


def test_sweep_across_negative_virtual_desktop_monotonic():
    eng, fake, cur, _, _ = make()
    eng.post("start")
    t = 0.0
    for x in range(-1920, 1920, 4):
        cur.pos = (x, 440)
        eng.step(t)
        t += 0.05  # slow sweep: no rate limiting
    played = [m[1] for m in notes_on(fake)]
    assert played == sorted(played)
    assert played[0] == eng.grid.notes[0] and played[-1] == eng.grid.notes[-1]
    assert len(played) == len(eng.grid.notes)


def test_boundary_jitter_hysteresis_dm04():
    eng, fake, cur, _, _ = make()
    eng.post("start")
    col_w = VIRT.w / len(eng.grid.notes)
    boundary = VIRT.x + col_w
    cur.pos = (int(boundary) - 5, 0)
    eng.step(0.0)
    t = 1.0
    for dx in (-1, 0, 1, 0, -1, 1) * 10:
        cur.pos = (int(boundary) + dx, 0)
        eng.step(t)
        t += 0.05
    assert len(notes_on(fake)) == 1
    cur.pos = (int(boundary) + 3, 0)
    eng.step(t)
    assert len(notes_on(fake)) == 2


def test_rate_limited_fast_sweep_latest_wins():
    eng, fake, cur, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    t = 0.0
    for x in range(-1920, 1920, 40):  # fast: several cells per tick
        t += TICK
        cur.pos = (x, 0)
        eng.step(t)
    times_on = len(notes_on(fake))
    assert times_on <= int(t / 0.030) + 2


def test_primary_screen_mode_clamps():
    eng, fake, cur, _, _ = make(DEFAULTS.replace(screen_mode="primary"))
    eng.post("start")
    cur.pos = (-1500, 500)  # on the left monitor → clamped to primary col 0
    eng.step(0.0)
    assert notes_on(fake)[0][1] == eng.grid.notes[0]
    assert eng.rect == PRIMARY


def test_metrics_refresh_every_2s_and_hotplug():
    eng, _fake, cur, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    reads = cur.metric_reads
    eng.step(1.0)
    assert cur.metric_reads == reads
    cur.virt = PRIMARY  # secondary unplugged
    eng.step(2.1)
    assert eng.rect == PRIMARY
    cur.virt = None  # metrics failure: keep last good rect
    eng.post("display_changed")
    eng.step(2.2)
    assert eng.rect == PRIMARY


def test_cursor_unavailable_is_ignored():
    eng, fake, cur, _, _ = make()
    cur.pos = None
    eng.post("start")
    eng.step(0.0)
    assert notes_on(fake) == []


def test_stop_silence_sequence_sn01():
    eng, fake, _cur, events, timer = make()
    eng.post("start")
    eng.step(0.0)
    note = notes_on(fake)[-1][1]
    fake.messages.clear()
    fake.log.clear()
    eng.post("stop")
    eng.step(0.01)
    assert fake.messages == [(OFF, note, 0), (CC, 123, 0)]
    assert fake.log[-2:] == ["reset", "close"]
    assert kinds(events)[-1] == "stopped"
    assert timer.calls == ["begin", "end"]


def test_stop_after_note_off_skips_note_off():
    eng, fake, _, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.step(1.0)  # 250 ms note expired
    fake.messages.clear()
    eng.post("stop")
    eng.step(1.1)
    assert fake.messages == [(CC, 123, 0)]


def test_open_errors_reported_and_stay_stopped():
    eng, _, _, events, _ = make(devices=())
    eng.post("start")
    eng.step(0.0)
    assert isinstance(events[-1].data["error"], NoDevicesError) and not eng.playing
    eng, _fake, _, events, timer = make(open_errors={0: 4})
    eng.post("start")
    eng.step(0.0)
    assert isinstance(events[-1].data["error"], DeviceBusyError) and not timer.active


def test_fallback_device_warning_w1():
    eng, _fake, _, events, _ = make(devices=("Other",))
    eng.post("start")
    eng.step(0.0)
    assert events[0] == Event("warning", {"saved": GS, "device": "Other"})
    assert eng.settings.midi_device == GS  # never written back (UX-Q4)


def test_device_loss_mid_play_stops_with_e4_md09a():
    eng, fake, cur, events, timer = make()
    eng.post("start")
    eng.step(0.0)
    fake.fail_after = len(fake.messages)
    cur.pos = (1900, 1000)
    eng.step(1.0)
    assert not eng.playing and not fake.is_open and not timer.active
    assert isinstance(events[-1].data["error"], DeviceLostError)
    eng.step(1.1)  # no retry loop
    assert kinds(events).count("error") == 1


def test_unexpected_exception_silences_and_reports_sn05():
    eng, fake, cur, events, _ = make()
    eng.post("start")
    eng.step(0.0)

    def boom():
        raise RuntimeError("bug")

    cur.position = boom
    fake.log.clear()
    eng.step(0.1)
    assert not eng.playing and fake.log[-2:] == ["reset", "close"]
    assert isinstance(events[-1].data["error"], RuntimeError)


def test_volume_changes_coalesced_per_tick_a5():
    eng, fake, _, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    fake.messages.clear()
    for v in range(0, 101, 10):
        eng.post("set_volume", v)
    eng.step(0.01)
    assert [m for m in fake.messages if m[:2] == (CC, 7)] == [(CC, 7, 127)]


def test_volume_via_settings_and_while_stopped():
    eng, fake, _, _, _ = make()
    eng.post("set_volume", 50)
    eng.step(0.0)
    assert fake.messages == []  # stopped: nothing sent, applied on open
    eng.post("start")
    eng.step(0.1)
    assert fake.messages[0] == (CC, 7, 64)
    eng.post("set_settings", eng.settings.replace(volume=0))
    eng.step(0.2)
    assert (CC, 7, 0) in fake.messages


def test_settings_change_rebuilds_grid_live():
    eng, fake, _cur, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.post("set_settings", eng.settings.replace(scale="chromatic", legato=True))
    eng.step(1.0)
    assert len(eng.grid.notes) == 61
    assert eng.scheduler.params.legato
    assert len(notes_on(fake)) == 2  # cell recomputed → replays under the new mapping


def test_set_device_while_playing_silences_and_reopens_md12():
    eng, fake, _, _events, _ = make(devices=(GS, "B"))
    eng.post("start")
    eng.step(0.0)
    fake.log.clear()
    eng.post("set_device", "B")
    eng.step(0.1)
    i = fake.log.index("open 1: B")
    assert fake.log[i - 3 : i] == ["msg B0 7B 00", "reset", "close"]  # CC123 → reset → close
    assert fake.opened == 1 and eng.settings.midi_device == "B"


def test_set_device_while_stopped_only_updates():
    eng, fake, _, _, _ = make(devices=(GS, "B"))
    eng.post("set_device", "B")
    eng.step(0.0)
    assert not fake.is_open and eng.settings.midi_device == "B"


def test_suspend_resume_playing_sn09c():
    eng, fake, _, events, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.post("suspend")
    eng.step(0.1)
    assert not fake.is_open and kinds(events)[-1] == "stopped"
    eng.post("resume")
    eng.step(0.2)
    assert eng.playing and fake.is_open


def test_suspend_resume_stopped_stays_closed():
    eng, fake, _, events, _ = make()
    eng.post("suspend")
    eng.post("resume")
    eng.step(0.0)
    assert not fake.is_open and events == []


def test_resume_reopen_failure_is_e4():
    eng, fake, _, events, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.post("suspend")
    eng.step(0.1)
    fake.devices = []
    eng.post("resume")
    eng.step(0.2)
    assert isinstance(events[-1].data["error"], DeviceLostError) and not eng.playing


def test_unknown_command_logged(caplog):
    eng, *_ = make()
    eng.post("dance")
    eng.step(0.0)
    assert "unknown engine command" in caplog.text


def test_start_twice_is_noop():
    eng, _fake, _, events, _ = make()
    eng.post("start")
    eng.post("start")
    eng.step(0.0)
    assert kinds(events).count("started") == 1


def test_rapid_start_stop_no_stuck_notes_sn11():
    eng, fake, cur, _, _ = make()
    t = 0.0
    for i in range(50):
        eng.post("start" if i % 2 == 0 else "stop")
        cur.pos = (-1920 + i * 70, 0)
        eng.step(t)
        t += 0.003
    eng.post("stop")
    eng.step(t)
    assert not fake.is_open
    # every note-on is followed later by note-off or CC123
    last_on = max(i for i, m in enumerate(fake.messages) if m[0] == ON)
    assert any(m == (CC, 123, 0) for m in fake.messages[last_on:])


# --- real thread ------------------------------------------------------------------------


def run_thread(eng):
    t = eng.start_thread()
    return t


def test_thread_quit_silences_sn02():
    eng, fake, _cur, _events, _ = make()
    run_thread(eng)
    eng.post("start")
    time.sleep(0.1)
    assert fake.is_open
    eng.shutdown()
    assert not eng.thread.is_alive()
    assert not fake.is_open and "reset" in fake.log


def test_thread_idle_when_stopped_and_paced_when_playing():
    """CPU proxy: no ticks while stopped; ~poll_hz ticks/s while playing (no busy-spin)."""
    eng, _fake, _cur, _, _ = make()
    if sys.platform == "win32":  # measure with the real 1 ms timer period, as the app does
        from mousemusic.platform.win_timer import TimerPeriod

        eng.timer = TimerPeriod()
    run_thread(eng)
    time.sleep(0.3)
    assert eng.stats.ticks == 0
    eng.post("start")
    time.sleep(1.0)
    ticks = eng.stats.ticks
    eng.shutdown()
    # upper bound = no busy-spin; loose lower bound because hosted runners are noisy
    assert 30 <= ticks <= 1.2 * 125, ticks
    # app-added processing per tick is far below one 8 ms tick
    assert eng.stats.total_tick_s / max(ticks, 1) < 0.002
    print(
        f"\nticks={ticks} mean_tick={eng.stats.total_tick_s / ticks * 1e6:.0f}us "
        f"max_tick={eng.stats.max_tick_s * 1e6:.0f}us "
        f"cpu={eng.stats.cpu_s:.3f}s wall={eng.stats.wall_s:.3f}s "
        f"({100 * eng.stats.cpu_s / eng.stats.wall_s:.2f}%)"
    )


def test_thread_exception_in_loop_still_silences():
    eng, fake, _cur, _, _ = make()
    eng.post("start")
    eng.step(0.0)

    def boom(cmd, value, now):
        raise KeyboardInterrupt

    eng.handle = boom
    eng.post("anything")
    with pytest.raises(KeyboardInterrupt):
        eng.run()
    assert not fake.is_open and "reset" in fake.log


def test_shutdown_without_thread_silences():
    eng, fake, _, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    eng.shutdown()
    assert not fake.is_open


def test_shutdown_timeout_forces_silence(caplog):
    eng, fake, _, _, _ = make()
    eng.post("start")
    eng.step(0.0)
    release = threading.Event()
    eng.thread = threading.Thread(target=release.wait, daemon=True)
    eng.thread.start()
    eng.shutdown(timeout=0.01)
    release.set()
    assert "did not stop" in caplog.text and not fake.is_open


def test_safe_stop_swallows_silence_failure(caplog):
    eng, _fake, _, _, timer = make()
    eng.post("start")
    eng.step(0.0)

    def boom(*a, **k):
        raise OSError("dead")

    eng.output.close = boom
    eng._safe_stop()
    assert not eng.playing and not timer.active and "silence path failed" in caplog.text


def test_fall_behind_does_not_burst(monkeypatch):
    import itertools

    later = (5.0 + i * 0.001 for i in itertools.count())
    times = itertools.chain([0.0, 0.0, 0.0], later)
    eng, _fake, _cur, _, _ = make()
    eng.clock = lambda: next(times)
    eng.post("start")
    steps = []
    orig = eng.step

    def step(now):
        steps.append(now)
        orig(now)
        if len(steps) >= 2:
            eng.quit_requested = True

    eng.step = step
    eng.run()
    assert len(steps) == 2
    assert steps[1] >= 5.0  # resumed from "now", not by replaying ~600 missed ticks


# --- exit handlers ---------------------------------------------------------------------------


def test_install_exit_handlers_atexit_and_signals():
    eng, fake, _, _, _ = make()
    registered, hooked = [], {}
    nums = install_exit_handlers(
        eng, register=registered.append, set_signal=lambda n, h: hooked.__setitem__(n, h)
    )
    assert registered == [eng.shutdown]
    import signal

    assert signal.SIGINT in nums and signal.SIGTERM in nums
    eng.post("start")
    eng.step(0.0)
    with pytest.raises(KeyboardInterrupt):
        hooked[signal.SIGINT](signal.SIGINT, None)
    assert not fake.is_open


def test_signal_handler_custom_callback_and_unhookable():
    eng, _fake, _, _, _ = make()
    called = []
    hooks = {}

    def set_signal(n, h):
        if n == engine_mod.signal.SIGTERM:
            raise ValueError("not main thread")
        hooks[n] = h

    nums = install_exit_handlers(
        eng, register=lambda f: None, set_signal=set_signal, on_signal=lambda: called.append(1)
    )
    assert engine_mod.signal.SIGTERM not in nums
    hooks[engine_mod.signal.SIGINT](2, None)
    assert called == [1]
