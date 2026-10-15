"""Note timing (ARCHITECTURE.md §5 "Note triggering and note-off"). PURE: the clock and MIDI
output are injected; nothing here imports platform/, midi.winmm or ui/.

Rules:
- Monophonic on channel 0. A new cell sends note-off for the sounding note, then note-on.
- Program change only when the row (program) changes, and always *before* the next note-on.
  A row change alone re-triggers the same pitch on the new instrument.
- Note-off at ``now + note_length_ms`` unless legato (then held until the next note or silence).
- Rate limit: at most one note-on per 30 ms. Requests inside the window replace each other
  (latest wins, never a queue) and the survivor plays as soon as the window ends.
- Errors from the output (device loss) propagate; the scheduler forgets its state first so the
  caller's silence path never resends to a dead device.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mousemusic.midi import note_off, note_on, program_change

#: Minimum spacing between note-ons, seconds (§5: ≈ 33 notes/s).
RATE_LIMIT_S = 0.030


class Output(Protocol):
    """The subset of :class:`mousemusic.midi.MidiOutput` the scheduler needs."""

    def send(self, status: int, data1: int = 0, data2: int = 0) -> None: ...
    def silence(self, sounding_note: int | None = None) -> None: ...


@dataclass(frozen=True)
class NoteParams:
    velocity: int = 100
    note_length_ms: int = 250
    legato: bool = False


class Scheduler:
    def __init__(self, output: Output, params: NoteParams | None = None) -> None:
        self.output = output
        self.params = params or NoteParams()
        self.active_note: int | None = None
        self.program: int | None = None
        self.off_at: float | None = None
        self.last_on: float | None = None
        self.pending: tuple[int, int, int | None] | None = None
        self.note_ons = 0

    # -- configuration ----------------------------------------------------------

    def set_params(self, params: NoteParams, now: float) -> None:
        """Apply new velocity/length/legato. Turning legato off schedules the held note's
        note-off from now; turning it on keeps the sounding note held."""
        was_legato = self.params.legato
        self.params = params
        if self.active_note is None:
            return
        if params.legato:
            self.off_at = None
        elif was_legato:
            self.off_at = now + params.note_length_ms / 1000

    # -- events -----------------------------------------------------------------

    def request(self, note: int, program: int, now: float, velocity: int | None = None) -> bool:
        """The cursor entered a new cell. Plays now if the rate limit allows, else stores it
        as the pending (latest-wins) request. Returns True if a note-on was sent.
        ``velocity`` overrides the setting for this note (taskbar wrap, design §4.3)."""
        self.pending = (note, program, velocity)
        return self._flush(now)

    def tick(self, now: float) -> None:
        """Called every engine tick: due note-off, then any pending note whose window ended."""
        if self.off_at is not None and now >= self.off_at and self.active_note is not None:
            note, self.active_note, self.off_at = self.active_note, None, None
            self._send(*note_off(note))
        self._flush(now)

    def next_deadline(self) -> float | None:
        """Earliest time the scheduler needs a tick (note-off or end of the rate window)."""
        times = []
        if self.off_at is not None:
            times.append(self.off_at)
        if self.pending is not None and self.last_on is not None:
            times.append(self.last_on + RATE_LIMIT_S)
        return min(times) if times else None

    def silence(self) -> None:
        """§5 silence path: note-off (active) → CC123 → reset. Forgets all state."""
        note = self.active_note
        self.reset_state()
        self.output.silence(note)

    def reset_state(self) -> None:
        """Forget everything without sending (device already gone or reopened)."""
        self.active_note = None
        self.program = None
        self.off_at = None
        self.last_on = None
        self.pending = None

    # -- internals --------------------------------------------------------------

    def _send(self, status: int, data1: int, data2: int) -> None:
        try:
            self.output.send(status, data1, data2)
        except Exception:
            self.reset_state()
            raise

    def _flush(self, now: float) -> bool:
        if self.pending is None:
            return False
        if self.last_on is not None and now - self.last_on < RATE_LIMIT_S:
            return False
        note, program, velocity = self.pending
        self.pending = None
        if self.active_note is not None:
            old, self.active_note = self.active_note, None
            self._send(*note_off(old))
        if program != self.program:
            self._send(*program_change(program))
            self.program = program
        self._send(*note_on(note, velocity or self.params.velocity))
        self.active_note = note
        self.last_on = now
        self.note_ons += 1
        self.off_at = None if self.params.legato else now + self.params.note_length_ms / 1000
        return True
