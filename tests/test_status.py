import pytest

from mousemusic.ui import strings
from mousemusic.ui.status import (
    AMBER,
    ERROR,
    GREEN,
    GREY,
    RED,
    WARNING,
    StatusModel,
    display_note,
    shorten,
)

GS = "Microsoft GS Wavetable Synth"


@pytest.mark.parametrize(
    ("note", "root", "name"),
    [(60, "C", "C4"), (61, "C", "C♯4"), (61, "F", "D♭4"), (70, "A#", "B♭4"), (63, "D#", "E♭4"),
     (68, "G#", "A♭4"), (66, "G", "F♯4"), (12, "C", "C0"), (108, "C", "C8")],
)  # fmt: skip
def test_display_note(note, root, name):
    assert display_note(note, root) == name


def test_shorten():
    assert shorten(GS) == "Microsoft GS Wavetable…"
    assert shorten("loopMIDI Port") == "loopMIDI Port"


def test_stopped_and_first_run_and_no_hotkey():
    m = StatusModel()
    s = m.current(0)
    assert (s.dot, s.color, s.text) == ("●", GREY, "Stopped — press Start or Ctrl+Alt+M")
    m.first_run = True
    assert m.current(0).text == strings.STATUS_FIRST_RUN
    m.first_run = False
    m.hotkey_ok = False
    assert m.current(0).text == "Stopped — press Start"
    assert m.hotkey_hint() == "(shortcut off)"
    m.hotkey_ok = True
    assert m.hotkey_hint() == "Ctrl+Alt+M"


def test_playing_flow_texts():
    m = StatusModel(first_run=True)
    m.on_start_requested(GS)
    assert m.current(0).text == "Connecting to Microsoft GS Wavetable Synth…"
    m.on_started(GS)
    s = m.current(0)
    assert s.text == "Playing — move the mouse · Microsoft GS Wavetable…" and s.color == GREEN
    m.on_note(64, 11)
    assert m.current(0).text == "E4 · Vibraphone · Microsoft GS Wavetable…"
    assert not m.first_run and m.started_once
    m.reconnecting = True
    assert m.current(0).text == "Reconnecting…"
    m.on_stopped()
    assert m.current(0).text.startswith("Stopped")


def test_precedence_error_warning_hint():
    m = StatusModel(first_run=True)
    m.add_warning("W1", "w1", 0)
    m.set_error("E1", "e1", "no-midi-device")
    s = m.current(0)
    assert (s.dot, s.color, s.severity, s.help_anchor) == ("■", RED, ERROR, "no-midi-device")
    m.clear_error("E2")  # wrong id: stays
    assert m.current(0).text == "e1"
    m.clear_error("E1")
    s = m.current(0)
    assert (s.dot, s.color, s.severity, s.text) == ("▲", AMBER, WARNING, "w1")
    m.clear_warning("W1")
    assert m.current(0).text == strings.STATUS_FIRST_RUN


def test_warning_expiry_rules():
    m = StatusModel()
    m.add_warning("W4", "w4", 0, duration=15)
    m.add_warning("W2", "w2", 0, duration=15, until_start=True)
    m.add_warning("W1", "w1", 0)
    assert m.current(14).text == "w4"
    assert m.current(15).text == "w2"  # W4 gone; W2 waits for the first Start
    m.on_started(GS)
    assert m.current(16).text == "w1"  # W2 gone (started and 15 s passed); W1 persists
    assert m.has_warning("W1") and not m.has_warning("W2")


def test_until_start_respects_15s_after_early_start():
    m = StatusModel()
    m.add_warning("W3", "w3", 0, duration=15, until_start=True)
    m.on_started(GS)
    assert m.current(5).text == "w3"
    assert m.current(15.1).text != "w3"


def test_add_same_warning_replaces():
    m = StatusModel()
    m.add_warning("W1", "a", 0)
    m.add_warning("W1", "b", 1)
    assert [w.text for w in m.warnings] == ["b"]


def test_tray_icon_and_tooltip():
    m = StatusModel()
    assert m.tray_icon() == "idle"
    assert m.tray_tooltip("0.1.0") == "MouseMusic v0.1.0 — Stopped"
    m.on_started(GS)
    assert m.tray_icon() == "playing"
    assert m.tray_tooltip("0.1.0") == "MouseMusic v0.1.0 — Playing"
    m.add_warning("W1", "x", 0)
    assert m.tray_icon() == "playing"  # warnings keep the icon
    m.set_error("E4", "lost")
    assert m.tray_icon() == "error"
    assert m.tray_tooltip("0.1.0") == "MouseMusic v0.1.0 — No sound (click for details)"
    m.on_started(GS)  # successful start resolves the error
    assert m.error is None
