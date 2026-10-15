import threading

import pytest

from mousemusic import preview as pv
from mousemusic.midi import DeviceBusyError, MidiOutput, NoDevicesError
from mousemusic.midi.fake import FakeMidiOut


@pytest.mark.parametrize(("text", "want"), [("0", 0), (" 127 ", 127), ("40", 40), (7, 7)])
def test_parse_program(text, want):
    assert pv.parse_program(text) == want


@pytest.mark.parametrize("text", ["-1", "128", "x", "", "4.5", None])
def test_parse_program_invalid(text):
    with pytest.raises(pv.InvalidProgram):
        pv.parse_program(text)


def test_play_once_scale_then_silent_and_closed():
    be = FakeMidiOut(["A", "B"])
    waits = []
    got = pv.play_once(be, "B", 80, 40, lambda s: waits.append(s) and False)
    assert got == "B" and be.opened is None
    assert be.messages[:2] == [(0xB0, 7, 102), (0xC0, 40, 0)]
    ons = [m[1] for m in be.messages if m[0] == 0x90]
    offs = [m[1] for m in be.messages if m[0] == 0x80]
    assert ons == offs == list(pv.SCALE) and waits == [pv.NOTE_S] * len(pv.SCALE)
    assert (0xB0, 123, 0) in be.messages  # silenced on close
    assert "close" in be.log


def test_play_scale_cancel_turns_note_off():
    be = FakeMidiOut()
    out = MidiOutput(be)
    out.open("x", 50)
    assert pv.play_scale(out, 0, lambda s: True) is False
    assert be.messages[-2:] == [(0x90, 60, 100), (0x80, 60, 0)]


def test_play_once_errors_close_device():
    with pytest.raises(NoDevicesError):
        pv.play_once(FakeMidiOut([]), "x", 50, 0, lambda s: False)
    with pytest.raises(DeviceBusyError):
        pv.play_once(FakeMidiOut(open_errors={0: 4}), "x", 50, 0, lambda s: False)


def test_previewer_runs_once_and_reports():
    done = []
    finished = threading.Event()
    p = pv.Previewer(FakeMidiOut, lambda e: (done.append(e), finished.set()))
    assert not p.active
    gate = threading.Event()
    real = pv.play_once

    def slow(*a):
        gate.wait(2)
        return real(*a[:4], lambda s: False)

    pv.play_once, saved = slow, pv.play_once
    try:
        assert p.start("x", 50, 1)
        assert p.active and not p.start("x", 50, 1)  # one at a time
        gate.set()
        assert finished.wait(2)
    finally:
        pv.play_once = saved
    assert done == [None]
    p.cancel()
    assert not p.active


def test_previewer_error_and_cancel():
    errs = []
    ev = threading.Event()
    p = pv.Previewer(lambda: FakeMidiOut([]), lambda e: (errs.append(e), ev.set()))
    p.start("x", 50, 1)
    assert ev.wait(2) and isinstance(errs[0], NoDevicesError)

    boom = []
    ev2 = threading.Event()

    def bad():
        raise RuntimeError("x")

    p2 = pv.Previewer(bad, lambda e: (boom.append(e), ev2.set()))
    p2.start("x", 50, 1)
    assert ev2.wait(2) and isinstance(boom[0], RuntimeError)

    called = []
    p3 = pv.Previewer(FakeMidiOut, called.append)
    p3.start("x", 50, 1)  # 8 x 0.18 s; cancel stops at the first wait
    p3.cancel()
    assert not p3.active and called == []
    p3.cancel()  # idempotent
