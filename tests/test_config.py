import json
import logging
import os
import sys
from pathlib import Path

import pytest

from mousemusic import config
from mousemusic.config import (
    DEFAULTS,
    DebouncedSaver,
    Settings,
    load,
    save,
    settings_path,
    validate,
)

SPEC_DEFAULTS = {
    "schema": 1,
    "midi_device": "Microsoft GS Wavetable Synth",
    "scale": "pentatonic_major",
    "root": "C",
    "low_note": 36,
    "high_note": 96,
    "instrument_set": "classic",
    "volume": 80,
    "velocity": 100,
    "note_length_ms": 250,
    "legato": False,
    "poll_hz": 125,
    "screen_mode": "virtual_desktop",
    "start_on_launch": False,
    "hotkey": "Ctrl+Alt+M",
    "theme": "system",
    "first_run_done": False,
    "tray_hint_shown": False,
    "window_x": None,
    "window_y": None,
    # taskbar notes, docs/design/cell-granularity.md §4.1 (CG-S1)
    "taskbar_mode": False,
    "taskbar_slot_dip": 44,
    "taskbar_offset_dip": 0,
    "taskbar_low_note": 48,
    "taskbar_high_note": 96,
    "taskbar_program": 13,
    "taskbar_monitors": "all",
    "taskbar_slot_source": "auto",
    "taskbar_secondary_programs": [8, 108, 9],
    "taskbar_tray": True,
    "taskbar_tray_slot_dip": 32,
}


def test_defaults_match_spec():
    assert DEFAULTS.to_dict() == SPEC_DEFAULTS


# --- load: missing / corrupt / out-of-range / unknown keys ----------------------


def test_missing_file_gives_defaults_and_writes_nothing(tmp_path):
    p = tmp_path / "settings.json"
    assert load(p) == DEFAULTS
    assert not p.exists()


@pytest.mark.parametrize(
    "content",
    [b"{not json", b"", b"[1, 2, 3]", b'"string"', b"null", b"\xff\xfe\x00garbage", b'{"a": '],
)
def test_corrupt_file_moved_to_bak_and_replaced(tmp_path, content, caplog):
    p = tmp_path / "settings.json"
    p.write_bytes(content)
    with caplog.at_level(logging.WARNING):
        assert load(p) == DEFAULTS
    assert (tmp_path / "settings.json.bak").read_bytes() == content
    assert json.loads(p.read_text(encoding="utf-8")) == SPEC_DEFAULTS
    assert "corrupt" in caplog.text


def test_corrupt_overwrites_existing_bak(tmp_path, caplog):
    p = tmp_path / "settings.json"
    (tmp_path / "settings.json.bak").write_text("old")
    p.write_text("bad")
    with caplog.at_level(logging.WARNING):
        load(p)
    assert "overwriting previous" in caplog.text
    assert (tmp_path / "settings.json.bak").read_text() == "bad"


def test_unreadable_file_gives_defaults_without_moving(tmp_path, caplog):
    p = tmp_path / "settings.json"
    p.mkdir()  # reading a directory raises OSError
    with caplog.at_level(logging.WARNING):
        assert load(p) == DEFAULTS
    assert p.is_dir()
    assert "could not read" in caplog.text


def test_corrupt_and_cannot_move(tmp_path, monkeypatch, caplog):
    p = tmp_path / "settings.json"
    p.write_text("bad")

    def boom(*a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(config.os, "replace", boom)
    with caplog.at_level(logging.WARNING):
        assert load(p) == DEFAULTS
    assert "could not be moved" in caplog.text
    assert "could not save" in caplog.text


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"scale": "blues", "bogus": 1, "nested": {"x": 2}}))
    s = load(p)
    assert s.scale == "blues"
    assert not hasattr(s, "bogus")


def test_partial_file_fills_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"velocity": 64}')
    assert load(p) == Settings(velocity=64)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("volume", 150, 100),
        ("volume", -5, 0),
        ("velocity", 0, 1),
        ("velocity", 300, 127),
        ("note_length_ms", 1, 50),
        ("note_length_ms", 10**9, 2000),
        ("poll_hz", 0, 30),
        ("poll_hz", 10_000, 250),
        ("low_note", -12, 0),
        ("high_note", 200, 127),
        ("volume", 55.6, 56),
        ("window_x", -(10**6), -32768),
        ("window_y", 10**6, 32767),
    ],
)
def test_out_of_range_clamped(tmp_path, key, value, expected, caplog):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({key: value}))
    with caplog.at_level(logging.WARNING):
        assert getattr(load(p), key) == expected
    assert key in caplog.text


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("volume", "loud"),
        ("volume", True),
        ("volume", None),
        ("volume", float("inf")),
        ("legato", 1),
        ("legato", "yes"),
        ("scale", "dorian"),
        ("scale", 3),
        ("root", "H"),
        ("root", 5),
        ("instrument_set", "kazoo"),
        ("screen_mode", "left"),
        ("midi_device", ""),
        ("midi_device", 7),
        ("hotkey", 5),
        ("hotkey", "Banana+Q"),
        ("hotkey", "Ctrl+Ctrl+M"),
        ("window_x", "left"),
        ("window_y", False),
    ],
)
def test_invalid_values_reset_to_default(key, value):
    s, issues = validate({key: value})
    assert getattr(s, key) == getattr(DEFAULTS, key)
    assert issues


def test_root_normalized():
    assert validate({"root": "bb"})[0].root == "A#"
    assert validate({"root": "f#"})[0].root == "F#"


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (36, 96, (36, 96)),
        (60, 72, (60, 72)),
        (60, 65, (60, 72)),
        (90, 40, (90, 102)),
        (120, 127, (115, 127)),
        (127, 127, (115, 127)),
        (0, 0, (0, 12)),
        (-50, 500, (0, 127)),
    ],
)
def test_note_range_rule_oq8(low, high, expected):
    s, issues = validate({"low_note": low, "high_note": high})
    assert (s.low_note, s.high_note) == expected
    assert bool(issues) == ((low, high) != expected)


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("Ctrl+Alt+M", "Ctrl+Alt+M"),
        ("alt + ctrl + m", "Ctrl+Alt+M"),
        ("shift+alt+ctrl+m", "Ctrl+Alt+Shift+M"),
        ("Win+F9", "Win+F9"),
        ("off", "Off"),
        ("", "Off"),
        ("None", "Off"),
    ],
)
def test_hotkey_normalised(value, want):
    assert validate({"hotkey": value}) == (Settings(hotkey=want), [])


def test_valid_file_has_no_issues():
    assert validate(SPEC_DEFAULTS) == (DEFAULTS, [])


def test_newer_schema_reads_known_keys_without_rewrite(tmp_path):
    p = tmp_path / "settings.json"
    text = json.dumps({"schema": 2, "scale": "blues", "future_key": [1]})
    p.write_text(text)
    s = load(p)
    assert s.scale == "blues" and s.schema == 1
    assert p.read_text() == text  # untouched until the next save
    assert any("newer" in i for i in validate({"schema": 2})[1])


@pytest.mark.parametrize("schema", ["1", None, True, 1.5])
def test_invalid_schema_treated_as_current(schema):
    s, issues = validate({"schema": schema, "scale": "minor"})
    assert s.scale == "minor" and issues


def test_migrations_run_in_order(monkeypatch):
    monkeypatch.setattr(config, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(
        config,
        "MIGRATIONS",
        {0: lambda r: {**r, "scale": "major"}, 2: lambda r: {**r, "root": "D"}},
    )
    s, issues = validate({"schema": 0})
    assert (s.scale, s.root) == ("major", "D") and not issues


def test_missing_schema_is_current():
    assert validate({}) == (DEFAULTS, [])


def test_replace_validates():
    s = DEFAULTS.replace(volume=999, scale="major")
    assert s.volume == 100 and s.scale == "major"
    assert DEFAULTS.volume == 80  # immutable


# --- save / round-trip ----------------------------------------------------------


def test_round_trip_equality(tmp_path):
    p = tmp_path / "sub" / "dir" / "settings.json"
    s = Settings(
        midi_device="loopMIDI Port",
        scale="blues",
        root="F#",
        low_note=40,
        high_note=80,
        instrument_set="full_gm",
        volume=0,
        velocity=1,
        note_length_ms=1000,
        legato=True,
        poll_hz=60,
        screen_mode="primary",
        start_on_launch=True,
        hotkey="Ctrl+Shift+F12",
        first_run_done=True,
        tray_hint_shown=True,
        window_x=-1500,
        window_y=20,
    )
    save(s, p)
    assert load(p) == s
    assert validate(s.to_dict()) == (s, [])
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == 1
    assert p.read_text(encoding="utf-8").startswith('{\n  "schema": 1,')  # indented, human-readable


def test_save_leaves_no_temp_files(tmp_path):
    p = tmp_path / "settings.json"
    save(DEFAULTS, p)
    save(DEFAULTS.replace(volume=10), p)
    assert sorted(x.name for x in tmp_path.iterdir()) == ["settings.json"]


def test_failed_replace_keeps_old_file_and_cleans_temp(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    save(DEFAULTS, p)
    before = p.read_text()

    def boom(*a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(config.os, "replace", boom)
    monkeypatch.setattr(config.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        save(DEFAULTS.replace(volume=1), p)
    assert p.read_text() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["settings.json"]


def test_replace_retried_on_transient_permission_error(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    real = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("busy")
        real(src, dst)

    monkeypatch.setattr(config.os, "replace", flaky)
    monkeypatch.setattr(config.time, "sleep", lambda s: None)
    save(DEFAULTS, p)
    assert len(calls) == 2 and load(p) == DEFAULTS


# --- location -----------------------------------------------------------------


def test_appdata_location(tmp_path):
    p = settings_path(app_dir=None, environ={"APPDATA": str(tmp_path)})
    assert p == tmp_path / "MouseMusic" / "settings.json"


def test_no_appdata_falls_back_to_home_config(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert settings_path(app_dir=None, environ={}) == tmp_path / ".config/MouseMusic/settings.json"


def test_portable_when_file_next_to_exe(tmp_path):
    exe = tmp_path / "exe"
    exe.mkdir()
    (exe / "settings.json").write_text("{}")
    assert settings_path(app_dir=exe, environ={"APPDATA": "x"}) == exe / "settings.json"


def test_not_portable_without_file(tmp_path):
    exe = tmp_path / "exe"
    exe.mkdir()
    assert settings_path(app_dir=exe, environ={"APPDATA": str(tmp_path)}) == (
        tmp_path / "MouseMusic" / "settings.json"
    )


def test_portable_flag_forces_exe_dir(tmp_path):
    exe = tmp_path / "exe"
    exe.mkdir()
    assert settings_path(portable=True, app_dir=exe, environ={"APPDATA": "x"}) == (
        exe / "settings.json"
    )


def test_exe_dir_frozen_and_source(monkeypatch, tmp_path):
    assert config.exe_dir() is None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MouseMusic.exe"))
    assert config.exe_dir() == tmp_path.resolve()
    assert settings_path(environ={}) != tmp_path / "settings.json"  # no file, not portable
    (tmp_path / "settings.json").write_text("{}")
    assert settings_path(environ={}) == tmp_path.resolve() / "settings.json"


def test_default_environ_used(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert settings_path(app_dir=None) == tmp_path / "MouseMusic" / "settings.json"


# --- debounced save -------------------------------------------------------------


class FakeTimer:
    def __init__(self, delay, fn):
        self.delay, self.fn = delay, fn
        self.started = self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn()


def test_debounce_only_last_request_written(tmp_path):
    p = tmp_path / "settings.json"
    timers = []

    def factory(delay, fn):
        timers.append(FakeTimer(delay, fn))
        return timers[-1]

    saver = DebouncedSaver(p, timer_factory=factory)
    for v in (10, 20, 30):
        saver.request(DEFAULTS.replace(volume=v))
    assert [t.delay for t in timers] == [0.5] * 3
    assert [t.cancelled for t in timers] == [True, True, False]
    assert not p.exists()
    for t in timers:
        t.fire()
    assert load(p).volume == 30
    assert saver.pending is None
    assert saver.flush() is False


def test_debounce_flush_writes_immediately(tmp_path):
    p = tmp_path / "settings.json"
    t = []
    saver = DebouncedSaver(p, timer_factory=lambda d, f: t.append(FakeTimer(d, f)) or t[-1])
    saver.request(DEFAULTS.replace(scale="minor"))
    assert saver.pending.scale == "minor"
    assert saver.flush() is True
    assert t[0].cancelled
    assert load(p).scale == "minor"


def test_debounce_real_timer(tmp_path):
    p = tmp_path / "settings.json"
    saver = DebouncedSaver(p, delay_s=0.01)
    saver.request(DEFAULTS.replace(volume=42))
    for _ in range(200):
        if p.exists():
            break
        import time

        time.sleep(0.01)
    assert load(p).volume == 42


def test_unwritable_keeps_pending_retry_on_next_change(tmp_path):
    """OQ-11: a failed save keeps settings in memory; the next change retries the same path."""
    target_dir = tmp_path / "locked"
    target_dir.write_text("not a dir")  # makes the folder uncreatable
    t = []
    saver = DebouncedSaver(
        target_dir / "settings.json", timer_factory=lambda d, f: t.append(FakeTimer(d, f)) or t[-1]
    )
    saver.request(DEFAULTS.replace(volume=5))
    assert saver.flush() is False
    target_dir.unlink()
    saver.request(DEFAULTS.replace(volume=6))
    assert saver.flush() is True
    assert load(target_dir / "settings.json").volume == 6


def test_debounce_save_failure_returns_false(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    saver = DebouncedSaver(blocker / "settings.json", timer_factory=lambda d, f: FakeTimer(d, f))
    saver.request(DEFAULTS)
    with caplog.at_level(logging.WARNING):
        assert saver.flush() is False
    assert "could not save" in caplog.text


def test_load_report_flags(tmp_path):
    from mousemusic.config import load_report

    p = tmp_path / "settings.json"
    r = load_report(p)
    assert r.settings == DEFAULTS and not r.existed and not r.corrupt and r.issues == ()
    p.write_text('{"volume": 500}')
    r = load_report(p)
    assert r.existed and not r.corrupt and r.issues and r.settings.volume == 100
    p.write_text("{bad")
    assert load_report(p).corrupt
    p.write_bytes(b"\xff\xfe")
    assert load_report(p).corrupt
    d = tmp_path / "dir.json"
    d.mkdir()
    r = load_report(d)
    assert r.existed and not r.corrupt


def test_saver_on_error_called(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    calls = []
    saver = DebouncedSaver(
        blocker / "settings.json",
        timer_factory=lambda d, f: FakeTimer(d, f),
        on_error=lambda: calls.append(1),
    )
    saver.request(DEFAULTS)
    saver.flush()
    assert calls == [1]


def test_bom_prefixed_file_is_not_corrupt(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"schema": 1, "volume": 33}')
    r = config.load_report(path)
    assert not r.corrupt and r.settings.volume == 33
    assert not (tmp_path / "settings.json.bak").exists()
    config.save(r.settings, path)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")  # written back as plain utf-8


@pytest.mark.parametrize(
    ("value", "want", "ok"),
    [
        ("system", "system", True),
        ("Dark", "dark", True),
        (" LIGHT ", "light", True),
        ("sepia", "system", False),
        (1, "system", False),
        (None, "system", False),
    ],
)
def test_theme_validated_and_normalised(value, want, ok):
    s, issues = validate({"theme": value})
    assert s.theme == want
    assert (issues == []) == ok


def test_theme_default_and_round_trip(tmp_path):
    assert DEFAULTS.theme == "system"
    path = tmp_path / "settings.json"
    config.save(DEFAULTS.replace(theme="dark"), path)
    assert config.load_report(path).settings.theme == "dark"
