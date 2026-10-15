import pytest

from mousemusic import engine as eng
from mousemusic.config import DEFAULTS, LoadResult
from mousemusic.engine import Event
from mousemusic.midi import (
    DeviceBusyError,
    DeviceLostError,
    DeviceOpenError,
    NoDevicesError,
)
from mousemusic.ui import strings
from mousemusic.ui.controller import AppController

GS = "Microsoft GS Wavetable Synth"


class FakeEngine:
    def __init__(self):
        self.posted = []
        self.shut = 0

    def post(self, cmd, value=None):
        self.posted.append((cmd, value))

    def shutdown(self, timeout=1.0):
        self.shut += 1


class FakeSaver:
    def __init__(self):
        self.saved = []
        self.flushed = 0

    def request(self, s):
        self.saved.append(s)

    def flush(self):
        self.flushed += 1
        return True


class FakeView:
    def __init__(self):
        self.calls = []

    def refresh(self):
        self.calls.append("refresh")

    def show_window(self):
        self.calls.append("show")

    def hide_window(self):
        self.calls.append("hide")

    def notify(self, title, text):
        self.calls.append(("notify", title, text))

    def quit_app(self):
        self.calls.append("quit")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(settings=DEFAULTS, devices=(GS,), **kw):
    e, s, v, c = FakeEngine(), FakeSaver(), FakeView(), Clock()
    dev = list(devices)
    ctl = AppController(settings, e, s, lambda: dev, c, **kw)
    ctl.view = v
    return ctl, e, s, v, c, dev


def text(ctl):
    return ctl.status.current(ctl.clock()).text


def test_startup_normal_first_run():
    ctl, *_ = make()
    ctl.startup(LoadResult(DEFAULTS))
    assert text(ctl) == strings.STATUS_FIRST_RUN
    assert ctl.selected_device == GS and ctl.can_start


def test_startup_not_first_run():
    ctl, *_ = make(DEFAULTS.replace(first_run_done=True))
    ctl.startup()
    assert text(ctl) == "Stopped — press Start or Ctrl+Alt+M"


def test_startup_e1_no_devices_start_disabled():
    ctl, e, *_ = make(devices=())
    ctl.startup()
    st = ctl.status.current(0)
    assert st.text == strings.E1_NO_DEVICE and st.help_anchor == "no-midi-device"
    assert not ctl.can_start
    assert [o.label for o in ctl.device_options()] == ["No MIDI output found"]
    ctl.toggle()
    assert e.posted == []


def test_e1_clears_when_device_appears():
    ctl, _e, _s, _v, _c, dev = make(devices=())
    ctl.startup()
    dev.append(GS)
    ctl.refresh_devices()
    assert ctl.can_start and ctl.status.error is None


def test_enumeration_failure_is_e1(caplog):
    ctl, *_ = make()

    def boom():
        raise OSError("x")

    ctl._list_devices = boom
    ctl.refresh_devices()
    assert ctl.status.error.id == "E1"


def test_startup_w1_fallback_never_written():
    ctl, _e, s, *_ = make(devices=("Other",))
    ctl.startup()
    assert text(ctl) == '"Microsoft GS Wavetable Synth" not found. Using Other instead.'
    assert ctl.selected_device == "Other" and s.saved == []


def test_startup_w2_w3_w4():
    ctl, *_ = make(hotkey_ok=False)
    ctl.startup(LoadResult(DEFAULTS, existed=True, corrupt=True))
    assert text(ctl) == strings.W2_SETTINGS_RESET
    assert ctl.status.current(0).help_anchor == "settings-reset"
    ctl2, *_ = make(hotkey_ok=False)
    ctl2.startup(LoadResult(DEFAULTS, existed=True, issues=("x",)))
    assert text(ctl2) == strings.W3_SETTINGS_CLAMPED
    ctl2.status.clear_warning("W3")
    assert text(ctl2) == (
        "Ctrl+Alt+M and Ctrl+Alt+Shift+M are in use by other apps, so the shortcut is off. "
        "Use the Start button."
    )


def test_startup_w4_single_when_fallback_is_configured():
    ctl, *_ = make(DEFAULTS.replace(hotkey="Ctrl+Alt+Shift+M"), hotkey_ok=False)
    ctl.startup()
    assert text(ctl) == (
        "Ctrl+Alt+Shift+M is in use by another app, so the shortcut is off. Use the Start button."
    )


def test_startup_fallback_active_shows_w6_and_active_shortcut():
    ctl, *_ = make(DEFAULTS.replace(first_run_done=True), hotkey_active="Ctrl+Alt+Shift+M")
    ctl.startup()
    assert (
        text(ctl)
        == "Ctrl+Alt+M is in use by another app, so the shortcut is Ctrl+Alt+Shift+M instead."
    )
    assert ctl.status.hotkey_hint() == "Ctrl+Alt+Shift+M"
    assert ctl.status.tray_tooltip("1") == "MouseMusic v1 — Stopped · Ctrl+Alt+Shift+M"
    ctl.status.clear_warning("W7")
    assert text(ctl) == "Stopped — press Start or Ctrl+Alt+Shift+M"


def test_hotkey_off_no_warning():
    ctl, *_ = make(DEFAULTS.replace(hotkey="Off", first_run_done=True))
    ctl.startup()
    assert text(ctl) == "Stopped — press Start"
    assert ctl.status.hotkey_hint() == strings.SHORTCUT_OFF


def test_set_hotkey_live_reregisters_and_handles_result():
    reg = []
    ctl, _e, s, _v, *_ = make(DEFAULTS.replace(first_run_done=True), hotkey_registrar=reg.append)
    ctl.startup()
    assert [o.value for o in ctl.hotkey_options()][-1] == "Off"
    ctl.set_hotkey("Ctrl+Alt+P")
    assert reg == ["Ctrl+Alt+P"] and s.saved[-1].hotkey == "Ctrl+Alt+P"
    ctl.set_hotkey("Ctrl+Alt+P")  # unchanged -> no re-register
    ctl.set_hotkey("Banana")  # invalid -> ignored
    assert reg == ["Ctrl+Alt+P"]
    ctl.dispatch(("hotkey", "Ctrl+Alt+Shift+M"))
    assert "so the shortcut is Ctrl+Alt+Shift+M instead" in text(ctl)
    ctl.dispatch(("hotkey", "Ctrl+Alt+P"))
    assert text(ctl) == "Stopped — press Start or Ctrl+Alt+P"
    ctl.dispatch(("hotkey", None))
    assert "Ctrl+Alt+P and Ctrl+Alt+Shift+M are in use" in text(ctl)
    ctl.set_hotkey("off")
    ctl.dispatch(("hotkey", None))
    assert text(ctl) == "Stopped — press Start"


def test_set_hotkey_without_registrar_and_custom_option():
    ctl, *_ = make(DEFAULTS.replace(hotkey="Win+F9", first_run_done=True))
    assert ctl.hotkey_options()[0].value == "Win+F9"
    ctl.set_hotkey("Ctrl+Alt+P")
    assert not ctl.status.hotkey_ok


def test_start_on_launch():
    ctl, e, *_ = make(DEFAULTS.replace(start_on_launch=True))
    ctl.startup()
    assert e.posted == [(eng.START, None)]


def test_toggle_start_label_flips_only_on_events():
    ctl, e, s, _v, _c, _ = make()
    ctl.startup()
    ctl.toggle()
    assert e.posted == [(eng.START, None)]
    assert not ctl.status.playing and text(ctl) == "Connecting to Microsoft GS Wavetable Synth…"
    ctl.handle_event(Event("started", {"device": GS, "fallback": False}))
    assert ctl.status.playing
    assert s.saved[-1].first_run_done is True
    ctl.handle_event(Event("note", {"note": 64, "program": 11}))
    assert text(ctl) == "E4 · Vibraphone · Microsoft GS Wavetable…"
    ctl.toggle()
    assert e.posted[-1] == (eng.STOP, None)
    ctl.handle_event(Event("stopped"))
    assert not ctl.status.playing


def test_toggle_while_connecting_stops():
    ctl, e, *_ = make()
    ctl.startup()
    ctl.toggle()
    ctl.toggle()
    assert e.posted[-1] == (eng.STOP, None)


def test_engine_warning_w1_then_started_fallback():
    ctl, *_ = make(devices=("Other",))
    ctl.startup()
    ctl.toggle()
    assert not ctl.status.has_warning("W1")
    ctl.handle_event(Event("warning", {"saved": GS, "device": "Other"}))
    ctl.handle_event(Event("started", {"device": "Other", "fallback": True}))
    assert ctl.status.has_warning("W1")
    assert ctl.settings.midi_device == GS


@pytest.mark.parametrize(
    ("exc", "eid", "anchor"),
    [
        (DeviceBusyError("x", device=GS), "E2", "device-busy"),
        (DeviceOpenError("x", device=GS), "E3", "no-sound"),
        (DeviceLostError("x", device=GS), "E4", None),
        (RuntimeError("x"), "E5", None),
        (NoDevicesError("x"), "E1", "no-midi-device"),
    ],
)
def test_error_events(exc, eid, anchor):
    ctl, *_ = make()
    ctl.startup()
    ctl.toggle()
    ctl.handle_event(Event("error", {"error": exc}))
    assert ctl.status.error.id == eid and ctl.status.current(0).help_anchor == anchor
    assert not ctl.status.playing and not ctl.status.connecting
    assert ctl.status.tray_icon() == "error"


def test_device_lost_balloon_only_when_hidden():
    ctl, _e, _s, v, _c, _ = make()
    ctl.startup()
    ctl.handle_event(Event("error", {"error": DeviceLostError("x", device=GS)}))
    assert not any(isinstance(x, tuple) for x in v.calls)
    ctl.hidden = True
    ctl.handle_event(Event("error", {"error": DeviceLostError("x", device=GS)}))
    assert ("notify", "MouseMusic stopped",
            f"Lost connection to {GS}. Open MouseMusic from the tray icon.") in v.calls  # fmt: skip


def test_pick_device_writes_and_clears():
    ctl, e, s, _v, _c, _dev = make(devices=("Other", GS, "B"))
    ctl.startup()
    ctl.status.set_error("E2", "busy")
    ctl.pick_device("B")
    assert s.saved[-1].midi_device == "B" and e.posted[-1] == (eng.SET_DEVICE, "B")
    assert ctl.status.error is None
    ctl.pick_device("nope")
    assert e.posted[-1] == (eng.SET_DEVICE, "B")
    ctl.handle_event(Event("started", {"device": "B", "fallback": False}))
    ctl.pick_device(GS)
    assert ctl.status.connecting


def test_reconnect():
    ctl, e, *_ = make()
    ctl.startup()
    ctl.reconnect()
    assert e.posted == []
    ctl.handle_event(Event("started", {"device": GS}))
    ctl.reconnect()
    assert e.posted[-1] == (eng.RECONNECT, None) and text(ctl) == "Reconnecting…"


def test_scale_key_and_disabled_key():
    ctl, e, s, *_ = make()
    assert [o.label for o in ctl.scale_options()][:2] == ["Pentatonic major", "Pentatonic minor"]
    assert ctl.key_enabled
    ctl.set_scale("chromatic")
    assert not ctl.key_enabled and e.posted[-1][0] == eng.SET_SETTINGS
    assert [o.label for o in ctl.key_options()][3] == "E♭"
    ctl.set_root("D#")
    assert s.saved[-1].root == "D#" and ctl.status.root == "D#"


def test_range_options_and_rules():
    ctl, *_ = make()
    assert [o.label for o in ctl.range_options(36)] == [f"C{i}" for i in range(9)]
    assert "G2" in [o.label for o in ctl.range_options(43)]
    ctl.set_low(96)  # ≥ high → high moves up
    assert (ctl.settings.low_note, ctl.settings.high_note) == (96, 108)
    ctl.set_high(36)  # ≤ low → low moves down
    assert (ctl.settings.low_note, ctl.settings.high_note) == (24, 36)
    ctl.set_low(120)
    assert (ctl.settings.low_note, ctl.settings.high_note) == (115, 127)
    ctl.set_high(0)
    assert (ctl.settings.low_note, ctl.settings.high_note) == (0, 12)
    ctl.set_low(0)
    ctl.set_high(60)
    assert (ctl.settings.low_note, ctl.settings.high_note) == (0, 60)


def test_instruments():
    ctl, *_ = make()
    labels = [o.label for o in ctl.instrument_options()]
    assert labels == ["Classic (8)", "Mellow (6)", "Percussive (7)", "Piano only (1)",
                      "Full GM library (128)"]  # fmt: skip
    assert ctl.instrument_tooltip().startswith("Top of the screen to bottom: Acoustic Grand Piano")
    assert ctl.instrument_tooltip("nope") == "Top of the screen to bottom: "
    ctl.set_instrument_set("mellow")
    assert ctl.settings.instrument_set == "mellow"


def test_volume_note_length_legato():
    ctl, e, s, *_ = make()
    ctl.set_volume(80.4)
    assert e.posted == []
    ctl.set_volume(55.6)
    assert e.posted[-1] == (eng.SET_VOLUME, 56) and s.saved[-1].volume == 56
    ctl.set_note_length(254)
    assert ctl.settings.note_length_ms == 250 and len(s.saved) == 1
    ctl.set_note_length(1234)
    assert ctl.settings.note_length_ms == 1230
    assert ctl.note_length_enabled
    ctl.set_legato(True)
    assert not ctl.note_length_enabled and e.posted[-1][1].legato


def test_window_moved_saves_without_engine_post():
    ctl, e, s, *_ = make()
    ctl.window_moved(10, 20)
    ctl.window_moved(10, 20)
    assert len(s.saved) == 1 and s.saved[0].window_x == 10 and e.posted == []


def test_close_to_tray_balloon_once():
    ctl, _e, _s, v, *_ = make()
    ctl.close_window()
    assert "hide" in v.calls and ctl.hidden
    assert ("notify", "MouseMusic is still running",
            "It's in the system tray. Right-click the icon to quit.") in v.calls  # fmt: skip
    assert ctl.settings.tray_hint_shown
    v.calls.clear()
    ctl.close_window()
    assert not any(isinstance(x, tuple) for x in v.calls)


def test_close_to_tray_playing_text_and_escape():
    ctl, _e, _s, v, *_ = make()
    ctl.close_window(balloon=False)
    assert not ctl.settings.tray_hint_shown
    ctl.handle_event(Event("started", {"device": GS}))
    ctl.close_window()
    notes = [c for c in v.calls if isinstance(c, tuple)]
    assert notes[-1][2].startswith("It's still playing in the system tray. Press Ctrl+Alt+M")
    ctl.show_window()
    assert v.calls[-1] == "show" and not ctl.hidden


def test_w5_once_per_session():
    ctl, *_ = make()
    ctl.on_save_error()
    assert text(ctl) == strings.W5_CANT_SAVE
    ctl.status.clear_warning("W5")
    ctl.on_save_error()
    assert not ctl.status.has_warning("W5")


def test_quit_shuts_down_flushes_once():
    ctl, e, s, v, *_ = make()
    ctl.quit()
    ctl.quit()
    assert e.shut == 1 and s.flushed == 1 and v.calls.count("quit") == 1


def test_dispatch_routes(caplog):
    ctl, e, _s, _v, *_ = make()
    ctl.startup()
    ctl.dispatch(("toggle", None))
    assert e.posted[-1] == (eng.START, None)
    ctl.dispatch(("event", Event("started", {"device": GS})))
    assert ctl.status.playing
    for cmd in ("suspend", "resume", "display_changed"):
        ctl.dispatch((cmd, None))
        assert e.posted[-1] == (cmd, None)
    ctl.dispatch(("show", None))
    ctl.dispatch(("save_error", None))
    ctl.dispatch(("weird", None))
    assert "unknown UI item" in caplog.text
    ctl.tick()
    ctl.dispatch(("quit", None))
    assert e.shut == 1


def test_no_view_is_safe():
    ctl, _e, _s, _v, *_ = make()
    ctl.view = None
    ctl.startup()
    ctl.close_window()
    ctl.show_window()
    ctl.handle_event(Event("error", {"error": DeviceLostError("x")}))
    ctl.quit()
