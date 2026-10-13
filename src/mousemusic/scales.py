"""Scale interval tables and note naming. PURE: no I/O, no platform imports."""

from __future__ import annotations

NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

#: Semitone offsets from the root, ascending, within one octave.
SCALES: dict[str, tuple[int, ...]] = {
    "chromatic": tuple(range(12)),
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),  # natural minor (Aeolian)
    "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
}

#: Display labels for the UI, in the order listed in ARCHITECTURE.md §2.
SCALE_LABELS: dict[str, str] = {
    "chromatic": "Chromatic",
    "major": "Major",
    "minor": "Minor",
    "pentatonic_major": "Pentatonic major",
    "pentatonic_minor": "Pentatonic minor",
    "blues": "Blues",
}

_FLATS = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}

MIDI_MIN = 0
MIDI_MAX = 127


def root_pitch_class(root: str) -> int:
    """Return 0-11 for a root name such as ``"C"``, ``"F#"`` or ``"Bb"``."""
    key = root.strip().upper()
    key = _FLATS.get(key, key)
    try:
        return NOTE_NAMES.index(key)
    except ValueError:
        raise ValueError(f"unknown root note: {root!r}") from None


def note_name(note: int) -> str:
    """MIDI note number to scientific pitch name; 60 -> ``"C4"``."""
    if not MIDI_MIN <= note <= MIDI_MAX:
        raise ValueError(f"MIDI note out of range: {note}")
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def scale_notes(
    scale: str, root: str, low_note: int, high_note: int
) -> tuple[int, ...]:
    """All notes of ``scale`` in ``root`` within ``low_note..high_note`` (inclusive), ascending.

    Example: C pentatonic major from 36 to 96 gives 26 notes.
    """
    try:
        intervals = SCALES[scale]
    except KeyError:
        raise ValueError(f"unknown scale: {scale!r}") from None
    if not (MIDI_MIN <= low_note <= MIDI_MAX and MIDI_MIN <= high_note <= MIDI_MAX):
        raise ValueError(f"note range must be within 0..127: {low_note}..{high_note}")
    if low_note > high_note:
        raise ValueError(f"low_note {low_note} is above high_note {high_note}")
    pcs = {(root_pitch_class(root) + i) % 12 for i in intervals}
    return tuple(n for n in range(low_note, high_note + 1) if n % 12 in pcs)
