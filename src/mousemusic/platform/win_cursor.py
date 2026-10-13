"""Cursor position, virtual-desktop metrics and DPI awareness via ``ctypes`` (§1, §9).

Importable on any OS: the ``user32``/``shcore`` libraries are injectable for tests and only
:func:`load_user32` / :func:`load_shcore` need Windows. All coordinates are physical pixels once
the process is per-monitor DPI aware, which :func:`set_dpi_awareness` must ensure first thing.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Any

from mousemusic.mapping import Rect

log = logging.getLogger(__name__)

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2
E_ACCESSDENIED = -2147024891  # 0x80070005: awareness already set (e.g. by the manifest)


def load_user32() -> Any:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        raise OSError("user32 is only available on Windows")
    lib = ctypes.WinDLL("user32", use_last_error=True)
    lib.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    lib.GetCursorPos.restype = wintypes.BOOL
    lib.GetSystemMetrics.argtypes = [ctypes.c_int]
    lib.GetSystemMetrics.restype = ctypes.c_int
    try:
        lib.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        lib.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    except AttributeError:
        pass  # older than Windows 10 1703
    lib.SetProcessDPIAware.restype = wintypes.BOOL
    return lib


def load_shcore() -> Any:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        raise OSError("shcore is only available on Windows")
    lib = ctypes.WinDLL("shcore")
    lib.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
    lib.SetProcessDpiAwareness.restype = ctypes.c_long
    return lib


def set_dpi_awareness(user32: Any = None, shcore_loader: Any = None) -> str:
    """Per-monitor v2 → per-monitor (shcore) → system aware. Returns which one took effect.
    Never raises: on failure the process stays unaware and the mapping uses scaled pixels."""
    try:
        user32 = user32 if user32 is not None else load_user32()
    except OSError as exc:
        log.warning("DPI awareness not set: %s", exc)
        return "unavailable"
    fn = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if fn is not None and fn(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
        return "per_monitor_v2"
    try:
        shcore = (shcore_loader or load_shcore)()
        hr = shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        if hr in (0, E_ACCESSDENIED):
            return "per_monitor" if hr == 0 else "already_set"
    except (OSError, AttributeError) as exc:
        log.info("shcore.SetProcessDpiAwareness unavailable: %s", exc)
    if user32.SetProcessDPIAware():
        return "system"
    log.warning("could not set any DPI awareness")
    return "unaware"


class WinCursor:
    """Polls ``GetCursorPos`` and the virtual-screen metrics. No hooks (§1, §9)."""

    def __init__(self, user32: Any = None) -> None:
        self._user32 = user32 if user32 is not None else load_user32()

    def position(self) -> tuple[int, int] | None:
        """Cursor in physical virtual-desktop pixels (may be negative); None on failure
        (e.g. secure desktop / UAC prompt)."""
        pt = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(pt)):
            return None
        return pt.x, pt.y

    def _rect(self, x: int, y: int, w: int, h: int) -> Rect | None:
        try:
            return Rect(x, y, w, h)
        except ValueError:
            log.warning("ignoring empty screen rect %r", (x, y, w, h))
            return None

    def virtual_rect(self) -> Rect | None:
        m = self._user32.GetSystemMetrics
        return self._rect(
            m(SM_XVIRTUALSCREEN), m(SM_YVIRTUALSCREEN), m(SM_CXVIRTUALSCREEN), m(SM_CYVIRTUALSCREEN)
        )

    def primary_rect(self) -> Rect | None:
        m = self._user32.GetSystemMetrics
        return self._rect(0, 0, m(SM_CXSCREEN), m(SM_CYSCREEN))


def monitor_work_areas(user32: Any = None) -> list[Rect]:  # pragma: no cover - Windows only
    """Work areas (excluding the taskbar) of all currently attached monitors, physical px."""
    u32 = user32 if user32 is not None else load_user32()

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]  # fmt: skip

    proc_t = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )  # fmt: skip
    found: list[Rect] = []

    def cb(hmon: Any, _hdc: Any, _rect: Any, _data: Any) -> bool:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if u32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcWork
            if r.right > r.left and r.bottom > r.top:
                found.append(Rect(r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    u32.EnumDisplayMonitors(None, None, proc_t(cb), 0)
    return found
