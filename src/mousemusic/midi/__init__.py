"""MIDI output layer (ARCHITECTURE.md §1, §3, §5, §9, §11).

- :class:`MidiOut` is the swappable backend protocol (WinMM today, e.g. rtmidi later).
- Message builders produce the 3-byte short messages we need (note on/off, program change, CC).
- :class:`MidiOutput` wraps a backend with device selection (saved name → fallback to device 0),
  CC7 volume, the silence path, and device-loss detection from ``short_msg`` errors.

Nothing here imports Tk or touches Windows directly; ``midi.winmm`` is only imported on Windows.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)

#: The only channel we play on (§5). Channel 9 is GM drums and must never be used.
CHANNEL = 0
DRUM_CHANNEL = 9

NOTE_OFF = 0x80
NOTE_ON = 0x90
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
CC_VOLUME = 7
CC_ALL_NOTES_OFF = 123

DEFAULT_DEVICE = "Microsoft GS Wavetable Synth"


# --- errors -----------------------------------------------------------------------


class MidiError(Exception):
    """Base for MIDI failures. ``code`` is the backend error code (MMSYSERR_*), for the log."""

    def __init__(self, message: str, *, device: str | None = None, code: int | None = None):
        super().__init__(message)
        self.device = device
        self.code = code


class NoDevicesError(MidiError):
    """No MIDI outputs at all (UX E1)."""


class DeviceBusyError(MidiError):
    """Open failed because another app holds the device (UX E2, MMSYSERR_ALLOCATED)."""


class DeviceOpenError(MidiError):
    """Any other open failure (UX E3)."""


class DeviceLostError(MidiError):
    """``short_msg`` failed mid-play (UX E4, §11 UX-Q8/OQ-1)."""


# --- backend protocol ---------------------------------------------------------------


@runtime_checkable
class MidiOut(Protocol):
    """Backend protocol: list_devices / open / short_msg / reset / close (§3).

    ``short_msg`` and ``reset`` return the backend status code (0 = OK), so callers can detect
    device loss without exceptions on the hot path. ``open`` raises :class:`MidiError`.
    """

    def list_devices(self) -> list[str]: ...
    def open(self, index: int) -> None: ...
    def short_msg(self, status: int, data1: int = 0, data2: int = 0) -> int: ...
    def reset(self) -> int: ...
    def close(self) -> None: ...

    @property
    def is_open(self) -> bool: ...


# --- message builders -----------------------------------------------------------------


def _check(value: int, name: str, hi: int = 127) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= hi:
        raise ValueError(f"{name} out of range: {value!r}")
    return value


def _status(kind: int, channel: int) -> int:
    _check(channel, "channel", 15)
    if channel == DRUM_CHANNEL:
        raise ValueError("channel 9 is GM drums and is never used")
    return kind | channel


def note_on(note: int, velocity: int, channel: int = CHANNEL) -> tuple[int, int, int]:
    return _status(NOTE_ON, channel), _check(note, "note"), _check(velocity, "velocity")


def note_off(note: int, channel: int = CHANNEL) -> tuple[int, int, int]:
    return _status(NOTE_OFF, channel), _check(note, "note"), 0


def program_change(program: int, channel: int = CHANNEL) -> tuple[int, int, int]:
    return _status(PROGRAM_CHANGE, channel), _check(program, "program"), 0


def control_change(controller: int, value: int, channel: int = CHANNEL) -> tuple[int, int, int]:
    return (
        _status(CONTROL_CHANGE, channel),
        _check(controller, "controller"),
        _check(value, "value"),
    )


def volume_to_cc7(volume: int) -> int:
    """``volume`` 0-100 % → CC7 value, ``round(volume * 127 / 100)`` (§4, §11 UX-Q5)."""
    return round(min(max(volume, 0), 100) * 127 / 100)


def volume_cc(volume: int, channel: int = CHANNEL) -> tuple[int, int, int]:
    return control_change(CC_VOLUME, volume_to_cc7(volume), channel)


def all_notes_off(channel: int = CHANNEL) -> tuple[int, int, int]:
    return control_change(CC_ALL_NOTES_OFF, 0, channel)


def pack_short_msg(status: int, data1: int = 0, data2: int = 0) -> int:
    """WinMM ``midiOutShortMsg`` DWORD: status in the low byte, then data1, then data2."""
    return (status & 0xFF) | ((data1 & 0x7F) << 8) | ((data2 & 0x7F) << 16)


# --- device selection -----------------------------------------------------------------


@dataclass(frozen=True)
class DeviceChoice:
    index: int
    name: str
    #: True when the saved name wasn't found and device 0 was used (UX W1). The fallback name
    #: must never be written back to ``midi_device`` (§11 UX-Q4).
    fallback: bool


def choose_device(devices: Sequence[str], saved: str) -> DeviceChoice:
    """Pick the saved device by exact name, else device 0 (§9). Raises :class:`NoDevicesError`."""
    if not devices:
        raise NoDevicesError("no MIDI output devices")
    if saved in devices:
        i = list(devices).index(saved)
        return DeviceChoice(i, devices[i], fallback=False)
    log.warning("MIDI device %r not found; falling back to %r", saved, devices[0])
    return DeviceChoice(0, devices[0], fallback=True)


# --- high-level output ------------------------------------------------------------------


class MidiOutput:
    """One open device with the rules from §5/§9/§11. Single owner: the engine thread (§6)."""

    def __init__(self, backend: MidiOut) -> None:
        self.backend = backend
        self.device: DeviceChoice | None = None

    @property
    def is_open(self) -> bool:
        return self.device is not None and self.backend.is_open

    def list_devices(self) -> list[str]:
        """Re-enumerate (called on Start, Reconnect and dropdown open)."""
        return self.backend.list_devices()

    def open(self, saved_name: str, volume: int) -> DeviceChoice:
        """Re-enumerate, open the saved device (or fall back to 0), then send CC7 volume.

        Raises NoDevicesError (E1), DeviceBusyError (E2) or DeviceOpenError (E3).
        """
        self.close()
        choice = choose_device(self.list_devices(), saved_name)
        try:
            self.backend.open(choice.index)
        except MidiError as exc:
            exc.device = exc.device or choice.name
            log.warning("opening %r failed (code %s): %s", choice.name, exc.code, exc)
            raise
        self.device = choice
        self.set_volume(volume)
        return choice

    def send(self, status: int, data1: int = 0, data2: int = 0) -> None:
        """Send one short message. A non-zero result means the device is gone (§11 UX-Q8):
        silence what we can, close, and raise :class:`DeviceLostError` (E4)."""
        if self.device is None:
            raise DeviceLostError("MIDI output is not open")
        code = self.backend.short_msg(status, data1, data2)
        if code:
            name = self.device.name
            log.error("midiOutShortMsg failed on %r (code %s); stopping", name, code)
            self.close()
            raise DeviceLostError(f"lost connection to {name}", device=name, code=code)

    def set_volume(self, volume: int) -> None:
        """CC7 Channel Volume; on open, on Start and on every change (§11 UX-Q5)."""
        self.send(*volume_cc(volume))

    def silence(self, sounding_note: int | None = None) -> None:
        """Best-effort silence path (§5): note-off for the active note, CC123, then reset.

        Never raises; used on Stop, Quit, device change, device loss and exceptions."""
        if self.device is None or not self.backend.is_open:
            return
        msgs = [all_notes_off()]
        if sounding_note is not None:
            msgs.insert(0, note_off(sounding_note))
        for msg in msgs:
            try:
                self.backend.short_msg(*msg)
            except Exception:  # pragma: no cover - backend contract is return codes
                log.exception("silence: short_msg raised")
        try:
            self.backend.reset()
        except Exception:  # pragma: no cover
            log.exception("silence: reset raised")

    def close(self, sounding_note: int | None = None) -> None:
        """Silence and close. Safe to call repeatedly."""
        if self.device is None:
            return
        self.silence(sounding_note)
        try:
            self.backend.close()
        except Exception:
            log.exception("closing MIDI device failed")
        self.device = None


def default_backend() -> MidiOut:
    """WinMM on Windows. Elsewhere a fake backend with no devices (WinMM is Windows-only)."""
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
        from mousemusic.midi.winmm import WinMMBackend

        return WinMMBackend()
    from mousemusic.midi.fake import FakeMidiOut

    return FakeMidiOut(devices=[])
