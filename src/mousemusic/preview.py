"""Instrument preview: a short scale on one GM program.

Used by ``--play-instrument <program>`` (blocking, CLI) and by the window's Preview button
(:class:`Previewer`, a cancellable background thread). Both reuse :class:`MidiOutput`, so
the open/volume/silence rules (§5, §9) are the same as in normal play.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from mousemusic.midi import MidiError, MidiOut, MidiOutput, note_off, note_on, program_change

log = logging.getLogger(__name__)

#: C major, C4 up to C5: eight notes, about 1.5 s at the default length.
SCALE = (60, 62, 64, 65, 67, 69, 71, 72)
NOTE_S = 0.18
VELOCITY = 100


class InvalidProgram(ValueError):
    pass


def parse_program(text: object) -> int:
    """GM program number 0-127 (as the MIDI program change carries it)."""
    try:
        value = int(str(text).strip(), 10)
    except ValueError:
        raise InvalidProgram(f"{text!r} is not a number") from None
    if not 0 <= value <= 127:
        raise InvalidProgram(f"{value} is outside 0-127")
    return value


def play_scale(
    output: MidiOutput,
    program: int,
    wait: Callable[[float], bool],
    *,
    velocity: int = VELOCITY,
    note_s: float = NOTE_S,
) -> bool:
    """Play :data:`SCALE` on ``program`` through an open ``output``. ``wait(seconds)``
    returns True to cancel. Returns False if cancelled. The caller closes ``output``,
    which silences it (§5)."""
    output.send(*program_change(program))
    for note in SCALE:
        output.send(*note_on(note, velocity))
        cancelled = wait(note_s)
        output.send(*note_off(note))
        if cancelled:
            return False
    return True


def play_once(
    backend: MidiOut,
    device: str,
    volume: int,
    program: int,
    wait: Callable[[float], bool],
) -> str:
    """Open ``device`` (or the fallback, §9), play the scale, close. Returns the device name
    actually used. Raises :class:`MidiError` subclasses (E1-E4)."""
    output = MidiOutput(backend)
    try:
        choice = output.open(device, volume)
        play_scale(output, program, wait)
        return choice.name
    finally:
        output.close()


class Previewer:
    """One preview at a time on a daemon thread; :meth:`cancel` stops it within one wait.

    ``on_done(error_or_None)`` is called from the preview thread when it ends (not when
    cancelled); the app posts it to the UI queue."""

    def __init__(
        self,
        backend_factory: Callable[[], MidiOut],
        on_done: Callable[[Exception | None], None],
    ) -> None:
        self.backend_factory = backend_factory
        self.on_done = on_done
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, device: str, volume: int, program: int) -> bool:
        if self.active:
            return False
        self._stop = stop = threading.Event()

        def run() -> None:
            error: Exception | None = None
            try:
                play_once(self.backend_factory(), device, volume, program, stop.wait)
            except MidiError as exc:
                error = exc
            except Exception as exc:  # never kill the app from a preview
                log.exception("preview failed")
                error = exc
            if not stop.is_set():
                self.on_done(error)

        self._thread = threading.Thread(target=run, name="preview", daemon=True)
        self._thread.start()
        return True

    def cancel(self, timeout: float = 1.0) -> None:
        """Stop and wait, so the device is closed before the engine opens it (Start)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
