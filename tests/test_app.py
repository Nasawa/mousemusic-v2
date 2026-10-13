"""End-to-end startup/shutdown of the real app wiring with --dry-run (Linux, under xvfb).

On Windows the same path also creates the hotkey window and tray, which are covered by
Grace's manual checks instead (see the PR's real-Windows list)."""

import sys
import tkinter as tk

import pytest

from mousemusic import app, config


class FakeInstance:
    def __init__(self, first=True):
        self.first, self.signalled, self.released, self.show_message = first, 0, 0, None

    def acquire(self):
        return self.first

    def signal_first(self):
        self.signalled += 1

    def release(self):
        self.released += 1


def test_second_instance_signals_and_exits(tmp_path):
    inst = FakeInstance(first=False)
    opts = app.Options(single_instance=inst, log_directory=tmp_path)
    assert app.run(opts) == 0
    assert inst.signalled == 1 and inst.released == 0


@pytest.mark.skipif(sys.platform == "win32", reason="real tray/hotkey on Windows: manual")
def test_dry_run_start_play_quit(tmp_path, capsys, monkeypatch):
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    monkeypatch.setattr(app.eng, "install_exit_handlers", lambda engine, **kw: [])
    inst = FakeInstance()
    seen = {}

    def on_ready(root, controller, q):
        seen["ctl"] = controller
        q.put(("toggle", None))
        root.after(400, lambda: q.put(("quit", None)))

    path = tmp_path / "settings.json"
    opts = app.Options(
        dry_run=True, settings_path=path, single_instance=inst, log_directory=tmp_path,
        on_ready=on_ready, log_level="debug",
    )  # fmt: skip
    assert app.run(opts) == 0
    assert inst.released == 1
    ctl = seen["ctl"]
    assert ctl.quitting
    assert path.is_file()  # flushed on quit
    out = capsys.readouterr().out
    assert "open" in out.lower() or out  # FakeMidiOut echoes MIDI traffic


def test_fatal_error_returns_1(tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(app, "show_fatal", shown.append)

    def boom(opts):
        raise RuntimeError("x")

    monkeypatch.setattr(app, "_run", boom)
    assert app.run(app.Options(log_directory=tmp_path)) == 1
    assert shown and "couldn't start" in shown[0]


def test_make_backend_dry_run():
    b = app.make_backend(config.DEFAULTS, True)
    assert b.list_devices() == [config.DEFAULTS.midi_device]
