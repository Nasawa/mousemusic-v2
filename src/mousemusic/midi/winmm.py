"""WinMM MIDI output via ``ctypes`` (§1): midiOutGetNumDevs, midiOutGetDevCapsW, midiOutOpen,
midiOutShortMsg, midiOutReset, midiOutClose. Zero dependencies.

Importable on any OS (so it can be unit-tested with a fake ``winmm`` object); only
:func:`load_winmm` needs Windows.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Any

from mousemusic.midi import DeviceBusyError, DeviceOpenError, MidiError, pack_short_msg

log = logging.getLogger(__name__)

MMSYSERR_NOERROR = 0
MMSYSERR_ERROR = 1
MMSYSERR_BADDEVICEID = 2
MMSYSERR_NOTENABLED = 3
MMSYSERR_ALLOCATED = 4
MMSYSERR_INVALHANDLE = 5
MMSYSERR_NODRIVER = 6
MMSYSERR_NOMEM = 7
MIDIERR_NOTREADY = 67
MIDIERR_NODEVICE = 68

ERROR_NAMES = {
    MMSYSERR_ERROR: "MMSYSERR_ERROR",
    MMSYSERR_BADDEVICEID: "MMSYSERR_BADDEVICEID",
    MMSYSERR_NOTENABLED: "MMSYSERR_NOTENABLED",
    MMSYSERR_ALLOCATED: "MMSYSERR_ALLOCATED",
    MMSYSERR_INVALHANDLE: "MMSYSERR_INVALHANDLE",
    MMSYSERR_NODRIVER: "MMSYSERR_NODRIVER",
    MMSYSERR_NOMEM: "MMSYSERR_NOMEM",
    MIDIERR_NOTREADY: "MIDIERR_NOTREADY",
    MIDIERR_NODEVICE: "MIDIERR_NODEVICE",
}

CALLBACK_NULL = 0
MAXPNAMELEN = 32
HMIDIOUT = wintypes.HANDLE


class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("wTechnology", wintypes.WORD),
        ("wVoices", wintypes.WORD),
        ("wNotes", wintypes.WORD),
        ("wChannelMask", wintypes.WORD),
        ("dwSupport", wintypes.DWORD),
    ]


def error_name(code: int) -> str:
    return ERROR_NAMES.get(code, f"MMRESULT {code}")


def load_winmm() -> Any:  # pragma: no cover - Windows only
    """Load ``winmm.dll`` and declare signatures (64-bit safe: handles and UINT_PTR ids)."""
    if sys.platform != "win32":
        raise OSError("WinMM is only available on Windows")
    lib = ctypes.WinDLL("winmm")
    mmresult = wintypes.UINT
    lib.midiOutGetNumDevs.argtypes = []
    lib.midiOutGetNumDevs.restype = wintypes.UINT
    lib.midiOutGetDevCapsW.argtypes = [ctypes.c_size_t, ctypes.POINTER(MIDIOUTCAPSW), wintypes.UINT]
    lib.midiOutGetDevCapsW.restype = mmresult
    lib.midiOutOpen.argtypes = [
        ctypes.POINTER(HMIDIOUT),
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_size_t,
        wintypes.DWORD,
    ]
    lib.midiOutOpen.restype = mmresult
    lib.midiOutShortMsg.argtypes = [HMIDIOUT, wintypes.DWORD]
    lib.midiOutShortMsg.restype = mmresult
    lib.midiOutReset.argtypes = [HMIDIOUT]
    lib.midiOutReset.restype = mmresult
    lib.midiOutClose.argtypes = [HMIDIOUT]
    lib.midiOutClose.restype = mmresult
    return lib


class WinMMBackend:
    """:class:`~mousemusic.midi.MidiOut` over WinMM. ``lib`` is injectable for tests."""

    def __init__(self, lib: Any = None) -> None:
        self._lib = lib if lib is not None else load_winmm()
        self._handle: HMIDIOUT | None = None
        self._names: list[str] = []

    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def list_devices(self) -> list[str]:
        names = []
        for i in range(self._lib.midiOutGetNumDevs()):
            caps = MIDIOUTCAPSW()
            code = self._lib.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
            if code:
                log.warning("midiOutGetDevCapsW(%d) failed: %s", i, error_name(code))
                names.append(f"MIDI output {i}")
            else:
                names.append(caps.szPname)
        self._names = names
        return list(names)

    def _name(self, index: int) -> str:
        return self._names[index] if 0 <= index < len(self._names) else f"MIDI output {index}"

    def open(self, index: int) -> None:
        if self._handle is not None:
            raise DeviceOpenError("a device is already open", code=MMSYSERR_ERROR)
        handle = HMIDIOUT()
        code = self._lib.midiOutOpen(ctypes.byref(handle), index, 0, 0, CALLBACK_NULL)
        name = self._name(index)
        if code == MMSYSERR_ALLOCATED:
            raise DeviceBusyError(f"{name}: {error_name(code)}", device=name, code=code)
        if code:
            raise DeviceOpenError(f"{name}: {error_name(code)}", device=name, code=code)
        self._handle = handle

    def short_msg(self, status: int, data1: int = 0, data2: int = 0) -> int:
        if self._handle is None:
            return MMSYSERR_INVALHANDLE
        return int(self._lib.midiOutShortMsg(self._handle, pack_short_msg(status, data1, data2)))

    def reset(self) -> int:
        if self._handle is None:
            return MMSYSERR_INVALHANDLE
        return int(self._lib.midiOutReset(self._handle))

    def close(self) -> None:
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        code = self._lib.midiOutClose(handle)
        if code:
            log.warning("midiOutClose failed: %s", error_name(code))


__all__ = ["MIDIOUTCAPSW", "MidiError", "WinMMBackend", "error_name", "load_winmm"]
