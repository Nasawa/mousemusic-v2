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
