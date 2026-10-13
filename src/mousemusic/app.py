"""Application wiring (ARCHITECTURE.md §6): the startup order and thread layout.

Main thread: Tk main loop (window + 50 ms queue drain) and signal handlers.
Engine thread: poll loop + MIDI. Hotkey thread (Windows): hidden message window for the global
hotkey, power/session/display messages and the single-instance "show" message. Tray thread:
pystray. Everything that isn't the Tk thread talks to the UI only through ``ui_queue``.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mousemusic import __version__, config
from mousemusic import engine as eng
from mousemusic.logs import log_dir, setup_logging
from mousemusic.midi import MidiOut, default_backend
from mousemusic.midi.fake import FakeMidiOut
from mousemusic.platform.hotkey import parse_hotkey
from mousemusic.platform.single_instance import SingleInstance
from mousemusic.ui import strings
from mousemusic.ui.controller import AppController

log = logging.getLogger(__name__)

JITTER_LOG_S = 60.0  # LT-02: debug-log poll jitter p95/max once a minute


@dataclass
class Options:
    dry_run: bool = False
    portable: bool = False
    log_level: str = "info"
    settings_path: Path | None = None
    log_directory: Path | None = None
    single_instance: Any = None
    root_factory: Any = None
    on_ready: Any = None  # test hook: called with (root, controller, ui_queue) before mainloop
    extra: dict[str, Any] = field(default_factory=dict)


def assets_dir() -> Path:
    """``assets/`` next to the bundled app (PyInstaller ``_MEIPASS``) or at the repo root."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"


def make_backend(settings: config.Settings, dry_run: bool) -> MidiOut:
    if dry_run:  # §11: --dry-run prints MIDI instead of sending it
        return FakeMidiOut([settings.midi_device or "Dry run"], echo=print)
    return default_backend()


def make_cursor(root: Any) -> tuple[Any, Any]:
    """Returns ``(cursor_source, tk_cache_or_None)``."""
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.platform.win_cursor import WinCursor

        return WinCursor(), None
    from mousemusic.ui.window import TkCursorCache

    cache = TkCursorCache()
    cache.update(root)
    return cache, cache


def make_monitors() -> Any:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.platform.win_cursor import monitor_work_areas

        return monitor_work_areas
    return None  # window falls back to Tk's screen size


def show_fatal(text: str) -> None:  # pragma: no cover - Windows message box
    """F1: last-resort crash dialog (docs/ux.md §4)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, strings.F1_TITLE, 0x10)
    else:
        print(f"{strings.F1_TITLE}: {text}", file=sys.stderr)


def run(opts: Options) -> int:
    setup_logging(opts.log_level, opts.log_directory or log_dir())
    log.info("MouseMusic %s starting (dry_run=%s)", __version__, opts.dry_run)
    try:
        return _run(opts)
    except Exception:
        log.exception("fatal error")
        show_fatal(strings.F1_TEXT)
        return 1


def _run(opts: Options) -> int:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.platform.win_cursor import set_dpi_awareness

        log.info("DPI awareness: %s", set_dpi_awareness())

    instance = opts.single_instance or SingleInstance()
    if not instance.acquire():
        log.info("another instance is running; asking it to show its window")
        instance.signal_first()
        return 0
    try:
        return _run_app(opts, instance)
    finally:
        instance.release()


def _run_app(opts: Options, instance: Any) -> int:
    import tkinter as tk

    from mousemusic.ui.window import MainWindow

    path = opts.settings_path or config.settings_path(portable=opts.portable)
    loaded = config.load_report(path)
    settings = loaded.settings
    ui_queue: queue.Queue = queue.Queue()
    post = ui_queue.put

    root = (opts.root_factory or tk.Tk)()
    root.withdraw()
    cursor, cache = make_cursor(root)
    backend = make_backend(settings, opts.dry_run)
    timer = None
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.platform.win_timer import TimerPeriod

        timer = TimerPeriod()
    engine = eng.Engine(backend, cursor, settings, emit=lambda e: post(("event", e)), timer=timer)
    saver = config.DebouncedSaver(path, on_error=lambda: post(("save_error", None)))

    # Signal handlers must be installed from the main thread (§6); they only post to the UI.
    eng.install_exit_handlers(engine, on_signal=lambda: post(("quit", None)))

    hotkey_ok, message_window = False, None
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.platform.win_hotkey import MessageWindow

        message_window = MessageWindow(
            parse_hotkey(settings.hotkey),
            lambda cmd: post((cmd, None)),
            show_message=instance.show_message,
            on_session_end=engine.shutdown,
        )
        hotkey_ok = message_window.start_and_wait()

    tray = None
    if sys.platform == "win32":  # pragma: no cover - Windows only
        from mousemusic.ui.tray import Tray

        tray = Tray(lambda action: post((action, None)), assets_dir() / "icons")
        if not tray.start(strings.TRAY_TOOLTIP_STOPPED.format(version=__version__)):
            tray = None

    controller = AppController(
        settings, engine, saver, backend.list_devices, time.monotonic,
        hotkey_ok=hotkey_ok and bool(settings.hotkey), first_run=not loaded.existed,
    )  # fmt: skip
    window = MainWindow(
        root, controller, ui_queue=ui_queue, tray=tray, version=__version__,
        cursor_cache=cache, monitors=make_monitors(),
    )  # fmt: skip
    engine.start_thread()
    controller.startup(loaded)
    window.refresh()
    window.show_window()
    window.start_polling()
    _schedule_jitter_log(root, engine, controller)
    if opts.on_ready is not None:
        opts.on_ready(root, controller, ui_queue)
    try:
        root.mainloop()
    finally:
        controller.quit()  # idempotent: engine silenced + joined, settings flushed
        if message_window is not None:  # pragma: no cover - Windows only
            message_window.stop()
        with contextlib.suppress(tk.TclError):
            root.destroy()
    log.info("MouseMusic exited cleanly")
    return 0


def _schedule_jitter_log(root: Any, engine: eng.Engine, controller: AppController) -> None:
    def tick() -> None:
        if controller.quitting:
            return
        stats = engine.stats.jitter(1.0 / engine.settings.poll_hz)
        if stats is not None:
            p95, worst = stats
            log.debug("poll jitter p95=%.2f ms max=%.2f ms", p95 * 1000, worst * 1000)
        root.after(int(JITTER_LOG_S * 1000), tick)

    root.after(int(JITTER_LOG_S * 1000), tick)
