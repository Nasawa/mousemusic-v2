"""Hidden top-level Win32 window on its own thread (§6 "Hotkey" thread).

- ``RegisterHotKey`` for the global shortcut (no hooks, §1/§9) → ``toggle``.
- ``WM_POWERBROADCAST`` → ``suspend`` / ``resume`` (§11 OQ-3; both ``PBT_APMRESUMEAUTOMATIC``
  and ``PBT_APMRESUMESUSPEND`` count as resume).
- ``WM_ENDSESSION`` → silence synchronously (before Windows ends the process), then ``quit``.
- ``WM_DISPLAYCHANGE`` → ``display_changed``; the single-instance message → ``show``.

It is a real top-level window (never shown), not ``HWND_MESSAGE``, because message-only
windows don't receive broadcasts. Message translation lives in the pure ``hotkey`` module;
this file is thin ctypes glue, exercised by Windows-only tests.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from typing import Any

from mousemusic.platform.hotkey import (
    MOD_NOREPEAT,
    WM_ENDSESSION,
    WM_SETTINGCHANGE,
    Hotkey,
    candidates,
    register_first,
    translate_message,
)

log = logging.getLogger(__name__)

HOTKEY_ID = 1
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_APP_REREGISTER = 0x8001  # WM_APP + 1


class MessageWindow(threading.Thread):  # pragma: no cover - Windows only
    def __init__(
        self,
        hotkey_setting: str,
        on_command: Callable[[str], None],
        *,
        on_hotkey: Callable[[str | None], None] | None = None,
        show_message: int | None = None,
        on_session_end: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(name="mousemusic-hotkey", daemon=True)
        self.setting = hotkey_setting
        self.on_hotkey = on_hotkey
        self.active: Hotkey | None = None
        self._pending: str | None = None
        self.on_command = on_command
        self.show_message = show_message
        self.on_session_end = on_session_end
        self.hwnd: Any = None
        self.ready = threading.Event()
        self._proc: Any = None

    def start_and_wait(self, timeout: float = 2.0) -> str | None:
        """Start the thread; returns the shortcut that registered (configured or the
        Ctrl+Alt+Shift+M fallback), or None (W4)."""
        self.start()
        self.ready.wait(timeout)
        return self.active.text if self.active else None

    def reregister(self, setting: str) -> None:
        """Live change from the picker: re-register on the window's own thread (Win32
        hotkeys belong to the registering thread); result goes to ``on_hotkey``."""
        self._pending = setting
        if self.hwnd:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32")
            user32.PostMessageW.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            ]  # fmt: skip
            user32.PostMessageW(self.hwnd, WM_APP_REREGISTER, 0, 0)

    def run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        lresult = ctypes.c_ssize_t
        wndproc_t = ctypes.WINFUNCTYPE(
            lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_t),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]  # fmt: skip
        user32.DefWindowProcW.restype = lresult
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]  # fmt: skip
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
        ]  # fmt: skip
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = lresult
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def try_register(hk: Hotkey) -> bool:
            ok = bool(user32.RegisterHotKey(self.hwnd, HOTKEY_ID, hk.modifiers | MOD_NOREPEAT,
                                            hk.vk))  # fmt: skip
            if not ok:
                log.warning("RegisterHotKey(%s) failed: %s", hk.text, ctypes.get_last_error())
            return ok

        def register(setting: str) -> None:
            if self.active is not None:
                user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
                self.active = None
            self.setting = setting
            self.active = register_first(candidates(setting), try_register)
            log.info("global shortcut: %s", self.active.text if self.active else "none")

        def proc(hwnd: Any, msg: int, wparam: int, lparam: int) -> int:
            try:
                if msg == WM_APP_REREGISTER:
                    register(self._pending if self._pending is not None else self.setting)
                    if self.on_hotkey is not None:
                        self.on_hotkey(self.active.text if self.active else None)
                    return 0
                setting = None
                if msg == WM_SETTINGCHANGE and lparam:
                    setting = ctypes.wstring_at(lparam)  # e.g. "ImmersiveColorSet"
                cmd = translate_message(msg, wparam, self.show_message, setting)
                if cmd is not None:
                    if msg == WM_ENDSESSION and self.on_session_end is not None:
                        self.on_session_end()  # silence before Windows ends the process
                    self.on_command(cmd)
                    return 0 if msg != 0x0218 else 1  # WM_POWERBROADCAST expects TRUE
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:
                log.exception("message window handler failed")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = wndproc_t(proc)
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        # Unique per instance: a window class is bound to one wndproc (this instance's).
        wc.lpszClassName = f"MouseMusicV2MessageWindow{id(self):x}"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            log.warning("RegisterClassW failed: %s", ctypes.get_last_error())
        self.hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "MouseMusic", 0, 0, 0, 0, 0, None, None, hinst, None
        )
        if not self.hwnd:
            log.error("CreateWindowExW failed: %s", ctypes.get_last_error())
            self.ready.set()
            return
        register(self.setting)
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self.active is not None:
            user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)

    def stop(self) -> None:
        if self.hwnd:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32")
            user32.PostMessageW.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            ]  # fmt: skip
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
