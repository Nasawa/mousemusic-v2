"""Engine thread (ARCHITECTURE.md §6): poll the cursor at ``poll_hz``, map it to a cell, and
drive the scheduler. The engine is the single owner of the MIDI device; other threads talk to
it only through :meth:`Engine.post` (a thread-safe command queue drained every tick).

Platform pieces (cursor, screen metrics, timer period, MIDI backend) are injected, so the
engine runs with fakes on any OS. :meth:`Engine.step` performs one tick with an explicit time,
which is how the tests drive it with a fake clock.

Silence on every exit path: Stop, Quit, device change, suspend, device loss, unexpected
exceptions inside a tick, and :meth:`Engine.run` exiting for any reason (``finally``). The
process-level paths (``atexit``, SIGINT/SIGTERM/SIGBREAK) go through
:func:`install_exit_handlers`.
"""

from __future__ import annotations

import atexit
import logging
import queue
import signal
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from mousemusic.config import DEFAULTS, Settings
from mousemusic.mapping import (
    Cell,
    Grid,
    HysteresisMapper,
    Rect,
    TaskbarSound,
    TaskbarZone,
    ZoneCell,
    ZoneMapper,
    build_grid,
    build_taskbar_sound,
    cell_width_px,
    fixed_width_grid,
)
from mousemusic.midi import DeviceLostError, MidiError, MidiOut, MidiOutput
from mousemusic.scheduler import NoteParams, Scheduler

log = logging.getLogger(__name__)

#: Screen metrics are re-read this often while playing (§9 hot-plug).
METRICS_REFRESH_S = 2.0
#: Tick intervals kept for jitter statistics (60 s at 125 Hz, test-plan LT-02).
JITTER_WINDOW = 7500
#: How long :meth:`Engine.shutdown` waits for the thread (§6).
JOIN_TIMEOUT_S = 1.0


class CursorSource(Protocol):
    def position(self) -> tuple[int, int] | None: ...
    def virtual_rect(self) -> Rect | None: ...
    def primary_rect(self) -> Rect | None: ...


class TimerPeriodLike(Protocol):
    def begin(self) -> None: ...
    def end(self) -> None: ...


class _NoTimer:
    def begin(self) -> None:
        pass

    def end(self) -> None:
        pass


@dataclass(frozen=True)
class Event:
    """Status for the UI (drained by ``root.after(50, …)``, §6)."""

    kind: str  # started | stopped | note | error | warning
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Stats:
    ticks: int = 0
    max_tick_s: float = 0.0
    total_tick_s: float = 0.0
    cpu_s: float = 0.0
    wall_s: float = 0.0
    #: Recent tick-to-tick intervals in seconds (for the LT-02 jitter log).
    intervals: deque[float] = field(default_factory=lambda: deque(maxlen=JITTER_WINDOW))
    last_tick_at: float | None = None

    def record_tick(self, now: float) -> None:
        if self.last_tick_at is not None:
            self.intervals.append(now - self.last_tick_at)
        self.last_tick_at = now

    def jitter(self, period_s: float) -> tuple[float, float] | None:
        """``(p95, max)`` of ``|interval - period|`` in seconds, or None without data."""
        if not self.intervals:
            return None
        dev = sorted(abs(i - period_s) for i in self.intervals)
        return dev[min(len(dev) - 1, int(0.95 * len(dev)))], dev[-1]


# Commands -----------------------------------------------------------------------------
START, STOP, SET_SETTINGS, SET_DEVICE, SET_VOLUME = (
    "start",
    "stop",
    "set_settings",
    "set_device",
    "set_volume",
)
SUSPEND, RESUME, QUIT, DISPLAY_CHANGED = "suspend", "resume", "quit", "display_changed"
RECONNECT = "reconnect"
TASKBAR = "taskbar"  # value: taskbar.TaskbarSnapshot from the taskbar-scan thread (CG-S3)
TASKBAR_KEYS = ("scale", "root", "taskbar_low_note", "taskbar_high_note", "taskbar_program",
                "taskbar_secondary_programs")  # fmt: skip


class Engine:
    def __init__(
        self,
        backend: MidiOut,
        cursor: CursorSource,
        settings: Settings = DEFAULTS,
        *,
        emit: Callable[[Event], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        timer: TimerPeriodLike | None = None,
    ) -> None:
        self.output = MidiOutput(backend)
        self.cursor = cursor
        self.settings = settings
        self.emit = emit or (lambda e: None)
        self.clock = clock
        self.timer = timer or _NoTimer()
        self.commands: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self.scheduler = Scheduler(self.output, self._params(settings))
        self.grid: Grid = self._grid(settings)
        self.rect: Rect | None = None
        self.mapper: ZoneMapper | None = None
        self.zones: tuple[TaskbarZone, ...] = ()  # latest snapshot, swapped in atomically
        self.taskbar_sound = self._taskbar_sound(settings)
        self.cell: Cell | None = None
        self.playing = False
        self.was_playing_before_suspend = False
        self.quit_requested = False
        self.pending_volume: int | None = None
        self.metrics_at: float | None = None
        self.stats = Stats()
        self.thread: threading.Thread | None = None
        self._silenced = threading.Event()

    # -- helpers -----------------------------------------------------------------------

    @staticmethod
    def _params(s: Settings) -> NoteParams:
        return NoteParams(velocity=s.velocity, note_length_ms=s.note_length_ms, legato=s.legato)

    @staticmethod
    def _grid(s: Settings) -> Grid:
        return build_grid(s.scale, s.root, s.low_note, s.high_note, s.instrument_set)

    @staticmethod
    def _taskbar_sound(s: Settings) -> TaskbarSound:
        return build_taskbar_sound(s.scale, s.root, s.taskbar_low_note, s.taskbar_high_note,
                                   s.taskbar_program, s.taskbar_secondary_programs)  # fmt: skip

    def _desktop_grid(self, rect: Rect) -> Grid:
        """Phase 2 ``cell_width_dip`` (CG-S4): fixed-width columns, scaled by the cursor
        source's DPI scale (system DPI on Windows); 0 = one column per note (unchanged)."""
        dip = self.settings.cell_width_dip
        if not dip:
            return self.grid
        scale = getattr(self.cursor, "dpi_scale", lambda: 1.0)() or 1.0
        return fixed_width_grid(self.grid, rect.w, cell_width_px(dip, scale))

    def _active_zones(self) -> tuple[TaskbarZone, ...]:
        return self.zones if self.settings.taskbar_mode else ()

    @property
    def period_s(self) -> float:
        return 1.0 / self.settings.poll_hz

    def post(self, command: str, value: Any = None) -> None:
        """Thread-safe: queue a command for the engine thread."""
        self.commands.put((command, value))

    # -- command handling (engine thread) -------------------------------------------------

    def drain(self, now: float) -> None:
        while True:
            try:
                cmd, value = self.commands.get_nowait()
            except queue.Empty:
                return
            self.handle(cmd, value, now)

    def handle(self, cmd: str, value: Any, now: float) -> None:
        if cmd == START:
            self.was_playing_before_suspend = False  # an explicit choice overrides a stale wake
            self.start(now)
        elif cmd == STOP:
            self.was_playing_before_suspend = False
            self.stop()
        elif cmd == SET_SETTINGS:
            self.apply_settings(value, now)
        elif cmd == SET_DEVICE:
            self.apply_settings(self.settings.replace(midi_device=value), now)
            if self.playing:  # §5: silence, close, reopen
                self.stop(emit=False)
                self.start(now)
        elif cmd == SET_VOLUME:
            self.pending_volume = value  # A-5: coalesced, sent once per tick
            self.settings = self.settings.replace(volume=value)
        elif cmd == SUSPEND:
            # A repeated suspend (no resume in between) must not forget that we were playing.
            self.was_playing_before_suspend = self.was_playing_before_suspend or self.playing
            self.stop(emit=self.playing)
        elif cmd == RESUME:
            if self.was_playing_before_suspend:
                self.was_playing_before_suspend = False
                self.start(now, lost_on_failure=True)
        elif cmd == RECONNECT:  # UX ⟳: close and reopen the selected device
            if self.playing:
                self.stop(emit=False)
                self.start(now)
        elif cmd == TASKBAR:
            self.zones = tuple(value.zones)
            if self.mapper is not None:
                self.mapper.set_zones(self._active_zones())
                self.cell = None
        elif cmd == DISPLAY_CHANGED:
            self.metrics_at = None
        elif cmd == QUIT:
            self.quit_requested = True
            self.stop(emit=self.playing)
        else:
            log.warning("unknown engine command %r", cmd)

    def apply_settings(self, settings: Settings, now: float) -> None:
        old = self.settings
        self.settings = settings
        self.scheduler.set_params(self._params(settings), now)
        mapping_keys = ("scale", "root", "low_note", "high_note", "instrument_set", "screen_mode",
                        "cell_width_dip")  # fmt: skip
        if any(getattr(old, k) != getattr(settings, k) for k in mapping_keys):
            self.grid = self._grid(settings)
            self.metrics_at = None
            self.mapper = None
            self.cell = None
        if any(getattr(old, k) != getattr(settings, k) for k in TASKBAR_KEYS):
            self.taskbar_sound = self._taskbar_sound(settings)
            self.cell = None
        if old.taskbar_mode != settings.taskbar_mode and self.mapper is not None:
            self.mapper.set_zones(self._active_zones())  # live, no Stop needed (ux §12.1)
            self.cell = None
        if settings.volume != old.volume:
            self.pending_volume = settings.volume

    def start(self, now: float, *, lost_on_failure: bool = False) -> bool:
        if self.playing:
            return True
        try:
            choice = self.output.open(self.settings.midi_device, self.settings.volume)
        except MidiError as exc:
            if lost_on_failure:  # §11 OQ-3: resume reopen failure is shown as E4
                exc = DeviceLostError(str(exc), device=exc.device, code=exc.code)
            self.emit(Event("error", {"error": exc}))
            return False
        self.scheduler.reset_state()
        self.playing = True
        self.pending_volume = None  # open() already sent CC7
        self.cell = None
        self.mapper = None
        self.metrics_at = None
        self.timer.begin()
        if choice.fallback:
            self.emit(Event("warning", {"saved": self.settings.midi_device, "device": choice.name}))
        self.emit(Event("started", {"device": choice.name, "fallback": choice.fallback}))
        return True

    def stop(self, *, emit: bool = True) -> None:
        """Silence and close the device (§5 silence path). Safe to call when stopped."""
        if self.playing or self.output.is_open:
            note = self.scheduler.active_note
            self.scheduler.reset_state()
            self.output.close(sounding_note=note)  # note-off → CC123 → reset → close
        self.playing = False
        self.cell = None
        self.timer.end()
        if emit:
            self.emit(Event("stopped"))

    # -- the tick ------------------------------------------------------------------------

    def _refresh_metrics(self, now: float) -> None:
        if self.metrics_at is not None and now - self.metrics_at < METRICS_REFRESH_S:
            return
        self.metrics_at = now
        if self.settings.screen_mode == "primary":
            rect = self.cursor.primary_rect()
        else:
            rect = self.cursor.virtual_rect()
        if rect is None:
            return  # keep the last good rect
        if rect != self.rect or self.mapper is None:
            self.rect = rect
            self.mapper = ZoneMapper(HysteresisMapper(self._desktop_grid(rect), rect),
                                     self._active_zones())  # fmt: skip
            self.cell = None

    def step(self, now: float) -> None:
        """One engine tick at time ``now`` (seconds on the engine clock)."""
        self.drain(now)
        if not self.playing:
            return
        t0 = time.perf_counter()
        try:
            self._tick(now)
        except DeviceLostError as exc:
            self._device_lost(exc)
        except Exception as exc:
            log.exception("engine tick failed; stopping")
            self._safe_stop()
            self.emit(Event("error", {"error": exc}))
        finally:
            dt = time.perf_counter() - t0
            self.stats.ticks += 1
            self.stats.total_tick_s += dt
            self.stats.max_tick_s = max(self.stats.max_tick_s, dt)

    def _tick(self, now: float) -> None:
        if self.pending_volume is not None:
            volume, self.pending_volume = self.pending_volume, None
            self.output.set_volume(volume)
        self._refresh_metrics(now)
        pos = self.cursor.position()
        if pos is not None and self.mapper is not None:
            cell = self.mapper.update(*pos)
            if cell != self.cell:  # a new note only on cell change (§5)
                self.cell = cell
                if isinstance(cell, ZoneCell):
                    self._zone_note(cell, now)
                else:
                    grid = self.mapper.desktop.grid
                    note, program = grid.sound(cell)
                    factor = grid.factor(cell)
                    velocity = (
                        None if factor == 1.0 else max(1, round(self.settings.velocity * factor))
                    )
                    self.scheduler.request(note, program, now, velocity)
                    self.emit(Event("note", {"note": note, "program": program}))
        self.scheduler.tick(now)

    def _zone_note(self, cell: ZoneCell, now: float) -> None:
        """Taskbar cell (design §4.3): the zone's program, sent before the note-on by the
        scheduler; wrapped notes softer. A silent cell (offset, gap) plays nothing."""
        sound = self.taskbar_sound.sound(cell)
        if sound is None:
            self.emit(Event("note", {"note": None, "program": None, "zone": cell}))
            return
        note, program, factor = sound
        velocity = max(1, round(self.settings.velocity * factor)) if factor != 1.0 else None
        self.scheduler.request(note, program, now, velocity)
        self.emit(Event("note", {"note": note, "program": program, "zone": cell}))

    def _device_lost(self, exc: DeviceLostError) -> None:
        # MidiOutput already silenced (best effort) and closed; no retry, no polling (OQ-1).
        self.scheduler.reset_state()
        self.playing = False
        self.cell = None
        self.timer.end()
        self.emit(Event("error", {"error": exc}))

    def _safe_stop(self) -> None:
        try:
            self.stop(emit=False)
        except Exception:
            log.exception("silence path failed")
            self.playing = False
            self.timer.end()

    # -- thread loop ---------------------------------------------------------------------

    def next_wakeup(self, now: float, next_tick: float) -> float | None:
        """Seconds to block waiting for commands. None = block until a command (stopped)."""
        if not self.playing:
            return None
        return max(0.0, next_tick - now)

    def run(self) -> None:
        """Engine thread body: perf_counter deadlines, blocking waits, no busy-spin (§6)."""
        cpu0, wall0 = time.thread_time(), time.perf_counter()
        next_tick = self.clock()
        try:
            while not self.quit_requested:
                now = self.clock()
                timeout = self.next_wakeup(now, next_tick)
                try:
                    cmd, value = self.commands.get(timeout=timeout)
                    self.handle(cmd, value, self.clock())
                except queue.Empty:
                    pass
                if self.quit_requested:
                    break
                now = self.clock()
                if not self.playing:
                    next_tick = now
                    self.stats.last_tick_at = None
                    continue
                if now >= next_tick:
                    self.stats.record_tick(now)
                    self.step(now)
                    next_tick += self.period_s
                    if next_tick <= now:  # fell behind (e.g. suspended): don't burst
                        next_tick = now + self.period_s
        finally:
            self._safe_stop()
            self._silenced.set()
            self.stats.cpu_s = time.thread_time() - cpu0
            self.stats.wall_s = time.perf_counter() - wall0

    def start_thread(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.run, name="mousemusic-engine", daemon=True)
        self.thread.start()
        return self.thread

    def shutdown(self, timeout: float = JOIN_TIMEOUT_S) -> None:
        """Post quit and join (§6). If the thread doesn't finish in time (or never ran),
        silence directly as a last resort so no note is left sounding."""
        self.post(QUIT)
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout)
        if not self._silenced.is_set() and (self.thread is None or not self.thread.is_alive()):
            self._safe_stop()
            self._silenced.set()
        elif not self._silenced.is_set():
            log.error("engine did not stop within %.1f s; forcing silence", timeout)
            self._safe_stop()


def install_exit_handlers(
    engine: Engine,
    *,
    register: Callable[[Callable[[], None]], Any] = atexit.register,
    set_signal: Callable[[int, Any], Any] | None = None,
    on_signal: Callable[[], None] | None = None,
) -> list[int]:
    """Silence on normal interpreter exit (atexit) and on SIGINT/SIGTERM/SIGBREAK (Ctrl+C,
    Ctrl+Break, console close). Signal handlers run on the main thread, so call this from it.
    Returns the signal numbers that were hooked."""
    register(engine.shutdown)
    set_signal = set_signal or signal.signal

    def handler(signum: int, frame: Any) -> None:
        log.info("signal %s: silencing and quitting", signum)
        engine.shutdown()
        if on_signal is not None:
            on_signal()
        else:
            raise KeyboardInterrupt

    hooked = []
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        num = getattr(signal, name, None)
        if num is None:
            continue
        try:
            set_signal(num, handler)
            hooked.append(num)
        except (ValueError, OSError):  # not main thread, or unsupported
            log.debug("cannot hook %s", name)
    return hooked
