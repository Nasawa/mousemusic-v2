# Instrument & scale curation (P3)

Data: [`data/curation.json`](../data/curation.json). Set and scale ids match `ARCHITECTURE.md` §4/§5, so S2's
`instruments.py` and `scales.py` can mirror it directly. GM program numbers are 0-based.

## Selection rules
Continuous cursor input fires up to ~33 notes/s (30 ms rate limit, §5), so on the Microsoft GS Wavetable Synth an
instrument must:
1. **Speak instantly.** Fast attack. Bowed strings (Violin 40, Cello 42), Choir (52) and most pads (89 Warm Pad) fade in
   over 100 ms+ on the GS synth and smear into mush, so they were removed.
2. **Decay on its own.** Plucked, struck or mallet sounds stay clean at 250 ms notes and in legato.
3. **Contrast with neighbours.** Adjacent rows must sound clearly different, so the Y position is learnable by ear (the
   point of the sensory-substitution goal).
4. **Avoid harsh or loop-artifact patches** on the GS bank (sax, organs, leads).

## Changes vs ARCHITECTURE.md §5
| Set | Removed | Added | Why |
|---|---|---|---|
| classic | 40 Violin, 42 Cello, 56 Trumpet, 73 Flute, 71 Clarinet | 4 E.Piano 1, 12 Marimba, 45 Pizzicato, 46 Harp, 105 Banjo | Slow sustained attacks replaced with plucked or struck sounds |
| mellow | 48 Strings, 52 Choir Aahs, 89 Warm Pad, 12 Marimba | 10 Music Box, 108 Kalimba, 88 New Age Pad | Pads and choir smear. New Age has a bell attack. Now 6 rows |
| percussive | — | — | Already ideal |
| single_piano, full_gm | — | — | Unchanged |

Reasons for each instrument are in the JSON. Scale defaults are unchanged: Pentatonic major in C, because every note sounds
consonant with every other.

## Scales
| Label | Intervals | Reason |
|---|---|---|
| Pentatonic major (default) | 0 2 4 7 9 | No semitone clashes, so any sweep sounds pleasant |
| Pentatonic minor | 0 3 5 7 10 | Same safety, darker mood |
| Major | 0 2 4 5 7 9 11 | Familiar, finer pitch steps |
| Minor | 0 2 3 5 7 8 10 | Sadder colour, still easy on the ear |
| Blues | 0 3 5 6 7 10 | Characterful, rarely harsh |
| Chromatic | 0–11 | Most precise for position, but clashes a lot |

UI order follows this table (friendliest first), not the order in ARCHITECTURE.md §2. Sprite/Archimedes, please confirm.

## Not yet verified
These choices are based on how GM/GS patches are known to behave. **No one has listen-tested them on real hardware yet.**
A listen pass on Windows (Grace, G4) should confirm them, especially Banjo (105) and New Age Pad (88).
