"""WinMM backend against a fake ``winmm`` library (runs on any OS)."""

import ctypes
import sys

import pytest

from mousemusic.midi import DeviceBusyError, DeviceOpenError, MidiOut, MidiOutput, note_on, winmm
from mousemusic.midi.winmm import MIDIOUTCAPSW, WinMMBackend, error_name


class FakeWinmm:
    def __init__(self, names=("Microsoft GS Wavetable Synth",), caps_fail=(), open_code=0):
        self.names = list(names)
        self.caps_fail = set(caps_fail)
        self.open_code = open_code
        self.send_code = 0
        self.calls = []

    def midiOutGetNumDevs(self):
        return len(self.names)

    def midiOutGetDevCapsW(self, i, pcaps, size):
        assert size == ctypes.sizeof(MIDIOUTCAPSW)
        if i in self.caps_fail:
            return winmm.MMSYSERR_NODRIVER
        pcaps._obj.szPname = self.names[i]
        return 0

    def midiOutOpen(self, phandle, index, cb, inst, flags):
        self.calls.append(("open", index, cb, inst, flags))
        if self.open_code:
            return self.open_code
        phandle._obj.value = 0x1234
        return 0

    def midiOutShortMsg(self, handle, msg):
        self.calls.append(("msg", handle.value, msg))
        return self.send_code

    def midiOutReset(self, handle):
        self.calls.append(("reset", handle.value))
        return 0

    def midiOutClose(self, handle):
        self.calls.append(("close", handle.value))
        return self.close_code if hasattr(self, "close_code") else 0


def test_caps_struct_layout():
    names = [f[0] for f in MIDIOUTCAPSW._fields_]
    assert names == [
        "wMid", "wPid", "vDriverVersion", "szPname", "wTechnology",
        "wVoices", "wNotes", "wChannelMask", "dwSupport",
    ]  # fmt: skip
    assert MIDIOUTCAPSW.szPname.offset == 8
    assert MIDIOUTCAPSW.wTechnology.offset == 8 + 32 * ctypes.sizeof(ctypes.c_wchar)
    if sys.platform == "win32":  # WCHAR = 2 bytes and DWORD = 4 bytes only on Windows
        assert ctypes.sizeof(MIDIOUTCAPSW) == 84


def test_protocol():
    assert isinstance(WinMMBackend(FakeWinmm()), MidiOut)


def test_list_devices_and_caps_failure(caplog):
    b = WinMMBackend(FakeWinmm(["A", "B", "C"], caps_fail={1}))
    assert b.list_devices() == ["A", "MIDI output 1", "C"]
    assert "MMSYSERR_NODRIVER" in caplog.text


def test_open_send_reset_close():
    lib = FakeWinmm()
    b = WinMMBackend(lib)
    b.list_devices()
    b.open(0)
    assert b.is_open
    assert lib.calls[0] == ("open", 0, 0, 0, winmm.CALLBACK_NULL)
    assert b.short_msg(0x90, 60, 100) == 0
    assert lib.calls[-1] == ("msg", 0x1234, 0x90 | 60 << 8 | 100 << 16)
    assert b.reset() == 0
    b.close()
    assert lib.calls[-2:] == [("reset", 0x1234), ("close", 0x1234)]
    assert not b.is_open
    b.close()  # no second midiOutClose
    assert lib.calls.count(("close", 0x1234)) == 1


def test_closed_handle_codes():
    b = WinMMBackend(FakeWinmm())
    assert b.short_msg(0x90, 1, 1) == winmm.MMSYSERR_INVALHANDLE
    assert b.reset() == winmm.MMSYSERR_INVALHANDLE


def test_open_busy_maps_to_e2():
    b = WinMMBackend(FakeWinmm(open_code=winmm.MMSYSERR_ALLOCATED))
    b.list_devices()
    with pytest.raises(DeviceBusyError) as exc:
        b.open(0)
    assert exc.value.code == 4 and exc.value.device == "Microsoft GS Wavetable Synth"
    assert not b.is_open


@pytest.mark.parametrize(
    "code",
    [winmm.MMSYSERR_BADDEVICEID, winmm.MMSYSERR_NODRIVER, winmm.MMSYSERR_NOMEM, 999],
)
def test_open_other_errors_map_to_e3(code):
    b = WinMMBackend(FakeWinmm(open_code=code))
    with pytest.raises(DeviceOpenError) as exc:
        b.open(5)  # not enumerated: generic name
    assert exc.value.code == code and exc.value.device == "MIDI output 5"


def test_double_open_rejected():
    b = WinMMBackend(FakeWinmm())
    b.open(0)
    with pytest.raises(DeviceOpenError):
        b.open(0)


def test_close_error_logged(caplog):
    lib = FakeWinmm()
    lib.close_code = winmm.MMSYSERR_INVALHANDLE
    b = WinMMBackend(lib)
    b.open(0)
    b.close()
    assert "MMSYSERR_INVALHANDLE" in caplog.text and not b.is_open


def test_device_loss_through_midioutput():
    lib = FakeWinmm()
    out = MidiOutput(WinMMBackend(lib))
    out.open("Microsoft GS Wavetable Synth", 80)
    lib.send_code = winmm.MIDIERR_NODEVICE
    with pytest.raises(Exception) as exc:
        out.send(*note_on(60, 100))
    assert type(exc.value).__name__ == "DeviceLostError" and exc.value.code == 68
    assert ("close", 0x1234) in lib.calls


def test_error_names():
    assert error_name(4) == "MMSYSERR_ALLOCATED"
    assert error_name(68) == "MIDIERR_NODEVICE"
    assert error_name(12345) == "MMRESULT 12345"


def test_load_winmm_off_windows(monkeypatch):
    monkeypatch.setattr(winmm.sys, "platform", "linux")
    with pytest.raises(OSError):
        winmm.load_winmm()
