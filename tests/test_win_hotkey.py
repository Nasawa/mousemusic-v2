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

    results = []
    w = MessageWindow(
        "Off",
        on_command,
        on_hotkey=results.append,
        show_message=0xC123,
        on_session_end=lambda: ended.append(1),
    )
    assert w.start_and_wait() is None  # shortcut Off: nothing registered
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
    # Live re-register: an unusual combo is almost certainly free on the runner.
    w.reregister("Ctrl+Alt+Shift+F11")
    for _ in range(50):
        if results:
            break
        threading.Event().wait(0.1)
    assert results and results[0] in ("Ctrl+Alt+Shift+F11", "Ctrl+Alt+Shift+M", None)
    w.stop()
    w.join(5)
    assert not w.is_alive()


def _wait(pred, seconds=5.0):
    end = threading.Event()
    for _ in range(int(seconds * 20)):
        if pred():
            return True
        end.wait(0.05)
    return pred()


@pytest.mark.parametrize("setting", ["Off", "Ctrl+Alt+Shift+M"])
def test_a2_message_window_exists_without_hotkey(setting):
    """ARCHITECTURE A-2: the hidden message window and its thread exist even when the
    shortcut is Off or fails to register, so power/session/theme broadcasts still arrive."""
    import ctypes
    from ctypes import wintypes

    from mousemusic.platform import hotkey as hk
    from mousemusic.platform.win_hotkey import MessageWindow

    holder = None
    if setting != "Off":  # make registration fail: another window holds the only candidate
        holder = MessageWindow(setting, lambda c: None)
        holder.start_and_wait()
    got = []
    w = MessageWindow(setting, got.append)
    active = w.start_and_wait()
    try:
        if setting == "Off" or (holder is not None and holder.active is not None):
            assert active is None
        assert w.hwnd and w.is_alive()
        user32 = ctypes.WinDLL("user32")
        user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]  # fmt: skip
        user32.SendMessageW.argtypes = user32.PostMessageW.argtypes
        user32.SendMessageW.restype = ctypes.c_ssize_t
        name = ctypes.create_unicode_buffer("ImmersiveColorSet")
        user32.PostMessageW(w.hwnd, hk.WM_POWERBROADCAST, hk.PBT_APMRESUMESUSPEND, 0)
        # WM_SETTINGCHANGE can't be posted (ERROR_MESSAGE_SYNC_ONLY); Windows sends it too.
        user32.SendMessageW(w.hwnd, hk.WM_SETTINGCHANGE, hk.SPI_SETHIGHCONTRAST, 0)
        user32.SendMessageW(w.hwnd, hk.WM_SETTINGCHANGE, 0, ctypes.addressof(name))
        assert _wait(lambda: len(got) >= 3), got
        assert got[:3] == ["resume", "theme_changed", "theme_changed"]
    finally:
        w.stop()
        w.join(5)
        if holder is not None:
            holder.stop()
            holder.join(5)
