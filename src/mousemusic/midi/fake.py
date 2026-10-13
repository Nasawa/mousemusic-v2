"""Fake MIDI backend: records messages. Used by tests and ``--dry-run`` (§3)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from mousemusic.midi import DeviceBusyError, DeviceOpenError

MMSYSERR_ALLOCATED = 4


class FakeMidiOut:
    """In-memory :class:`~mousemusic.midi.MidiOut`.

    ``open_errors`` maps a device index to an error code to raise on open (4 = busy → E2,
    anything else → E3). ``fail_after`` makes ``short_msg`` return ``fail_code`` once that many
    messages have been sent, to simulate a device lost mid-play (E4). ``echo`` receives a line
    per message (``--dry-run`` prints them).
    """

    def __init__(
        self,
        devices: Iterable[str] = ("Microsoft GS Wavetable Synth",),
        *,
        open_errors: dict[int, int] | None = None,
        fail_after: int | None = None,
        fail_code: int = 6,
        echo: Callable[[str], None] | None = None,
    ) -> None:
        self.devices = list(devices)
        self.open_errors = dict(open_errors or {})
        self.fail_after = fail_after
        self.fail_code = fail_code
        self.echo = echo
        self.messages: list[tuple[int, int, int]] = []
        self.log: list[str] = []
        self.opened: int | None = None
        self.enumerations = 0

    @property
    def is_open(self) -> bool:
        return self.opened is not None

    def _record(self, line: str) -> None:
        self.log.append(line)
        if self.echo:
            self.echo(line)

    def list_devices(self) -> list[str]:
        self.enumerations += 1
        return list(self.devices)

    def open(self, index: int) -> None:
        if self.opened is not None:
            raise DeviceOpenError("already open", code=1)
        if not 0 <= index < len(self.devices):
            raise DeviceOpenError(f"bad device id {index}", code=2)
        code = self.open_errors.get(index)
        name = self.devices[index]
        if code == MMSYSERR_ALLOCATED:
            raise DeviceBusyError(f"{name} is busy", device=name, code=code)
        if code:
            raise DeviceOpenError(f"cannot open {name}", device=name, code=code)
        self.opened = index
        self._record(f"open {index}: {name}")

    def short_msg(self, status: int, data1: int = 0, data2: int = 0) -> int:
        if self.opened is None:
            return 5  # MMSYSERR_INVALHANDLE
        if self.fail_after is not None and len(self.messages) >= self.fail_after:
            return self.fail_code
        self.messages.append((status, data1, data2))
        self._record(f"msg {status:02X} {data1:02X} {data2:02X}")
        return 0

    def reset(self) -> int:
        if self.opened is None:
            return 5
        self._record("reset")
        return 0

    def close(self) -> None:
        if self.opened is not None:
            self._record("close")
        self.opened = None
