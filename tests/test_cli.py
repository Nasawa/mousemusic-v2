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
    ]


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
