import pytest

from mousemusic.platform.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMRESUMESUSPEND,
    PBT_APMSUSPEND,
    WM_DISPLAYCHANGE,
    WM_ENDSESSION,
    WM_HOTKEY,
    WM_POWERBROADCAST,
    Hotkey,
    parse_hotkey,
    translate_message,
)


@pytest.mark.parametrize(
    ("text", "mods", "vk"),
    [
        ("Ctrl+Alt+M", MOD_CONTROL | MOD_ALT, ord("M")),
        ("Shift+Win+F12", MOD_SHIFT | MOD_WIN, 0x7B),
        ("Ctrl+0", MOD_CONTROL, ord("0")),
        ("alt + ctrl + m", MOD_CONTROL | MOD_ALT, ord("M")),
        ("Ctrl+F1", MOD_CONTROL, 0x70),
    ],
)
def test_valid_sd14(text, mods, vk):
    hk = parse_hotkey(text)
    assert hk == Hotkey(mods, vk, text.strip())


@pytest.mark.parametrize(
    "text",
    ["Ctrl+Alt", "Hyper+M", "Ctrl+F13", "Ctrl+MM", "", 123, None, "M", "Ctrl+Ctrl+M",
     "Ctrl++M", "Ctrl+F0", "Ctrl+F01", "Ctrl+é"],
)  # fmt: skip
def test_invalid_sd14(text):
    assert parse_hotkey(text) is None


@pytest.mark.parametrize(
    ("msg", "wp", "cmd"),
    [
        (WM_HOTKEY, 1, "toggle"),
        (WM_POWERBROADCAST, PBT_APMSUSPEND, "suspend"),
        (WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC, "resume"),
        (WM_POWERBROADCAST, PBT_APMRESUMESUSPEND, "resume"),
        (WM_POWERBROADCAST, 0x000A, None),  # PBT_APMPOWERSTATUSCHANGE
        (WM_ENDSESSION, 1, "quit"),
        (WM_ENDSESSION, 0, None),
        (WM_DISPLAYCHANGE, 0, "display_changed"),
        (0xC123, 0, "show"),
        (0x0001, 0, None),
    ],
)
def test_translate(msg, wp, cmd):
    assert translate_message(msg, wp, show_message=0xC123) == cmd


def test_translate_without_show_message():
    assert translate_message(0xC123, 0) is None
