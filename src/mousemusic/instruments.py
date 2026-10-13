"""General MIDI program names and instrument sets. No platform imports.

Program numbers are 0-based (GM program 1 "Acoustic Grand Piano" is 0 here).

Instrument sets are data, not code: they are loaded from ``data/curation.json`` (curated by P3,
see PR #4). If that file is missing or unusable, the sets from ARCHITECTURE.md §5 are used as a
built-in fallback, so the app always has valid sets. The file is read once, at import.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
            raise ValueError(f"instrument set {self.name!r} has a program outside 0..127")


#: Mirror of data/curation.json (§5 after §11 P3); used only when that file is missing or invalid.
#: tests/test_instruments.py asserts the two stay identical.
BUILTIN_INSTRUMENT_SETS: dict[str, InstrumentSet] = {
    s.name: s
    for s in (
        InstrumentSet("classic", "Classic", (0, 4, 11, 12, 24, 45, 46, 105)),
        InstrumentSet("mellow", "Mellow", (4, 11, 10, 108, 46, 88)),
        InstrumentSet("percussive", "Percussive", (8, 9, 12, 13, 14, 108, 114)),
        InstrumentSet("single_piano", "Piano only", (0,)),
        InstrumentSet("full_gm", "All 128 GM", tuple(range(128))),
    )
}
BUILTIN_DEFAULT_SET = "classic"

_RANGE_RE = re.compile(r"^\s*(\d+)\s*\.\.\s*(\d+)\s*$")


def _parse_programs(value: Any) -> tuple[int, ...]:
    """Accept ``[0, 11, ...]``, ``[{"program": 0, ...}, ...]`` or ``"0..127"``."""
    if isinstance(value, str):
        m = _RANGE_RE.match(value)
        if not m:
            raise ValueError(f"bad program range {value!r}")
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            raise ValueError(f"bad program range {value!r}")
        return tuple(range(lo, hi + 1))
    if not isinstance(value, list):
        raise ValueError("programs must be a list or a 'lo..hi' string")
    out = []
    for item in value:
        p = item.get("program") if isinstance(item, Mapping) else item
        if isinstance(p, bool) or not isinstance(p, int):
            raise ValueError(f"bad program entry {item!r}")
        out.append(p)
    return tuple(out)


def parse_curation(data: Any) -> tuple[dict[str, InstrumentSet], str]:
    """Parse curation JSON into ``(sets, default_set_name)``. Invalid sets are skipped with a
    warning. Raises ValueError if no valid set remains."""
    if not isinstance(data, Mapping) or not isinstance(data.get("instrument_sets"), list):
        raise ValueError("curation data has no 'instrument_sets' list")
    sets: dict[str, InstrumentSet] = {}
    for entry in data["instrument_sets"]:
        try:
            if not isinstance(entry, Mapping):
                raise ValueError("entry is not an object")
            name = entry.get("id")
            if not isinstance(name, str) or not name:
                raise ValueError("missing 'id'")
            if name in sets:
                raise ValueError(f"duplicate id {name!r}")
            label = entry.get("label")
            label = label if isinstance(label, str) and label else name
            sets[name] = InstrumentSet(name, label, _parse_programs(entry.get("programs")))
        except ValueError as exc:
            log.warning("curation: skipping instrument set %r: %s", entry, exc)
    if not sets:
        raise ValueError("curation data has no valid instrument sets")
    default = data.get("default_instrument_set")
    if default not in sets:
        default = BUILTIN_DEFAULT_SET if BUILTIN_DEFAULT_SET in sets else next(iter(sets))
    return sets, default


def curation_path() -> Path:
    """``data/curation.json`` in the PyInstaller bundle or the source checkout."""
    bundle = getattr(sys, "_MEIPASS", None)
    root = Path(bundle) if bundle else Path(__file__).resolve().parents[2]
    return root / "data" / "curation.json"


def load_instrument_sets(path: Path | None = None) -> tuple[dict[str, InstrumentSet], str]:
    """Load sets from ``path`` (default :func:`curation_path`); fall back to the built-ins."""
    path = curation_path() if path is None else path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return parse_curation(data)
    except FileNotFoundError:
        log.info("no %s; using built-in instrument sets", path)
    except (OSError, ValueError) as exc:
        log.warning("could not load %s (%s); using built-in instrument sets", path, exc)
    return dict(BUILTIN_INSTRUMENT_SETS), BUILTIN_DEFAULT_SET


INSTRUMENT_SETS, DEFAULT_INSTRUMENT_SET = load_instrument_sets()


def program_name(program: int) -> str:
    if not 0 <= program <= 127:
        raise ValueError(f"GM program out of range: {program}")
    return GM_PROGRAM_NAMES[program]


def get_instrument_set(name: str) -> InstrumentSet:
    try:
        return INSTRUMENT_SETS[name]
    except KeyError:
        raise ValueError(f"unknown instrument set: {name!r}") from None


def load_scale_order(path: Path | None = None) -> tuple[str, ...]:
    """Scale ids in UI order: friendliest first, from ``scales`` in data/curation.json (§11 P3).
    Unknown ids are dropped, missing ones appended in their default order."""
    from mousemusic.scales import SCALE_LABELS

    path = curation_path() if path is None else path
    order: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.get("scales", []):
            sid = entry.get("id") if isinstance(entry, Mapping) else None
            if sid in SCALE_LABELS and sid not in order:
                order.append(sid)
    except (OSError, ValueError, AttributeError) as exc:
        log.info("scale order: using defaults (%s)", exc)
    return tuple(order + [s for s in SCALE_LABELS if s not in order])
