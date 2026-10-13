"""Pure helpers for the Win32 message window (``win_hotkey.py``): hotkey parsing (§11 OQ-5)
and translating window messages into engine/UI commands (§9, §11 OQ-3). No ctypes here."""

from __future__ import annotations

from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {"CTRL": MOD_CONTROL, "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN}
VK_F1 = 0x70

WM_ENDSESSION = 0x0016
WM_DISPLAYCHANGE = 0x007E
WM_HOTKEY = 0x0312
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012


@dataclass(frozen=True)
class Hotkey:
    modifiers: int  # MOD_* flags, without MOD_NOREPEAT
    vk: int
    text: str


def _vk(key: str) -> int | None:
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        return ord(key)  # VK codes for A-Z and 0-9 equal their ASCII codes
    if key.startswith("F") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 12 and key[1:] == str(n):
            return VK_F1 + n - 1
    return None


def parse_hotkey(text: object) -> Hotkey | None:
    """``"Ctrl+Alt+M"`` → :class:`Hotkey`. Modifiers Ctrl/Alt/Shift/Win (any order, case-
    insensitive, each at most once, at least one) plus exactly one A-Z, 0-9 or F1-F12 key.
    Anything else → None (W4; the default is *not* substituted, §11 OQ-5)."""
    if not isinstance(text, str):
        return None
    parts = [p.strip().upper() for p in text.split("+")]
    if len(parts) < 2 or any(not p for p in parts):
        return None
    *mods, key = parts
    flags = 0
    for m in mods:
        bit = _MODS.get(m)
        if bit is None or flags & bit:
            return None
        flags |= bit
    vk = _vk(key)
    if vk is None:
        return None
    return Hotkey(flags, vk, text.strip())


def translate_message(msg: int, wparam: int, show_message: int | None = None) -> str | None:
    """Window message → command name, or None to ignore.

    ``toggle`` (hotkey), ``suspend``/``resume`` (OQ-3; ``PBT_APMRESUMESUSPEND`` and
    ``PBT_APMRESUMEAUTOMATIC`` both mean resume, the engine ignores the second one),
    ``quit`` (session ending), ``display_changed``, ``show`` (second instance)."""
    if msg == WM_HOTKEY:
        return "toggle"
    if msg == WM_POWERBROADCAST:
        if wparam == PBT_APMSUSPEND:
            return "suspend"
        if wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
            return "resume"
        return None
    if msg == WM_ENDSESSION:
        return "quit" if wparam else None
    if msg == WM_DISPLAYCHANGE:
        return "display_changed"
    if show_message is not None and msg == show_message:
        return "show"
    return None
