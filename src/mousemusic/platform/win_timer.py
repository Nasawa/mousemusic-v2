"""1 ms timer resolution while playing (§6): ``timeBeginPeriod(1)`` / ``timeEndPeriod(1)``.

Idempotent and safe on any OS (a no-op where WinMM isn't available)."""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

PERIOD_MS = 1


def load_winmm_timer() -> Any:  # pragma: no cover - Windows only
    lib = ctypes.WinDLL("winmm")
    lib.timeBeginPeriod.argtypes = [ctypes.c_uint]
    lib.timeBeginPeriod.restype = ctypes.c_uint
    lib.timeEndPeriod.argtypes = [ctypes.c_uint]
    lib.timeEndPeriod.restype = ctypes.c_uint
    return lib


class TimerPeriod:
    def __init__(self, lib: Any = None) -> None:
        if lib is None and sys.platform == "win32":  # pragma: no cover
            lib = load_winmm_timer()
        self._lib = lib
        self.active = False

    def begin(self) -> None:
        if self.active or self._lib is None:
            return
        code = self._lib.timeBeginPeriod(PERIOD_MS)
        if code:
            log.warning("timeBeginPeriod(1) failed: %s", code)
            return
        self.active = True

    def end(self) -> None:
        if not self.active:
            return
        self.active = False
        self._lib.timeEndPeriod(PERIOD_MS)
