"""Single instance (§9): named mutex ``Local\\MouseMusicV2``. A second launch broadcasts a
registered window message so the first instance shows its window, then exits.

``kernel32``/``user32`` are injectable; off Windows every launch counts as the first."""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

MUTEX_NAME = "Local\\MouseMusicV2"
SHOW_MESSAGE_NAME = "MouseMusicV2.ShowWindow"
ERROR_ALREADY_EXISTS = 183
HWND_BROADCAST = 0xFFFF


def _load() -> tuple[Any, Any, Any]:  # pragma: no cover - Windows only
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    u32.RegisterWindowMessageW.restype = wintypes.UINT
    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.PostMessageW.restype = wintypes.BOOL
    return k32, u32, ctypes.get_last_error


class SingleInstance:
    def __init__(self, kernel32: Any = None, user32: Any = None, last_error: Any = None) -> None:
        if kernel32 is None and sys.platform == "win32":  # pragma: no cover
            kernel32, user32, last_error = _load()
        self._k32, self._u32, self._last_error = kernel32, user32, last_error
        self._handle: Any = None
        self.show_message: int | None = None
        if self._u32 is not None:
            self.show_message = int(self._u32.RegisterWindowMessageW(SHOW_MESSAGE_NAME)) or None

    def acquire(self) -> bool:
        """True if this is the first instance (or the check is unavailable)."""
        if self._k32 is None:
            return True
        self._handle = self._k32.CreateMutexW(None, False, MUTEX_NAME)
        if not self._handle:
            log.warning("CreateMutexW failed (%s); not enforcing single instance",
                        self._last_error())  # fmt: skip
            return True
        if self._last_error() == ERROR_ALREADY_EXISTS:
            self._k32.CloseHandle(self._handle)
            self._handle = None
            return False
        return True

    def signal_first(self) -> None:
        """Ask the running instance to show, restore and focus its window."""
        if self._u32 is not None and self.show_message:
            self._u32.PostMessageW(HWND_BROADCAST, self.show_message, 0, 0)

    def release(self) -> None:
        if self._handle and self._k32 is not None:
            self._k32.CloseHandle(self._handle)
        self._handle = None
