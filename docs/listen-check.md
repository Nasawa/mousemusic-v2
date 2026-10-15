# Listen check (CG-P2): taskbar instruments vs the Classic set

> **Proxy analysis, not a listening test.** No one has listened to these on the Microsoft GS Wavetable Synth. The
> numbers come from rendering with two SoundFonts and measuring the audio. They point in a direction, but **a human
> listen on Windows (GS synth) is still required** before any defaults change.

## Method

- Renderer: `fluidsynth` 2.x, 44.1 kHz, reverb and chorus off. SoundFonts:
  - **GeneralUser GS** (GU, a GS-compatible bank whose patch voicing is close to the Roland-derived GS set behind
    `gm.dls`). This is the primary reference.
  - **FluidR3 GM** (FR), as a cross-check. Microsoft's `gm.dls` itself can't be loaded in fluidsynth here.
- App conditions: velocity 100, CC7 = 102 (volume 80 %), note length 250 ms, monophonic. These are the settings defaults.
- Pitches: the taskbar range C3–C7 (MIDI 48–96, 9 notes), and the default desktop range C2–C7 for the Classic rows.
  The value reported is the median over notes.
- Measures (per note, from a 5 ms RMS envelope and an FFT of the first 250 ms):
  - **Attack:** onset to 90 % of peak. Lower = tracks the cursor better.
  - **Decay:** peak to −20 dB, including the release after note-off at 250 ms. It also tells you whether quickly
    repeated notes will overlap.
  - **Spectral centroid:** brightness.
  - **Harshness proxy:** share of energy in 2–5 kHz (where the ear is most sensitive) plus share above 5 kHz.
- Script: [`tools/listen_check.py`](../tools/listen_check.py). Raw results:
  [`listen-check/results-generaluser-gs.json`](listen-check/results-generaluser-gs.json),
  [`results-fluidr3.json`](listen-check/results-fluidr3.json) and [`candidates.json`](listen-check/candidates.json).
- Clips (GU, ~4 notes/s slow taskbar sweep, mono Ogg, ~20–50 KB each): `listen-check/sweep-gm12.ogg` (Marimba),
  `sweep-gm13.ogg` (Xylophone), `sweep-gm108.ogg` (Kalimba), `sweep-gm12-plus-gm13.ogg` (alternating, offset 125 ms).

## Results

### Classic set and the taskbar defaults (taskbar range C3–C7)

| GM | Instrument | Role | Attack ms (GU / FR) | Decay to −20 dB ms (GU / FR) | Centroid Hz (GU / FR) | Harshness % (GU / FR) |
|---|---|---|---|---|---|---|
| 0 | Acoustic Grand Piano | Classic | 20 / 15 | 320 / 310 | 590 / 1186 | 1.0 / 6.8 |
| 4 | Electric Piano 1 | Classic | 5 / 5 | 280 / 280 | 533 / 547 | 0.0 / 0.0 |
| 11 | Vibraphone | Classic | 35 / 5 | 445 / 330 | 774 / 532 | 0.6 / 0.6 |
| 12 | Marimba | Classic + taskbar default | 20 / 25 | 465 / 285 | 525 / 526 | 0.0 / 0.0 |
| 24 | Nylon Guitar | Classic | 15 / 5 | 285 / 330 | 719 / 1044 | 2.8 / 2.3 |
| 45 | Pizzicato Strings | Classic | 40 / 55 | 110 / 150 | 561 / 669 | 0.4 / 1.0 |
| 46 | Orchestral Harp | Classic | 10 / 5 | 560 / 535 | 720 / 550 | 1.0 / 0.2 |
| 105 | Banjo | Classic | 5 / 5 | 185 / 230 | 1776 / 2358 | 21.2 / 36.5 |
| 13 | Xylophone | secondary taskbar default | 5 / 5 | 140 / 130 | 562 / 613 | 0.2 / 0.6 |
| 108 | Kalimba | candidate | 10 / 5 | 290 / 225 | 524 / 528 | 0.0 / 0.2 |

### Mallet and bell candidates for the taskbar (C3–C7)

| GM | Instrument | Attack ms (GU / FR) | Decay ms (GU / FR) | Centroid Hz (GU / FR) | Harshness % (GU / FR) |
|---|---|---|---|---|---|
| 8 | Celesta | 10 / 10 | 630 / 500 | 525 / 533 | 0.0 / 0.3 |
| 9 | Glockenspiel | 0 / 20 | 555 / 455 | 2077 / 3194 | 4.5 / 22.1 |
| 10 | Music Box | 35 / 55 | 570 / 300 | 756 / 2181 | 0.0 / 37.2 |
| 11 | Vibraphone | 35 / 5 | 445 / 330 | 774 / 532 | 0.6 / 0.6 |
| 12 | Marimba | 20 / 25 | 465 / 285 | 525 / 526 | 0.0 / 0.0 |
| 13 | Xylophone | 5 / 5 | 140 / 130 | 562 / 613 | 0.2 / 0.6 |
| 108 | Kalimba | 10 / 5 | 290 / 225 | 524 / 528 | 0.0 / 0.2 |
| 114 | Steel Drums | 35 / 5 | 225 / 260 | 1622 / 1401 | 42.6 / 22.6 |

### Marimba and Xylophone together

Rendering both together on the same note (GU / FR):
- Xylophone is only **7 % / 17 % brighter** (centroid ratio 1.07 / 1.17). In brightness they're nearly the same.
- Marimba rings **2.6× / 2.1× longer** (decay 465 vs 140 ms in GU). Decay is the main thing that separates them.
- The combination adds no harshness (0 % in 2–5 kHz) and peaks about 6 dB above either alone. In the app they never
  sound together on purpose, since it's monophonic and only one zone is active at a time. The only overlap is a
  Marimba release tail when moving from the primary taskbar to the secondary one.

### "The full set sounds harsh"

- **Full GM library (128):** at C4/C6 the median harshness is 17 % (GU) / 15 % (FR). 44–45 programs exceed 30 %, and
  51–60 have slow attacks (> 60 ms). Sweeping all 128 rows inevitably lands on many harsh or smeary patches. That's
  expected for a "v1 behaviour" set, so it should stay an opt-in.
- **Classic set:** every row is ≤ 3 % (GU) except **Banjo (105): 21 % in GU and 37 % in FR**, the brightest by far
  (centroid 1.8–2.4 kHz versus ~0.5–0.8 kHz for the others). If "full set" means the full Classic sweep, Banjo is the
  likely source of the harshness.

## Findings

1. **Marimba (12) collides with Classic.** It's Classic's row 4, so on the primary taskbar it sounds identical to a
   desktop row and doesn't signal "you're on the taskbar". That was the risk flagged in design #23.
2. **Marimba vs Xylophone are only moderately distinct.** They have similar brightness and differ mainly in decay
   (~2–2.6×). On two adjacent monitors that's probably learnable, but it's not obvious at first.
3. **Xylophone (13)** has the fastest attack (5 ms), the shortest decay (~135 ms, so no smearing on quick hovers), low
   harshness, and isn't in Classic. It's a good primary taskbar voice.
4. **Celesta (8)** has a fast attack, the longest clean ring (500–630 ms), near-zero harshness in both fonts, and isn't
   in Classic. Its decay is ~4× Xylophone's, the biggest non-harsh contrast among the candidates. **Glockenspiel (9)**
   and **Steel Drums (114)** contrast more but are harsh (up to 22 % and 43 %). Music Box (10) is clean in GU but harsh
   (37 %) in FR, so it's risky on an unknown GS voicing.
5. Kalimba (108) is very clean, but it's spectrally almost the same as Marimba. It's a poor contrast partner.

## Recommendation (pending a human listen on Windows)

| Key | Current default | Recommended | Why |
|---|---|---|---|
| `taskbar_program` | 12 Marimba | **13 Xylophone** | Not in Classic, so the taskbar is audibly its own zone. Fastest and cleanest attack |
| `taskbar_secondary_program` | 13 Xylophone | **8 Celesta** | Strongest clean contrast with Xylophone (bell ring vs dry knock). Not in Classic |
| Classic row 8 | 105 Banjo | Consider **108 Kalimba** or 7 Clavinet *(not measured in depth)* | Banjo is the only harsh Classic row, and the likely cause of the "harsh" feedback |

The Percussive set already contains 8, 12 and 13, so any mallet will collide with it. The recommendation prioritises
Classic, the default set.

## Still needed (human, Windows)

- Listen on the **Microsoft GS Wavetable Synth** to: Xylophone vs Celesta on the taskbar, Banjo in Classic, and the
  Classic sweep at the default C2–C7. The GS voicing may differ from both SoundFonts (in particular Celesta's
  octave and Banjo's brightness).
- Confirm with Christopher that "full set" meant Classic (Banjo) or the Full GM library.
