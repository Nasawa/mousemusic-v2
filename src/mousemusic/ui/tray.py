"""System tray icon (docs/ux.md §2) via pystray.

Menu callbacks run on the tray thread and only post work to the UI queue (§6). The menu
layout is :func:`menu_spec` (pure, tested); the pystray wiring is thin glue that needs a real
tray (Windows shell), so it is covered by Grace's manual checks rather than CI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mousemusic.ui import strings

log = logging.getLogger(__name__)

STATES = ("idle", "playing", "error")


def menu_spec(playing: bool) -> list[tuple[str, str, bool]]:
    """``(label, action, default)`` in exact order; ``-`` is the separator (§2.2)."""
    return [
        (strings.TRAY_STOP if playing else strings.TRAY_START, "toggle", False),
        (strings.TRAY_SHOW, "show", True),
        ("-", "", False),
        (strings.TRAY_QUIT, "quit", False),
    ]


def icon_paths(icons_dir: Path) -> dict[str, Path]:
    return {state: icons_dir / f"tray-{state}.ico" for state in STATES}


class Tray:  # pragma: no cover - needs a desktop tray; manual check (Grace)
    def __init__(self, post: Callable[[str], None], icons_dir: Path) -> None:
        self.post = post
        self.icons_dir = icons_dir
        self.icon: Any = None
        self.playing = False
        self._images: dict[str, Any] = {}

    def start(self, tooltip: str) -> bool:
        try:
            import pystray
            from PIL import Image
        except Exception as exc:  # no tray backend (e.g. headless Linux)
            log.warning("tray unavailable: %s", exc)
            return False
        self._images = {s: Image.open(p) for s, p in icon_paths(self.icons_dir).items()}

        def item(index: int) -> Any:
            def text(_item: Any) -> str:
                return menu_spec(self.playing)[index][0]

            _label, action, default = menu_spec(False)[index]
            return pystray.MenuItem(text, lambda *_: self.post(action), default=default)

        menu = pystray.Menu(item(0), item(1), pystray.Menu.SEPARATOR, item(3))
        self.icon = pystray.Icon("MouseMusic", self._images["idle"], tooltip, menu)
        self.icon.run_detached()
        return True

    def update(self, state: str, tooltip: str, playing: bool) -> None:
        if self.icon is None:
            return
        self.playing = playing
        image = self._images.get(state)
        if image is not None and self.icon.icon is not image:
            self.icon.icon = image
        if self.icon.title != tooltip:
            self.icon.title = tooltip
        self.icon.update_menu()

    def notify(self, title: str, text: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(text, title)
            except Exception:
                log.exception("tray notification failed")

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
