"""Real WinMM smoke test (§8): opens the GS synth and plays one note. Grace's machine only;
skipped off Windows and when no MIDI output exists (CI runners)."""

import sys
import time

import pytest

pytestmark = [
    pytest.mark.windows_audio,
    pytest.mark.skipif(sys.platform != "win32", reason="WinMM is Windows-only"),
]


def test_play_one_note():  # pragma: no cover - needs real hardware
    from mousemusic.midi import MidiOutput, note_on, program_change
    from mousemusic.midi.winmm import WinMMBackend

    backend = WinMMBackend()
    if not backend.list_devices():
        pytest.skip("no MIDI output devices")
    out = MidiOutput(backend)
    out.open("Microsoft GS Wavetable Synth", volume=80)
    try:
        out.send(*program_change(0))
        out.send(*note_on(60, 100))
        time.sleep(0.3)
    finally:
        out.close(sounding_note=60)
