"""Status-line, tray-icon and tooltip state (docs/ux.md §1.3, §2.1, §4). Pure: time is passed in.

Precedence: Error > Warning > first-run hint > normal status. One message at a time. Errors stay
until resolved; warnings expire by their own rule; when an error clears, the oldest pending
warning shows, then the normal status.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mousemusic.instruments import program_name
from mousemusic.ui import strings

NORMAL, WARNING, ERROR = "normal", "warning", "error"
GREY, GREEN, AMBER, RED = "#808080", "#16A34A", "#D97706", "#DC2626"

#: W2/W3/W4/W5 minimum display time (docs/ux.md §4), seconds.
WARNING_SECONDS = 15.0
#: Device names in the status line are shortened to about 20 characters (§1.3).
DEVICE_MAX = 23

_SHARP_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
_FLAT_NAMES = ("C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B")
#: Keys shown with flats (docs/ux.md §1.3): F, B♭, E♭, A♭ (stored as sharps in settings).
FLAT_KEYS = frozenset({"F", "A#", "D#", "G#"})


def display_note(note: int, root: str = "C") -> str:
    """60 → ``C4``; 61 → ``C♯4`` (or ``D♭4`` in a flat key). Middle C = C4."""
    names = _FLAT_NAMES if root in FLAT_KEYS else _SHARP_NAMES
    return f"{names[note % 12]}{note // 12 - 1}"


def shorten(name: str, limit: int = DEVICE_MAX) -> str:
    """``Microsoft GS Wavetable Synth`` → ``Microsoft GS Wavetable…``."""
    if len(name) <= limit:
        return name
    return name[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class Status:
    dot: str
    color: str
    text: str
    severity: str = NORMAL
    help_anchor: str | None = None


@dataclass
class _Message:
    id: str
    text: str
    help_anchor: str | None = None
    shown_at: float = 0.0
    duration: float | None = None  # expires after this many seconds
    until_start: bool = False  # ...and not before the first Start (W2/W3)


@dataclass
class StatusModel:
    hotkey: str = "Ctrl+Alt+M"
    hotkey_ok: bool = True
    first_run: bool = False
    root: str = "C"
    device: str | None = None
    playing: bool = False
    connecting: bool = False
    reconnecting: bool = False
    started_once: bool = False
    last_note: tuple[int, int] | None = None
    error: _Message | None = None
    warnings: list[_Message] = field(default_factory=list)

    # -- errors / warnings -------------------------------------------------------------

    def set_error(self, id: str, text: str, help_anchor: str | None = None) -> None:
        self.error = _Message(id, text, help_anchor)
        self.connecting = self.reconnecting = False

    def clear_error(self, *ids: str) -> None:
        """Clear the current error (only if it is one of ``ids``, when given)."""
        if self.error is not None and (not ids or self.error.id in ids):
            self.error = None

    def add_warning(
        self,
        id: str,
        text: str,
        now: float,
        *,
        help_anchor: str | None = None,
        duration: float | None = None,
        until_start: bool = False,
    ) -> None:
        self.clear_warning(id)
        self.warnings.append(_Message(id, text, help_anchor, now, duration, until_start))

    def clear_warning(self, id: str) -> None:
        self.warnings = [w for w in self.warnings if w.id != id]

    def has_warning(self, id: str) -> bool:
        return any(w.id == id for w in self.warnings)

    def expire(self, now: float) -> None:
        def alive(w: _Message) -> bool:
            if w.duration is not None and now - w.shown_at < w.duration:
                return True
            if w.until_start and not self.started_once:
                return True
            return w.duration is None and not w.until_start

        self.warnings = [w for w in self.warnings if alive(w)]

    # -- playback state ----------------------------------------------------------------

    def on_start_requested(self, device: str | None) -> None:
        self.connecting = True
        self.reconnecting = False
        if device:
            self.device = device

    def on_started(self, device: str) -> None:
        self.device = device
        self.playing = True
        self.started_once = True
        self.first_run = False
        self.connecting = self.reconnecting = False
        self.last_note = None
        self.clear_error()  # E2-E5 resolved by a successful start

    def on_stopped(self) -> None:
        self.playing = False
        self.connecting = self.reconnecting = False
        self.last_note = None

    def on_note(self, note: int, program: int) -> None:
        self.last_note = (note, program)

    # -- rendering ---------------------------------------------------------------------

    def current(self, now: float) -> Status:
        self.expire(now)
        if self.error is not None:
            return Status(strings.DOT_ERROR, RED, self.error.text, ERROR, self.error.help_anchor)
        if self.warnings:
            w = self.warnings[0]
            return Status(strings.DOT_WARNING, AMBER, w.text, WARNING, w.help_anchor)
        if self.reconnecting:
            return Status(strings.DOT_NORMAL, GREY, strings.STATUS_RECONNECTING)
        if self.connecting:
            dev = self.device or ""
            return Status(strings.DOT_NORMAL, GREY, strings.STATUS_CONNECTING.format(device=dev))
        if self.playing:
            dev = shorten(self.device or "")
            if self.last_note is None:
                return Status(strings.DOT_NORMAL, GREEN,
                              strings.STATUS_PLAYING_IDLE.format(device=dev))  # fmt: skip
            note, program = self.last_note
            text = strings.STATUS_PLAYING.format(
                note=display_note(note, self.root), instrument=program_name(program), device=dev
            )
            return Status(strings.DOT_NORMAL, GREEN, text)
        if self.first_run:
            return Status(strings.DOT_NORMAL, GREY, strings.STATUS_FIRST_RUN)
        if self.hotkey_ok:
            return Status(strings.DOT_NORMAL, GREY,
                          strings.STATUS_STOPPED.format(hotkey=self.hotkey))  # fmt: skip
        return Status(strings.DOT_NORMAL, GREY, strings.STATUS_STOPPED_NO_HOTKEY)

    def tray_icon(self) -> str:
        """``idle`` / ``playing`` / ``error`` (assets/icons/tray-<state>.ico)."""
        if self.error is not None:
            return "error"
        return "playing" if self.playing else "idle"

    def tray_tooltip(self, version: str) -> str:
        state = self.tray_icon()
        template = {
            "error": strings.TRAY_TOOLTIP_ERROR,
            "playing": strings.TRAY_TOOLTIP_PLAYING,
            "idle": strings.TRAY_TOOLTIP_STOPPED,
        }[state]
        return template.format(version=version)

    def hotkey_hint(self) -> str:
        return self.hotkey if self.hotkey_ok else strings.SHORTCUT_OFF
