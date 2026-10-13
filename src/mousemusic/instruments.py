"""General MIDI program names and instrument sets. PURE: no I/O, no platform imports.

Program numbers are 0-based (GM program 1 "Acoustic Grand Piano" is 0 here).
"""

from __future__ import annotations

from dataclasses import dataclass

GM_PROGRAM_NAMES: tuple[str, ...] = (
    # Piano
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
    # Chromatic percussion
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    # Organ
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    # Guitar
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
    "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar",
    "Distortion Guitar", "Guitar Harmonics",
    # Bass
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    # Strings
    "Violin", "Viola", "Cello", "Contrabass",
    "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    # Ensemble
    "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
    "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
    # Brass
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
    "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
    # Reed
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet",
    # Pipe
    "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    # Synth lead
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
    "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    # Synth pad
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
    "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    # Synth effects
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    # Ethnic
    "Sitar", "Banjo", "Shamisen", "Koto",
    "Kalimba", "Bagpipe", "Fiddle", "Shanai",
    # Percussive
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    # Sound effects
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
)  # fmt: skip


@dataclass(frozen=True)
class InstrumentSet:
    """A named list of GM programs; rows top -> bottom map to ``programs[0..]``."""

    name: str
    label: str
    programs: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.programs:
            raise ValueError(f"instrument set {self.name!r} has no programs")
        if any(not 0 <= p <= 127 for p in self.programs):
            raise ValueError(
                f"instrument set {self.name!r} has a program outside 0..127"
            )


INSTRUMENT_SETS: dict[str, InstrumentSet] = {
    s.name: s
    for s in (
        InstrumentSet("classic", "Classic", (0, 11, 24, 40, 42, 56, 73, 71)),
        InstrumentSet("mellow", "Mellow", (4, 11, 12, 46, 48, 52, 89)),
        InstrumentSet("percussive", "Percussive", (8, 9, 12, 13, 14, 108, 114)),
        InstrumentSet("single_piano", "Single piano", (0,)),
        InstrumentSet("full_gm", "Full General MIDI", tuple(range(128))),
    )
}

DEFAULT_INSTRUMENT_SET = "classic"


def program_name(program: int) -> str:
    if not 0 <= program <= 127:
        raise ValueError(f"GM program out of range: {program}")
    return GM_PROGRAM_NAMES[program]


def get_instrument_set(name: str) -> InstrumentSet:
    try:
        return INSTRUMENT_SETS[name]
    except KeyError:
        raise ValueError(f"unknown instrument set: {name!r}") from None
