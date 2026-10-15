"""C-2: expose the full status message to screen readers (ARCHITECTURE §11 C-2).

Tk 8.6 has no accessibility API. MSAA/UIA read a child window's text as its Name, so we set
the status label's window text to the full message and fire one EVENT_OBJECT_NAMECHANGE.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

EVENT_OBJECT_NAMECHANGE = 0x800C
OBJID_CLIENT = -4
CHILDID_SELF = 0


def _user32() -> Any:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32")
    u.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    u.SetWindowTextW.restype = wintypes.BOOL
    u.NotifyWinEvent.argtypes = [wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG]
    u.NotifyWinEvent.restype = None
    return u


class Announcer:
    """Call with ``(hwnd, full_text)`` on every refresh; announces only distinct messages."""

    def __init__(self, user32: Any = None) -> None:
        self._user32 = user32
        self.last: str | None = None

    def __call__(self, hwnd: int, text: str) -> bool:
        if not hwnd or text == self.last:
            return False
        self.last = text
        try:
            u = self._user32 = self._user32 or _user32()
            u.SetWindowTextW(hwnd, text)
            u.NotifyWinEvent(EVENT_OBJECT_NAMECHANGE, hwnd, OBJID_CLIENT, CHILDID_SELF)
        except Exception:
            log.exception("screen-reader announcement failed")
            return False
        return True
