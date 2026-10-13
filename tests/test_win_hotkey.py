"""SN-09d: the real hidden message window translates posted Win32 messages (Windows CI)."""

import sys
import threading

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 message window")


def test_message_window_translates_posted_messages():
    import ctypes
    from ctypes import wintypes

    from mousemusic.platform import hotkey as hk
    from mousemusic.platform.win_hotkey import MessageWindow

    got, ended = [], []
    done = threading.Event()

    def on_command(cmd):
        got.append(cmd)
        if len(got) == 6:
            done.set()

    w = MessageWindow(None, on_command, show_message=0xC123, on_session_end=lambda: ended.append(1))
    assert w.start_and_wait() is False  # no hotkey requested
    assert w.hwnd
    user32 = ctypes.WinDLL("user32")
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    for msg, wp in (
        (hk.WM_HOTKEY, 1),
        (hk.WM_POWERBROADCAST, hk.PBT_APMSUSPEND),
        (hk.WM_POWERBROADCAST, hk.PBT_APMRESUMESUSPEND),
        (hk.WM_POWERBROADCAST, hk.PBT_APMRESUMEAUTOMATIC),
        (hk.WM_DISPLAYCHANGE, 0),
        (0xC123, 0),
    ):
        assert user32.PostMessageW(w.hwnd, msg, wp, 0)
    assert done.wait(5), got
    assert got == ["toggle", "suspend", "resume", "resume", "display_changed", "show"]
    w.stop()
    w.join(5)
    assert not w.is_alive()
