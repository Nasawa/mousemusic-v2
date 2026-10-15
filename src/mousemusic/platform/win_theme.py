"""Windows theme probes and the dark title bar (docs/ux.md §11.1, §11.3, §11.6).

Every function returns a value and never raises; OS access is injectable for tests.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
SPI_GETHIGHCONTRAST = 0x0042
SPI_SETHIGHCONTRAST = 0x0043
HCF_HIGHCONTRASTON = 0x00000001
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # Windows 10 builds 17763-18985
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x0001, 0x0002, 0x0004, 0x0020


class HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("lpszDefaultScheme", ctypes.c_wchar_p),
    ]


def apps_use_light_theme(winreg_module: Any = None) -> bool | None:
    """``AppsUseLightTheme`` (HKCU): True/False, or None if missing/unreadable."""
    try:
        reg = winreg_module
        if reg is None:  # pragma: no cover - Windows only
            import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as key:
            value, _type = reg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except Exception as exc:
        log.debug("AppsUseLightTheme unavailable: %s", exc)
        return None


def high_contrast_on(user32: Any = None) -> bool:
    try:
        u32 = user32
        if u32 is None:  # pragma: no cover - Windows only
            u32 = ctypes.WinDLL("user32")
        hc = HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
        if not u32.SystemParametersInfoW(SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0):
            return False
        return bool(hc.dwFlags & HCF_HIGHCONTRASTON)
    except Exception as exc:
        log.debug("high contrast query failed: %s", exc)
        return False


def set_dark_title_bar(hwnd: int, dark: bool, dwmapi: Any = None, user32: Any = None) -> bool:
    """DWM immersive dark mode on the frame: attribute 20, then 19 on older Windows 10.
    Forces a non-client repaint so a live change shows without restart. False if unsupported."""
    try:
        dwm = dwmapi
        u32 = user32
        if dwm is None:  # pragma: no cover - Windows only
            dwm = ctypes.WinDLL("dwmapi")
        if u32 is None:  # pragma: no cover - Windows only
            u32 = ctypes.WinDLL("user32")
        value = ctypes.c_int(1 if dark else 0)
        ok = False
        for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            hr = dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
            if hr == 0:  # S_OK
                ok = True
                break
        if not ok:
            log.debug("DwmSetWindowAttribute dark=%s unsupported", dark)
            return False
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        return True
    except Exception as exc:
        log.debug("dark title bar failed: %s", exc)
        return False


def frame_hwnd(root: Any, user32: Any = None) -> int | None:
    """The top-level frame that owns the Tk root's client window."""
    try:
        u32 = user32
        if u32 is None:  # pragma: no cover - Windows only
            u32 = ctypes.WinDLL("user32")
        return u32.GetParent(root.winfo_id()) or None
    except Exception as exc:
        log.debug("GetParent failed: %s", exc)
        return None


def probe() -> tuple[bool | None, bool]:
    """``(apps_use_light, high_contrast)`` for the current OS; non-Windows → (None, False)."""
    if sys.platform != "win32":
        return None, False
    return apps_use_light_theme(), high_contrast_on()  # pragma: no cover - Windows only
