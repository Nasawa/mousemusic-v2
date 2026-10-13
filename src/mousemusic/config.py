"""Settings: dataclass, defaults, location, validation/clamping, load and atomic save.

See ARCHITECTURE.md §4. Never raises on bad settings files: unknown keys are ignored, invalid
values are clamped or reset to defaults with a log warning, and a corrupt file is renamed to
``settings.json.bak`` and replaced with defaults.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import math
import os
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from mousemusic.instruments import INSTRUMENT_SETS
from mousemusic.scales import NOTE_NAMES, SCALES, root_pitch_class

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
APP_DIR_NAME = "MouseMusic"
SETTINGS_FILE = "settings.json"
SAVE_DEBOUNCE_S = 0.5
SCREEN_MODES = ("virtual_desktop", "primary")

# Validation ranges, ARCHITECTURE.md §11 OQ-8. WINDOW_POS_RANGE is ours (Win32 coordinate span).
NOTE_RANGE = (0, 127)
MIN_NOTE_SPAN = 12
VOLUME_RANGE = (0, 100)
VELOCITY_RANGE = (1, 127)
NOTE_LENGTH_RANGE_MS = (50, 2000)
POLL_HZ_RANGE = (30, 250)
WINDOW_POS_RANGE = (-32768, 32767)

#: Migrations from older schemas, ``{from_version: fn(raw) -> raw}``, applied in order (OQ-9).
#: Empty while schema 1 is the only version; a file without ``schema`` is treated as 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


@dataclass(frozen=True)
class Settings:
    """Immutable settings snapshot. Defaults match ARCHITECTURE.md §4."""

    schema: int = SCHEMA_VERSION
    midi_device: str = "Microsoft GS Wavetable Synth"
    scale: str = "pentatonic_major"
    root: str = "C"
    low_note: int = 36
    high_note: int = 96
    instrument_set: str = "classic"
    volume: int = 80
    velocity: int = 100
    note_length_ms: int = 250
    legato: bool = False
    poll_hz: int = 125
    screen_mode: str = "virtual_desktop"
    start_on_launch: bool = False
    hotkey: str = "Ctrl+Alt+M"
    first_run_done: bool = False
    tray_hint_shown: bool = False
    window_x: int | None = None
    window_y: int | None = None

    def replace(self, **changes: Any) -> Settings:
        """A validated copy with ``changes`` applied (for UI updates)."""
        merged = {**dataclasses.asdict(self), **changes}
        return validate(merged)[0]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


DEFAULTS = Settings()
_FIELD_NAMES = tuple(f.name for f in fields(Settings))


# --- validation ---------------------------------------------------------------


class _Issues(list[str]):
    def add(self, key: str, value: Any, result: Any) -> None:
        self.append(f"{key}={value!r} is invalid; using {result!r}")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return round(value)
    return None


def _int(raw: Mapping[str, Any], key: str, lo: int, hi: int, issues: _Issues) -> int:
    default = getattr(DEFAULTS, key)
    if key not in raw:
        return default
    value = raw[key]
    n = _as_int(value)
    if n is None:
        issues.add(key, value, default)
        return default
    clamped = min(max(n, lo), hi)
    if clamped != value:
        issues.add(key, value, clamped)
    return clamped


def _bool(raw: Mapping[str, Any], key: str, issues: _Issues) -> bool:
    default = getattr(DEFAULTS, key)
    value = raw.get(key, default)
    if not isinstance(value, bool):
        issues.add(key, value, default)
        return default
    return value


def _choice(raw: Mapping[str, Any], key: str, choices: Any, issues: _Issues) -> str:
    default = getattr(DEFAULTS, key)
    value = raw.get(key, default)
    if not isinstance(value, str) or value not in choices:
        issues.add(key, value, default)
        return default
    return value


def _text(raw: Mapping[str, Any], key: str, issues: _Issues) -> str:
    default = getattr(DEFAULTS, key)
    value = raw.get(key, default)
    if not isinstance(value, str) or not value.strip():
        issues.add(key, value, default)
        return default
    return value


def _optional_int(raw: Mapping[str, Any], key: str, issues: _Issues) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    n = _as_int(value)
    if n is None:
        issues.add(key, value, None)
        return None
    clamped = min(max(n, WINDOW_POS_RANGE[0]), WINDOW_POS_RANGE[1])
    if clamped != value:
        issues.add(key, value, clamped)
    return clamped


def _hotkey(raw: Mapping[str, Any], issues: _Issues) -> str:
    """Kept verbatim if it is a string: parsing happens where the hotkey is registered, and an
    unparsable value disables the shortcut with W4 instead of silently using the default
    (ARCHITECTURE.md §11 OQ-5)."""
    value = raw.get("hotkey", DEFAULTS.hotkey)
    if not isinstance(value, str):
        issues.add("hotkey", value, DEFAULTS.hotkey)
        return DEFAULTS.hotkey
    return value


def _note_range(low: int, high: int, issues: _Issues) -> tuple[int, int]:
    """OQ-8: keep at least an octave. If ``high - low < 12``: ``high = min(127, low + 12)``;
    if that is still short, ``low = high - 12``."""
    if high - low >= MIN_NOTE_SPAN:
        return low, high
    new_high = min(NOTE_RANGE[1], low + MIN_NOTE_SPAN)
    new_low = low if new_high - low >= MIN_NOTE_SPAN else new_high - MIN_NOTE_SPAN
    issues.append(f"note range {low}..{high} is under an octave; using {new_low}..{new_high}")
    return new_low, new_high


def _migrate(raw: Mapping[str, Any], issues: _Issues) -> Mapping[str, Any]:
    schema = raw.get("schema", SCHEMA_VERSION)
    if isinstance(schema, bool) or not isinstance(schema, int):
        issues.append(f"schema={schema!r} is invalid; treating as {SCHEMA_VERSION}")
        return raw
    if schema > SCHEMA_VERSION:
        issues.append(f"schema={schema} is newer than {SCHEMA_VERSION}; reading known keys only")
        return raw
    data = dict(raw)
    for version in range(schema, SCHEMA_VERSION):
        if version in MIGRATIONS:
            data = MIGRATIONS[version](data)
    return data


def _root(raw: Mapping[str, Any], issues: _Issues) -> str:
    value = raw.get("root", DEFAULTS.root)
    try:
        return NOTE_NAMES[root_pitch_class(value)]
    except (ValueError, AttributeError):
        issues.add("root", value, DEFAULTS.root)
        return DEFAULTS.root


def validate(raw: Mapping[str, Any]) -> tuple[Settings, list[str]]:
    """Build a valid :class:`Settings` from untrusted data. Returns it plus a list of warnings.

    Unknown keys are ignored. Missing keys take defaults. Out-of-range numbers are clamped per
    key, then the note range is widened to an octave if needed (OQ-8). Wrong types and unknown
    choices fall back to that key's default. A newer ``schema`` is read best-effort (OQ-9); it is
    not rewritten here, only by the next save.
    """
    issues = _Issues()
    raw = _migrate(raw, issues)
    scale = _choice(raw, "scale", SCALES, issues)
    root = _root(raw, issues)
    low, high = _note_range(
        _int(raw, "low_note", *NOTE_RANGE, issues),
        _int(raw, "high_note", *NOTE_RANGE, issues),
        issues,
    )

    settings = Settings(
        schema=SCHEMA_VERSION,
        midi_device=_text(raw, "midi_device", issues),
        scale=scale,
        root=root,
        low_note=low,
        high_note=high,
        instrument_set=_choice(raw, "instrument_set", INSTRUMENT_SETS, issues),
        volume=_int(raw, "volume", *VOLUME_RANGE, issues),
        velocity=_int(raw, "velocity", *VELOCITY_RANGE, issues),
        note_length_ms=_int(raw, "note_length_ms", *NOTE_LENGTH_RANGE_MS, issues),
        legato=_bool(raw, "legato", issues),
        poll_hz=_int(raw, "poll_hz", *POLL_HZ_RANGE, issues),
        screen_mode=_choice(raw, "screen_mode", SCREEN_MODES, issues),
        start_on_launch=_bool(raw, "start_on_launch", issues),
        hotkey=_hotkey(raw, issues),
        first_run_done=_bool(raw, "first_run_done", issues),
        tray_hint_shown=_bool(raw, "tray_hint_shown", issues),
        window_x=_optional_int(raw, "window_x", issues),
        window_y=_optional_int(raw, "window_y", issues),
    )
    return settings, list(issues)


# --- location -----------------------------------------------------------------


def exe_dir() -> Path | None:
    """Folder of the packaged exe, or ``None`` when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def settings_path(
    *,
    portable: bool = False,
    app_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Where settings live.

    Portable mode (``--portable``, or a ``settings.json`` already next to the exe) uses the exe
    folder. Otherwise ``%APPDATA%\\MouseMusic\\settings.json``. If ``APPDATA`` is unset (not
    Windows), ``~/.config/MouseMusic/settings.json`` is used so the core runs anywhere.
    """
    env = os.environ if environ is None else environ
    if app_dir is None:
        app_dir = exe_dir()
    if app_dir is not None and (portable or (app_dir / SETTINGS_FILE).is_file()):
        return app_dir / SETTINGS_FILE
    appdata = env.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / APP_DIR_NAME / SETTINGS_FILE


# --- load / save ----------------------------------------------------------------


def _backup_corrupt(path: Path) -> None:
    bak = path.with_name(path.name + ".bak")
    if bak.exists():
        log.warning("overwriting previous %s (only the latest backup is kept)", bak)
    try:
        os.replace(path, bak)
        log.warning("settings file %s is corrupt; moved to %s and using defaults", path, bak)
    except OSError as exc:
        log.warning("settings file %s is corrupt and could not be moved: %s", path, exc)


@dataclass(frozen=True)
class LoadResult:
    """What :func:`load_report` found, so the UI can show W2 (corrupt) / W3 (issues)."""

    settings: Settings
    existed: bool = False
    corrupt: bool = False
    issues: tuple[str, ...] = ()


def load_report(path: Path) -> LoadResult:
    """Load settings, never raising. See module docstring for the robustness rules."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LoadResult(DEFAULTS)
    except (OSError, UnicodeDecodeError) as exc:
        if isinstance(exc, UnicodeDecodeError):
            _backup_corrupt(path)
            _try_save(DEFAULTS, path)
            return LoadResult(DEFAULTS, existed=True, corrupt=True)
        log.warning("could not read settings %s: %s; using defaults", path, exc)
        return LoadResult(DEFAULTS, existed=True)
    try:
        raw = json.loads(text)
    except ValueError:
        raw = None
    if not isinstance(raw, dict):
        _backup_corrupt(path)
        _try_save(DEFAULTS, path)
        return LoadResult(DEFAULTS, existed=True, corrupt=True)
    settings, issues = validate(raw)
    for issue in issues:
        log.warning("settings: %s", issue)
    return LoadResult(settings, existed=True, issues=tuple(issues))


def load(path: Path) -> Settings:
    """Load settings, never raising (see :func:`load_report`)."""
    return load_report(path).settings


def save(settings: Settings, path: Path, *, retries: int = 3, retry_delay_s: float = 0.05) -> None:
    """Write atomically: temp file in the same folder, fsync, then ``os.replace``.

    ``os.replace`` is retried briefly because on Windows antivirus or indexers can hold the
    target open for a moment (PermissionError).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(settings.to_dict(), indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(retries + 1):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == retries:
                    raise
                time.sleep(retry_delay_s)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _try_save(settings: Settings, path: Path) -> bool:
    try:
        save(settings, path)
    except OSError as exc:
        log.warning("could not save settings %s: %s", path, exc)
        return False
    return True


class Timer:
    """Minimal interface of :class:`threading.Timer` used by :class:`DebouncedSaver`."""

    def start(self) -> None: ...  # pragma: no cover
    def cancel(self) -> None: ...  # pragma: no cover


TimerFactory = Callable[[float, Callable[[], None]], Timer]


def _thread_timer(delay: float, fn: Callable[[], None]) -> Timer:
    t = threading.Timer(delay, fn)
    t.daemon = True
    return t


class DebouncedSaver:
    """Saves the latest requested settings ``delay_s`` after the last :meth:`request` call.

    Thread-safe. Call :meth:`flush` on shutdown to write any pending change immediately.
    """

    def __init__(
        self,
        path: Path,
        delay_s: float = SAVE_DEBOUNCE_S,
        timer_factory: TimerFactory = _thread_timer,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        self.path = path
        self.on_error = on_error  # W5 hook; called on each failed save (UI shows it once)
        self.delay_s = delay_s
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._pending: Settings | None = None
        self._timer: Timer | None = None

    def request(self, settings: Settings) -> None:
        with self._lock:
            self._pending = settings
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._timer_factory(self.delay_s, self.flush)
            self._timer.start()

    @property
    def pending(self) -> Settings | None:
        return self._pending

    def flush(self) -> bool:
        """Write the pending settings now. Returns False if nothing was written."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            settings, self._pending = self._pending, None
        if settings is None:
            return False
        ok = _try_save(settings, self.path)
        if not ok and self.on_error is not None:
            self.on_error()
        return ok
