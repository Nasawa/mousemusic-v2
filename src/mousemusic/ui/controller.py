"""App controller: the testable logic behind the window and tray (docs/ux.md §1-§4).

Runs on the Tk main thread only. Other threads (engine events, tray, hotkey window, settings
saver) hand work to it through :meth:`AppController.dispatch`, fed from a queue that the window
drains every 50 ms (§6). The view (Tk window + tray) is a thin layer that reads the option
lists and :attr:`status` from here and calls the action methods.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from mousemusic import engine as eng
from mousemusic.config import LoadResult, Settings
from mousemusic.instruments import INSTRUMENT_SETS, load_scale_order, program_name
from mousemusic.midi import DeviceLostError, NoDevicesError
from mousemusic.scales import NOTE_NAMES, SCALE_LABELS
from mousemusic.ui import strings
from mousemusic.ui.status import WARNING_SECONDS, StatusModel, display_note

log = logging.getLogger(__name__)

#: Octave Cs offered in the pitch-range boxes: C0 (12) … C8 (108) (§11 UX-Q6).
OCTAVE_NOTES = tuple(range(12, 109, 12))
OCTAVE = 12
NOTE_LENGTH_STEP = 10


class EnginePort(Protocol):
    def post(self, command: str, value: Any = None) -> None: ...
    def shutdown(self, timeout: float = ...) -> None: ...


class SaverPort(Protocol):
    def request(self, settings: Settings) -> None: ...
    def flush(self) -> bool: ...


class View(Protocol):
    def refresh(self) -> None: ...
    def show_window(self) -> None: ...
    def hide_window(self) -> None: ...
    def notify(self, title: str, text: str) -> None: ...
    def quit_app(self) -> None: ...


@dataclass(frozen=True)
class Option:
    value: Any
    label: str


class AppController:
    def __init__(
        self,
        settings: Settings,
        engine: EnginePort,
        saver: SaverPort,
        list_devices: Callable[[], list[str]],
        clock: Callable[[], float],
        *,
        hotkey_ok: bool = True,
        first_run: bool = False,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.saver = saver
        self._list_devices = list_devices
        self.clock = clock
        self.view: View | None = None
        self.hidden = False
        self.devices: list[str] = []
        self.selected_device: str | None = None
        self.w5_shown = False
        self.quitting = False
        self.status = StatusModel(
            hotkey=settings.hotkey,
            hotkey_ok=hotkey_ok,
            first_run=first_run or not settings.first_run_done,
            root=settings.root,
        )
        self.scale_order = load_scale_order()

    # -- startup -----------------------------------------------------------------------

    def startup(self, load: LoadResult | None = None) -> None:
        now = self.clock()
        if load is not None and load.corrupt:
            self.status.add_warning(
                "W2", strings.W2_SETTINGS_RESET, now, help_anchor=strings.W2_HELP,
                duration=WARNING_SECONDS, until_start=True,
            )  # fmt: skip
        elif load is not None and load.issues:
            self.status.add_warning(
                "W3", strings.W3_SETTINGS_CLAMPED, now, duration=WARNING_SECONDS, until_start=True
            )
        if not self.status.hotkey_ok:
            self.status.add_warning(
                "W4", strings.W4_HOTKEY_OFF.format(hotkey=self.settings.hotkey), now,
                duration=WARNING_SECONDS,
            )  # fmt: skip
        self.refresh_devices()
        if self.settings.start_on_launch and self.can_start:
            self.toggle()

    # -- devices -----------------------------------------------------------------------

    def refresh_devices(self) -> list[str]:
        """Re-enumerate (dropdown open, ⟳, startup). Updates E1/W1 (§9, docs/ux.md §4)."""
        try:
            self.devices = list(self._list_devices())
        except Exception:
            log.exception("enumerating MIDI devices failed")
            self.devices = []
        saved = self.settings.midi_device
        if not self.devices:
            self.selected_device = None
            self.status.clear_warning("W1")
            self.status.set_error("E1", strings.E1_NO_DEVICE, strings.E1_HELP)
        else:
            self.status.clear_error("E1")
            if saved in self.devices:
                self.selected_device = saved
                self.status.clear_warning("W1")
            else:
                self.selected_device = self.devices[0]
                if not self.status.playing:
                    self._warn_fallback(saved, self.devices[0])
        self._changed()
        return self.devices

    def _warn_fallback(self, saved: str, device: str) -> None:
        text = strings.W1_DEVICE_FALLBACK.format(saved=saved, device=device)
        self.status.add_warning("W1", text, self.clock())

    @property
    def can_start(self) -> bool:
        return bool(self.devices) and not (self.status.error and self.status.error.id == "E1")

    def device_options(self) -> list[Option]:
        if not self.devices:
            return [Option(None, strings.NO_DEVICE_COMBO)]
        return [Option(d, d) for d in self.devices]

    def pick_device(self, name: str) -> None:
        """Explicit user pick: written to ``midi_device`` (§11 UX-Q4), clears W1/E2-E4."""
        if name not in self.devices:
            return
        self.selected_device = name
        self.status.clear_warning("W1")
        self.status.clear_error("E2", "E3", "E4")
        self._update(midi_device=name, post=False)
        self.engine.post(eng.SET_DEVICE, name)
        if self.status.playing:
            self.status.on_start_requested(name)
        self._changed()

    def reconnect(self) -> None:
        """⟳: re-enumerate; if playing, close and reopen the selected device."""
        self.refresh_devices()
        if self.status.playing:
            self.status.reconnecting = True
            self.engine.post(eng.RECONNECT)
        self._changed()

    # -- playback ----------------------------------------------------------------------

    def toggle(self) -> None:
        """Start/Stop button, tray item and hotkey. The label flips only on engine events."""
        if self.status.playing or self.status.connecting:
            self.engine.post(eng.STOP)
            return
        if not self.can_start:
            self.refresh_devices()
            if not self.can_start:
                return
        self.status.clear_warning("W1")  # comes back from the engine if still missing
        self.status.clear_error("E2", "E3", "E4", "E5")
        self.status.on_start_requested(self.selected_device)
        self.engine.post(eng.START)
        self._changed()

    def handle_event(self, event: eng.Event) -> None:
        if event.kind == "started":
            self.status.on_started(event.data["device"])
            self.selected_device = event.data["device"]
            if not event.data.get("fallback"):
                self.status.clear_warning("W1")
            if not self.settings.first_run_done:
                self._update(first_run_done=True, post=False)
        elif event.kind == "warning":
            self._warn_fallback(event.data["saved"], event.data["device"])
        elif event.kind == "stopped":
            self.status.on_stopped()
        elif event.kind == "note":
            self.status.on_note(event.data["note"], event.data["program"])
        elif event.kind == "error":
            self._on_error(event.data["error"])
        self._changed()

    def _on_error(self, exc: Exception) -> None:
        text, anchor = strings.midi_error_message(exc, self.selected_device)
        if isinstance(exc, NoDevicesError):
            self.devices = []
            self.selected_device = None
            err_id = "E1"
        else:
            err_id = {
                "DeviceBusyError": "E2",
                "DeviceOpenError": "E3",
                "DeviceLostError": "E4",
            }.get(type(exc).__name__, "E5")
        self.status.on_stopped()
        self.status.set_error(err_id, text, anchor)
        if isinstance(exc, DeviceLostError) and self.hidden and self.view is not None:
            device = exc.device or self.selected_device or ""
            self.view.notify(strings.BALLOON_LOST_TITLE, strings.BALLOON_LOST.format(device=device))

    # -- settings controls -------------------------------------------------------------

    def _update(self, post: bool = True, **changes: Any) -> None:
        self.settings = self.settings.replace(**changes)
        self.status.root = self.settings.root
        if post:
            self.engine.post(eng.SET_SETTINGS, self.settings)
        self.saver.request(self.settings)

    def scale_options(self) -> list[Option]:
        return [Option(s, SCALE_LABELS[s]) for s in self.scale_order]

    def set_scale(self, scale: str) -> None:
        self._update(scale=scale)
        self._changed()

    @property
    def key_enabled(self) -> bool:
        return self.settings.scale != "chromatic"

    def key_options(self) -> list[Option]:
        return [Option(n, label) for n, label in zip(NOTE_NAMES, strings.KEY_LABELS, strict=True)]

    def set_root(self, root: str) -> None:
        self._update(root=root)
        self._changed()

    def range_options(self, current: int) -> list[Option]:
        """Octave Cs; a non-C value from the file is shown as an extra item (UX-Q6)."""
        notes = sorted(set(OCTAVE_NOTES) | {current})
        return [Option(n, display_note(n, self.settings.root)) for n in notes]

    def set_low(self, low: int) -> None:
        high = self.settings.high_note
        if high - low < OCTAVE:
            high = min(127, low + OCTAVE)
            low = min(low, high - OCTAVE)
        self._update(low_note=low, high_note=high)
        self._changed()

    def set_high(self, high: int) -> None:
        low = self.settings.low_note
        if high - low < OCTAVE:
            low = max(0, high - OCTAVE)
            high = max(high, low + OCTAVE)
        self._update(low_note=low, high_note=high)
        self._changed()

    def instrument_options(self) -> list[Option]:
        return [Option(s.name, f"{s.label} ({len(s.programs)})") for s in INSTRUMENT_SETS.values()]

    def instrument_tooltip(self, name: str | None = None) -> str:
        s = INSTRUMENT_SETS.get(name or self.settings.instrument_set)
        names = ", ".join(program_name(p) for p in s.programs) if s else ""
        return strings.INSTRUMENTS_TOOLTIP.format(names=names)

    def set_instrument_set(self, name: str) -> None:
        self._update(instrument_set=name)
        self._changed()

    def set_volume(self, volume: float) -> None:
        v = round(volume)
        if v == self.settings.volume:
            return
        self.engine.post(eng.SET_VOLUME, v)
        self._update(volume=v, post=False)
        self._changed()

    def set_note_length(self, ms: float) -> None:
        v = round(ms / NOTE_LENGTH_STEP) * NOTE_LENGTH_STEP
        if v == self.settings.note_length_ms:
            return
        self._update(note_length_ms=v)
        self._changed()

    @property
    def note_length_enabled(self) -> bool:
        return not self.settings.legato

    def set_legato(self, on: bool) -> None:
        self._update(legato=bool(on))
        self._changed()

    def window_moved(self, x: int, y: int) -> None:
        if (x, y) != (self.settings.window_x, self.settings.window_y):
            self._update(window_x=x, window_y=y, post=False)

    # -- window / tray -----------------------------------------------------------------

    def close_window(self, *, balloon: bool = True) -> None:
        """✕ hides to the tray (playback continues); first time only shows the balloon.
        Esc calls this with ``balloon=False``."""
        self.hidden = True
        if self.view is not None:
            self.view.hide_window()
        if balloon and not self.settings.tray_hint_shown:
            if self.status.playing:
                text = strings.BALLOON_FIRST_CLOSE_PLAYING.format(hotkey=self.settings.hotkey)
            else:
                text = strings.BALLOON_FIRST_CLOSE
            if self.view is not None:
                self.view.notify(strings.BALLOON_FIRST_CLOSE_TITLE, text)
            self._update(tray_hint_shown=True, post=False)

    def show_window(self) -> None:
        self.hidden = False
        if self.view is not None:
            self.view.show_window()

    def on_save_error(self) -> None:
        """W5, once per session (OQ-11). The saver retries on the next change."""
        if self.w5_shown:
            return
        self.w5_shown = True
        self.status.add_warning("W5", strings.W5_CANT_SAVE, self.clock(), duration=WARNING_SECONDS)
        self._changed()

    def quit(self) -> None:
        """Tray → Quit / session end: silence and close (engine), save, exit. No confirmation."""
        if self.quitting:
            return
        self.quitting = True
        try:
            self.engine.shutdown()
        finally:
            self.saver.flush()
            if self.view is not None:
                self.view.quit_app()

    def dispatch(self, item: tuple[str, Any]) -> None:
        """Work handed over from other threads (engine, tray, hotkey window, saver)."""
        kind, value = item
        if kind == "event":
            self.handle_event(value)
        elif kind == "toggle":
            self.toggle()
        elif kind == "show":
            self.show_window()
        elif kind == "quit":
            self.quit()
        elif kind == "save_error":
            self.on_save_error()
        elif kind in (eng.SUSPEND, eng.RESUME, eng.DISPLAY_CHANGED):
            self.engine.post(kind)
        else:
            log.warning("unknown UI item %r", kind)

    def tick(self) -> None:
        """Called by the 50 ms drain so expiring warnings disappear."""
        self._changed()

    def _changed(self) -> None:
        if self.view is not None:
            self.view.refresh()
