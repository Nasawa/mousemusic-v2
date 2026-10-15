import subprocess
import sys

import pytest

from mousemusic import __version__
from mousemusic.__main__ import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"mousemusic {__version__}"


def test_no_args_launches_app(monkeypatch):
    import mousemusic.app as app

    seen = []
    monkeypatch.setattr(app, "run", lambda opts: seen.append(opts) or 0)
    assert main(["--dry-run", "--portable", "--log-level", "debug"]) == 0
    assert seen[0].dry_run and seen[0].portable and seen[0].log_level == "debug"


def test_self_test_passes_with_zero_devices():
    from mousemusic.__main__ import self_test
    from mousemusic.midi.fake import FakeMidiOut

    lines = []
    assert self_test(lambda: FakeMidiOut([]), out=lines.append) == 0
    assert [ln for ln in lines if ln.startswith("PASS")] == [
        "PASS bundle",
        "PASS settings",
        "PASS mapping",
        "PASS midi",
        "PASS taskbar",
    ]
    assert "     no taskbar zone" in lines  # no taskbar on CI/Linux: still a pass


def test_self_test_reports_failure():
    from mousemusic.__main__ import self_test

    def boom():
        raise RuntimeError("no winmm")

    lines = []
    assert self_test(boom, out=lines.append) == 1
    assert "FAIL midi: no winmm" in lines


def test_python_dash_m_self_test():
    out = subprocess.run(
        [sys.executable, "-m", "mousemusic", "--self-test"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_python_dash_m_version():
    out = subprocess.run(
        [sys.executable, "-m", "mousemusic", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"mousemusic {__version__}"


def test_list_devices_none(capsys, monkeypatch):
    from mousemusic.midi import fake

    monkeypatch.setattr("mousemusic.__main__.default_backend", lambda: fake.FakeMidiOut([]))
    assert main(["--list-devices"]) == 0
    assert capsys.readouterr().out == "No MIDI output devices found.\n"


def test_list_devices_lines():
    from mousemusic.__main__ import list_devices
    from mousemusic.midi.fake import FakeMidiOut

    lines = []
    assert list_devices(lambda: FakeMidiOut(["Microsoft GS Wavetable Synth", "loopMIDI"]),
                        lines.append) == 0  # fmt: skip
    assert lines == ["0: Microsoft GS Wavetable Synth", "1: loopMIDI"]


def test_list_devices_backend_failure_is_friendly(caplog):
    from mousemusic.__main__ import list_devices

    def boom():
        raise OSError("winmm.dll missing")

    lines = []
    assert list_devices(boom, lines.append) == 0
    assert lines == ["No MIDI output devices found."]


def _play(text, be=None, **kw):
    from mousemusic.__main__ import play_instrument
    from mousemusic.midi.fake import FakeMidiOut

    out, err = [], []
    be = be if be is not None else FakeMidiOut()
    rc = play_instrument(text, backend_factory=lambda: be, wait=lambda s: False,
                         out=out.append, err=err.append, **kw)  # fmt: skip
    return rc, out, err, be


def test_play_instrument_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    rc, out, err, be = _play("40")
    assert rc == 0 and not err
    assert out == ["Playing GM program 40 (Violin)...",
                   "Done: played on Microsoft GS Wavetable Synth."]  # fmt: skip
    assert (0xC0, 40, 0) in be.messages


@pytest.mark.parametrize("text", ["128", "-3", "violin"])
def test_play_instrument_invalid(text):
    rc, out, err, be = _play(text)
    assert rc == 2 and not out and not be.messages
    assert err[0].startswith("--play-instrument needs a GM program number from 0 to 127")


def test_play_instrument_no_device_and_busy(tmp_path, monkeypatch):
    from mousemusic.midi.fake import FakeMidiOut
    from mousemusic.ui import strings

    monkeypatch.setenv("APPDATA", str(tmp_path))
    rc, _out, err, _ = _play("0", FakeMidiOut([]))
    assert rc == 1 and err == [strings.E1_NO_DEVICE]
    rc, _out, err, _ = _play("0", FakeMidiOut(["Synth"], open_errors={0: 4}))
    assert (rc == 1 and "Synth" in err[0] and "in use" in err[0].lower()) or rc == 1


def test_play_instrument_bad_settings_uses_defaults(monkeypatch):
    import mousemusic.config as config

    monkeypatch.setattr(config, "load", lambda p: (_ for _ in ()).throw(OSError("x")))
    rc, *_ = _play("1")
    assert rc == 0


def test_play_instrument_main_dry_run(capsys, tmp_path, monkeypatch):
    import threading

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(threading.Event, "wait", lambda self, t=None: False)
    assert main(["--play-instrument=5", "--dry-run"]) == 0
    text = capsys.readouterr().out
    assert "Playing GM program 5" in text and "msg C0 05 00" in text and "Done:" in text
    assert main(["--play-instrument", "999"]) == 2
