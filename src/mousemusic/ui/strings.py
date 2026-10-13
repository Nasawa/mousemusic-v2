"""User-facing copy, verbatim from docs/ux.md (§4). Edit copy here, not in logic.

Status-line messages that end in a Help link are stored without the trailing ``Help``; the
UI renders the link from the matching ``*_HELP`` anchor (§11 UX-Q7).
"""

from __future__ import annotations

HELP_BASE = "https://github.com/Nasawa/mousemusic-v2#"
ANCHOR_NO_SOUND = "no-sound"
ANCHOR_NO_MIDI_DEVICE = "no-midi-device"
ANCHOR_DEVICE_BUSY = "device-busy"
ANCHOR_SETTINGS_RESET = "settings-reset"


def help_url(anchor: str) -> str:
    return HELP_BASE + anchor


# Errors (red ■)
E1_NO_DEVICE = "No MIDI output found. Install a MIDI synth, then click ⟳."
E1_HELP = ANCHOR_NO_MIDI_DEVICE
E2_DEVICE_BUSY = "{device} is being used by another app. Close it, or pick another output."
E2_HELP = ANCHOR_DEVICE_BUSY
E3_OPEN_FAILED = "Couldn't open {device}. Try ⟳ or pick another output."
E3_HELP = ANCHOR_NO_SOUND
E4_DEVICE_LOST = "Lost connection to {device}. Playback stopped. Click ⟳ to reconnect."
E5_UNEXPECTED = "Something went wrong and playback stopped. Click Start to try again."

# Warnings (amber ▲)
W1_DEVICE_FALLBACK = '"{saved}" not found. Using {device} instead.'
W2_SETTINGS_RESET = (
    "Your settings file couldn't be read, so defaults were restored. "
    "The old file was saved as settings.json.bak."
)
W2_HELP = ANCHOR_SETTINGS_RESET
W3_SETTINGS_CLAMPED = "Some settings were out of range and have been reset."
W4_HOTKEY_OFF = "{hotkey} is in use by another app, so the shortcut is off. Use the Start button."
W5_CANT_SAVE = "Settings can't be saved right now. Changes will last until you quit."

# Fatal (F1, Windows MessageBox before the window exists)
F1_TITLE = "MouseMusic"
F1_TEXT = (
    "MouseMusic couldn't start.\n\nA log was saved to:\n"
    "%LOCALAPPDATA%\\MouseMusic\\logs\\mousemusic.log"
)

# Window (docs/ux.md §1)
WINDOW_TITLE = "MouseMusic"
START = "▶  Start"
STOP = "■  Stop"
SHORTCUT_OFF = "(shortcut off)"
LABEL_SCALE = "Scale"
LABEL_KEY = "Key"
LABEL_RANGE = "Pitch range"
LABEL_RANGE_TO = "to"
LABEL_INSTRUMENTS = "Instruments"
LABEL_VOLUME = "Volume"
LABEL_NOTE_LENGTH = "Note length"
LABEL_LEGATO = "Hold notes (legato)"
LABEL_MIDI = "MIDI output"
RECONNECT_BUTTON = "⟳"
RECONNECT_TOOLTIP = "Reconnect"
INSTRUMENTS_TOOLTIP = "Top of the screen to bottom: {names}"
HELP_LINK = "Help"
VOLUME_VALUE = "{value} %"
NOTE_LENGTH_VALUE = "{value} ms"
KEY_LABELS = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")

# Status line (docs/ux.md §1.3, §3)
STATUS_STOPPED = "Stopped — press Start or {hotkey}"
STATUS_STOPPED_NO_HOTKEY = "Stopped — press Start"
STATUS_PLAYING_IDLE = "Playing — move the mouse · {device}"
STATUS_PLAYING = "{note} · {instrument} · {device}"
STATUS_CONNECTING = "Connecting to {device}…"
STATUS_RECONNECTING = "Reconnecting…"
STATUS_FIRST_RUN = "Click Start, then move your mouse. Left↔right = pitch, up↕down = instrument."
DOT_NORMAL = "●"
DOT_WARNING = "▲"
DOT_ERROR = "■"

# Tray (docs/ux.md §2)
TRAY_TOOLTIP_STOPPED = "MouseMusic v{version} — Stopped"
TRAY_TOOLTIP_PLAYING = "MouseMusic v{version} — Playing"
TRAY_TOOLTIP_ERROR = "MouseMusic v{version} — No sound (click for details)"
TRAY_START = "Start"
TRAY_STOP = "Stop"
TRAY_SHOW = "Show window"
TRAY_QUIT = "Quit"
BALLOON_FIRST_CLOSE_TITLE = "MouseMusic is still running"
BALLOON_FIRST_CLOSE = "It's in the system tray. Right-click the icon to quit."
BALLOON_FIRST_CLOSE_PLAYING = (
    "It's still playing in the system tray. "
    "Press {hotkey} to stop, or right-click the icon to quit."
)
BALLOON_LOST_TITLE = "MouseMusic stopped"
BALLOON_LOST = "Lost connection to {device}. Open MouseMusic from the tray icon."

# Device combobox placeholder when the list is empty
NO_DEVICE_COMBO = "No MIDI output found"

# CLI (--list-devices)
CLI_NO_DEVICES = "No MIDI output devices found."
CLI_DEVICE_LINE = "{index}: {name}"


def midi_error_message(exc: Exception, device: str | None = None) -> tuple[str, str | None]:
    """Status-line text and Help anchor for a MIDI error (E1-E4). Unknown errors → E5."""
    from mousemusic.midi import DeviceBusyError, DeviceLostError, DeviceOpenError, NoDevicesError

    name = getattr(exc, "device", None) or device or "the MIDI output"
    if isinstance(exc, NoDevicesError):
        return E1_NO_DEVICE, E1_HELP
    if isinstance(exc, DeviceBusyError):
        return E2_DEVICE_BUSY.format(device=name), E2_HELP
    if isinstance(exc, DeviceLostError):
        return E4_DEVICE_LOST.format(device=name), None
    if isinstance(exc, DeviceOpenError):
        return E3_OPEN_FAILED.format(device=name), E3_HELP
    return E5_UNEXPECTED, None
