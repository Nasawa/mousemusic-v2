import pytest

from mousemusic.midi import DeviceBusyError, DeviceLostError, DeviceOpenError, NoDevicesError
from mousemusic.ui import strings


def test_exact_copy_from_ux_doc():
    assert strings.E1_NO_DEVICE == "No MIDI output found. Install a MIDI synth, then click ⟳."
    assert strings.CLI_NO_DEVICES == "No MIDI output devices found."
    assert strings.help_url(strings.E1_HELP) == (
        "https://github.com/Nasawa/mousemusic-v2#no-midi-device"
    )


@pytest.mark.parametrize(
    ("exc", "text", "anchor"),
    [
        (NoDevicesError("x"), "No MIDI output found. Install a MIDI synth, then click ⟳.",
         "no-midi-device"),
        (DeviceBusyError("x", device="GS"),
         "GS is being used by another app. Close it, or pick another output.", "device-busy"),
        (DeviceOpenError("x", device="GS"), "Couldn't open GS. Try ⟳ or pick another output.",
         "no-sound"),
        (DeviceLostError("x", device="GS"),
         "Lost connection to GS. Playback stopped. Click ⟳ to reconnect.", None),
        (RuntimeError("x"),
         "Something went wrong and playback stopped. Click Start to try again.", None),
    ],
)  # fmt: skip
def test_midi_error_message(exc, text, anchor):
    assert strings.midi_error_message(exc) == (text, anchor)


def test_midi_error_message_device_fallback():
    assert strings.midi_error_message(DeviceBusyError("x"), device="Synth")[0].startswith("Synth ")
