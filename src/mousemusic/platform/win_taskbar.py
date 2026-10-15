"""Taskbar geometry via Win32 (docs/design/cell-granularity.md §4.2; CG-S2).

Primary bar: ``SHAppBarMessage(ABM_GETTASKBARPOS)``. Secondary bars: every visible top-level
``Shell_SecondaryTrayWnd``. Tray: ``TrayNotifyWnd`` on the primary bar. Scale:
``GetDpiForMonitor(MDT_EFFECTIVE_DPI) / 96``. Monitor number from ``\\\\.\\DISPLAYn``.
All coordinates are physical px (the process is per-monitor-v2 aware). Never raises.
"""

from __future__ import annotations

import ctypes
import logging
import re
import sys
from ctypes import wintypes
from typing import Any

from mousemusic.mapping import Rect
from mousemusic.taskbar import BOTTOM, LEFT, RIGHT, TOP, TaskbarInfo, infer_edge

log = logging.getLogger(__name__)

ABM_GETTASKBARPOS = 0x00000005
ABE_EDGES = {0: LEFT, 1: TOP, 2: RIGHT, 3: BOTTOM}
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
PRIMARY_CLASS = "Shell_TrayWnd"
SECONDARY_CLASS = "Shell_SecondaryTrayWnd"
TRAY_CLASS = "TrayNotifyWnd"
TASKBAR_CREATED = "TaskbarCreated"


def display_number(device: str, default: int = 1) -> int:
    """``\\\\.\\DISPLAY2`` → 2 (what Settings → Display shows)."""
    m = re.search(r"DISPLAY(\d+)$", device or "")
    return int(m.group(1)) if m else default


def to_rect(r: Any) -> Rect | None:
    w, h = r.right - r.left, r.bottom - r.top
    return Rect(r.left, r.top, w, h) if w > 0 and h > 0 else None


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT), ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]  # fmt: skip


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]  # fmt: skip


def find_taskbars() -> list[TaskbarInfo]:  # pragma: no cover - Windows only (A-win test)
    if sys.platform != "win32":
        return []
    try:
        return _find_taskbars()
    except Exception:
        log.debug("taskbar geometry failed", exc_info=True)
        return []


def _find_taskbars() -> list[TaskbarInfo]:  # pragma: no cover - Windows only
    u32 = ctypes.WinDLL("user32")
    shell32 = ctypes.WinDLL("shell32")
    try:
        shcore = ctypes.WinDLL("shcore")
    except OSError:
        shcore = None
    u32.FindWindowW.restype = wintypes.HWND
    u32.FindWindowExW.restype = wintypes.HWND
    u32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    u32.MonitorFromRect.restype = wintypes.HMONITOR
    u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    shell32.SHAppBarMessage.restype = ctypes.c_size_t

    def window_rect(hwnd: int) -> Rect | None:
        r = wintypes.RECT()
        return to_rect(r) if u32.GetWindowRect(hwnd, ctypes.byref(r)) else None

    def monitor(rect: Rect) -> tuple[Rect, float, int]:
        r = wintypes.RECT(rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)
        hmon = u32.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONEAREST)
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        u32.GetMonitorInfoW(hmon, ctypes.byref(info))
        mrect = to_rect(info.rcMonitor) or rect
        scale = 1.0
        if shcore is not None:
            dx, dy = wintypes.UINT(), wintypes.UINT()
            if (
                shcore.GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy))
                == 0
            ):
                scale = dx.value / 96.0
        return mrect, scale, display_number(info.szDevice)

    bars: list[TaskbarInfo] = []
    primary = u32.FindWindowW(PRIMARY_CLASS, None)
    if primary:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        rect = None
        edge = BOTTOM
        if shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd)):
            rect = to_rect(abd.rc)
            edge = ABE_EDGES.get(abd.uEdge, BOTTOM)
        rect = rect or window_rect(primary)
        if rect is not None:
            mrect, scale, num = monitor(rect)
            tray_hwnd = u32.FindWindowExW(primary, None, TRAY_CLASS, None)
            tray = window_rect(tray_hwnd) if tray_hwnd else None
            bars.append(TaskbarInfo(primary, rect, edge, mrect, scale, True, num, tray))

    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    buf = ctypes.create_unicode_buffer(64)

    def cb(hwnd: int, _l: int) -> bool:
        u32.GetClassNameW(hwnd, buf, 64)
        if buf.value == SECONDARY_CLASS and u32.IsWindowVisible(hwnd):
            rect = window_rect(hwnd)
            if rect is not None:
                mrect, scale, num = monitor(rect)
                bars.append(TaskbarInfo(hwnd, rect, infer_edge(rect, mrect), mrect, scale,
                                        False, num, None))  # fmt: skip
        return True

    u32.EnumWindows(proc_t(cb), 0)
    return bars


def register_taskbar_created() -> int:  # pragma: no cover - Windows only
    """The registered ``TaskbarCreated`` message id (Explorer restart broadcast)."""
    return ctypes.WinDLL("user32").RegisterWindowMessageW(TASKBAR_CREATED)
