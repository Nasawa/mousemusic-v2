"""G2 edge-case tests drawn from docs/test-plan.md (case ids in each docstring)."""

import json

import pytest

from mousemusic import config
from mousemusic.config import DEFAULTS
from mousemusic.engine import Engine
from mousemusic.mapping import HysteresisMapper, Rect, build_grid, cell_at
from mousemusic.midi import DeviceLostError, volume_to_cc7
from mousemusic.midi.fake import FakeMidiOut
from mousemusic.platform.hotkey import (
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMRESUMESUSPEND,
    PBT_APMSUSPEND,
    WM_POWERBROADCAST,
    parse_hotkey,
    translate_message,
)

GS = "Microsoft GS Wavetable Synth"
ON, OFF, CC = 0x90, 0x80, 0xB0


class _Cursor:
    def __init__(self, pos, virt):
        self.pos, self.virt = pos, virt

    def position(self):
        return self.pos

    def virtual_rect(self):
        return self.virt

    def primary_rect(self):
        return Rect(0, 0, 1920, 1080)


class _Timer:
    active = False

    def begin(self):
        self.active = True

    def end(self):
        self.active = False


VIRT = Rect(-1920, 0, 3840, 1080)


def _engine(settings=DEFAULTS, virt=VIRT, pos=(0, 500)):
    fake = FakeMidiOut((GS,))
    cur = _Cursor(pos, virt)
    events = []
    eng = Engine(fake, cur, settings, emit=events.append, timer=_Timer())
    return eng, fake, cur, events


# --- settings corruption (SC-02/03/04/09, §4 "never crashes on bad settings") ---------------


def test_deeply_nested_json_does_not_crash_sc09(tmp_path):
    """A pathological file (deep nesting) must go down the corrupt path, not raise
    RecursionError out of load_report()."""
    p = tmp_path / "settings.json"
    p.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    result = config.load_report(p)
    assert result.corrupt and result.settings == DEFAULTS
    assert (tmp_path / "settings.json.bak").exists()


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_non_finite_json_numbers_fall_back_to_default_sc05(tmp_path, literal):
    """Python's json accepts NaN/Infinity and turns 1e400 into inf. Each numeric key must
    fall back to its own default (W3), and the rest of the file must be kept."""
    p = tmp_path / "settings.json"
    keys = ("volume", "velocity", "note_length_ms", "poll_hz")
    body = ", ".join(f'"{k}": {literal}' for k in keys)
    p.write_text("{" + body + ', "scale": "blues"}', encoding="utf-8")
    result = config.load_report(p)
    assert not result.corrupt
    for k in keys:
        assert getattr(result.settings, k) == getattr(DEFAULTS, k)
    assert result.settings.scale == "blues"
    assert len(result.issues) >= len(keys)


def test_utf8_bom_file_is_recoverable_from_bak(tmp_path):
    """Files saved by PowerShell 5 `Set-Content -Encoding utf8` start with a BOM. Today that
    is treated as corrupt (§4); at minimum the user's original bytes must survive in .bak."""
    p = tmp_path / "settings.json"
    original = "\ufeff" + json.dumps({"volume": 37})
    p.write_text(original, encoding="utf-8")
    result = config.load_report(p)
    assert result.settings.volume in (37, DEFAULTS.volume)
    if result.corrupt:
        assert (tmp_path / "settings.json.bak").read_text(encoding="utf-8") == original
        assert json.loads(p.read_text(encoding="utf-8")) == DEFAULTS.to_dict()


# --- volume (VO-02/03/04) -----------------------------------------------------------------


def test_volume_to_cc7_full_range_vo02():
    values = [volume_to_cc7(v) for v in range(101)]
    assert values[0] == 0 and values[100] == 127 and values[80] == 102 and values[50] == 64
    assert values == sorted(values)  # monotonic
    assert all(0 <= c <= 127 for c in values)
    assert all(values[v] == round(v * 127 / 100) for v in range(101))
    # out-of-range inputs are clamped, never produce an invalid data byte
    assert volume_to_cc7(-50) == 0 and volume_to_cc7(1000) == 127


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(55.5, 56), (True, 80), ("80", 80), (None, 80), ([], 80), (-1, 0), (101, 100)],
)
def test_volume_types_and_range_vo03_vo04(raw, expected):
    settings, issues = config.validate({"volume": raw})
    assert settings.volume == expected
    assert issues  # every one of these is reported (W3)


# --- device loss / stuck notes (MD-09a, SN-01, SN-09c) ----------------------------------------


def test_device_loss_on_volume_cc7_is_e4():
    """MD-09a: the loss rule covers every short message, including CC7 from the slider."""
    eng, fake, _cur, events = _engine()
    eng.post("start")
    eng.step(0.0)
    fake.fail_after = len(fake.messages)
    eng.post("set_volume", 10)
    eng.step(0.1)
    assert not eng.playing and not fake.is_open
    assert isinstance(events[-1].data["error"], DeviceLostError)


def test_suspend_with_legato_note_held_sends_off_then_all_notes_off_sn09():
    """SN-09: with legato a note never expires; suspend must still silence it before close."""
    eng, fake, _cur, _events = _engine(DEFAULTS.replace(legato=True))
    eng.post("start")
    eng.step(0.0)
    held = [m for m in fake.messages if m[0] == ON][-1][1]
    eng.step(5.0)  # long after note_length_ms: still held because of legato
    assert not any(m[0] == OFF for m in fake.messages)
    fake.log.clear()
    fake.messages.clear()
    eng.post("suspend")
    eng.step(5.1)
    assert fake.messages == [(OFF, held, 0), (CC, 123, 0)]
    assert fake.log[-2:] == ["reset", "close"]


def test_repeated_suspend_and_stray_resume_are_safe_sn09e():
    eng, fake, _cur, _events = _engine()
    eng.post("resume")  # resume without a prior suspend: nothing happens
    eng.step(0.0)
    assert not fake.is_open
    eng.post("start")
    eng.step(0.1)
    eng.post("suspend")
    eng.post("suspend")  # e.g. both a sleep and a hibernate broadcast
    eng.step(0.2)
    assert not fake.is_open
    eng.post("resume")
    eng.post("resume")  # PBT_APMRESUMESUSPEND and PBT_APMRESUMEAUTOMATIC both arrive
    eng.step(0.3)
    assert eng.playing and fake.is_open


def test_both_resume_broadcasts_map_to_resume():
    assert translate_message(WM_POWERBROADCAST, PBT_APMSUSPEND) == "suspend"
    assert translate_message(WM_POWERBROADCAST, PBT_APMRESUMESUSPEND) == "resume"
    assert translate_message(WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC) == "resume"
    assert translate_message(WM_POWERBROADCAST, 0x000A) is None  # PBT_APMPOWERSTATUSCHANGE


# --- hotkey parsing (SD-14) -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Alt+Alt+M",
        "Ctrl+F13",
        "Ctrl+F0",
        "Ctrl+F01",
        "Ctrl+MM",
        "M",
        "Ctrl+Alt",
        "Ctrl+Alt+M+",
        "Ctrl+Ä",
        "Ctrl+\uff11",
        "Control+M",
        "Ctrl+Alt+Del",
        "",
        "+",
        123,
        None,
    ],
)
def test_hotkey_rejects_invalid_sd14(text):
    assert parse_hotkey(text) is None


@pytest.mark.parametrize(
    ("text", "mods", "vk"),
    [(" ctrl + alt + m ", 0x3, ord("M")), ("Shift+Win+F12", 0xC, 0x7B), ("CTRL+0", 0x2, 0x30)],
)
def test_hotkey_accepts_case_and_spacing_sd14(text, mods, vk):
    hk = parse_hotkey(text)
    assert hk is not None and (hk.modifiers, hk.vk) == (mods, vk)


# --- DPI / multi-monitor (DM-02, DM-05, DM-10, DM-11) ---------------------------------------


def test_negative_x_and_y_virtual_desktop_corners_dm02():
    """Secondary monitor left of AND above the primary: both origins negative."""
    grid = build_grid("pentatonic_major", "C", 36, 96, "classic")
    rect = Rect(-2560, -1440, 2560 + 1920, 1440 + 1080)
    assert cell_at(-2560, -1440, rect, grid) == cell_at(-99999, -99999, rect, grid)
    top_left = cell_at(-2560, -1440, rect, grid)
    bottom_right = cell_at(rect.x + rect.w - 1, rect.y + rect.h - 1, rect, grid)
    assert (top_left.col, top_left.row) == (0, 0)
    assert (bottom_right.col, bottom_right.row) == (grid.cols - 1, grid.rows - 1)
    # the primary monitor's origin (0, 0) is in the middle of the grid, not at col 0
    assert 0 < cell_at(0, 0, rect, grid).col < grid.cols - 1


def test_every_pixel_column_maps_to_a_valid_monotonic_cell_dm05():
    grid = build_grid("chromatic", "C", 0, 127, "full_gm")
    rect = Rect(-1366, 0, 1366 + 3840, 2160)  # odd width so boundaries land on fractions
    cols = [cell_at(x, 0, rect, grid).col for x in range(rect.x, rect.x + rect.w)]
    assert cols == sorted(cols) and cols[0] == 0 and cols[-1] == grid.cols - 1
    assert set(cols) == set(range(grid.cols))  # every note is reachable


def test_hotplug_shrinks_rect_while_cursor_outside_dm11():
    """After unplugging the left monitor, a stale cursor position on it clamps to col 0."""
    grid = build_grid("pentatonic_major", "C", 36, 96, "classic")
    m = HysteresisMapper(grid, Rect(-1920, 0, 3840, 1080))
    m.update(-1000, 500)
    m.reset(rect=Rect(0, 0, 1920, 1080))
    cell = m.update(-1000, 500)
    assert cell.col == 0 and 0 <= cell.row < grid.rows


def test_explicit_stop_clears_pending_wake_sn09a():
    """Suspend while playing, resume never arrives, user presses Stop: a later resume must
    not start playback by surprise (§11 OQ-3: resume only if it was playing)."""
    eng, fake, _cur, _events = _engine()
    eng.post("start")
    eng.step(0.0)
    eng.post("suspend")
    eng.step(0.1)
    eng.post("stop")
    eng.post("resume")
    eng.step(0.2)
    assert not eng.playing and not fake.is_open


@pytest.mark.parametrize("text", ["Alt+Alt+M", "Ctrl+F13", "Ctrl+MM", "Control+M", "+", 123, None])
def test_invalid_hotkey_setting_resets_to_default_with_w3_sd14(text):
    from mousemusic.config import DEFAULTS, validate

    s, issues = validate({"hotkey": text})
    assert s.hotkey == DEFAULTS.hotkey == "Ctrl+Alt+M"
    assert any(i.startswith("hotkey=") for i in issues)  # W3 is shown for any issue
