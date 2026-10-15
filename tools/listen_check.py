"""Proxy "listen check" (CG-P2): render GM programs with fluidsynth and measure them.

Not a substitute for listening on the Microsoft GS Wavetable Synth. It renders each program with
a GM/GS SoundFont and reports objective proxies: attack, decay, brightness (spectral centroid)
and a harshness proxy.

Usage:  python tools/listen_check.py SOUNDFONT.sf2 [--out DIR] [--clips]
Needs:  fluidsynth on PATH, numpy, scipy.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SR = 44100
VEL = 100  # settings default velocity
CC7 = round(80 * 127 / 100)  # settings default volume 80 %
NOTE_MS = 250  # settings default note_length_ms
TASKBAR_NOTES = [48, 55, 60, 67, 72, 79, 84, 91, 96]  # C3..C7, across the taskbar range
DESKTOP_NOTES = [36, 48, 60, 72, 84, 96]  # C2..C7, the default desktop range
NAMES = {
    0: "Acoustic Grand Piano",
    4: "Electric Piano 1",
    11: "Vibraphone",
    12: "Marimba",
    13: "Xylophone",
    24: "Nylon Guitar",
    45: "Pizzicato Strings",
    46: "Orchestral Harp",
    105: "Banjo",
    108: "Kalimba",
    8: "Celesta",
    9: "Glockenspiel",
    114: "Steel Drums",
    10: "Music Box",
    88: "Pad 1 (new age)",
    14: "Tubular Bells",
}


def vlq(n: int) -> bytes:
    out = [n & 0x7F]
    while n > 0x7F:
        n >>= 7
        out.insert(0, (n & 0x7F) | 0x80)
    return bytes(out)


def smf(events: list[tuple[int, bytes]]) -> bytes:
    """events: (abs_ms, raw message). 1 tick = 1 ms (tempo 500000, division 500)."""
    events = sorted(events, key=lambda e: e[0])
    trk, t = b"", 0
    for ms, msg in events:
        trk += vlq(ms - t) + msg
        t = ms
    trk += vlq(0) + b"\xff\x2f\x00"
    return (
        b"MThd" + struct.pack(">IHHH", 6, 0, 1, 500) + b"MTrk" + struct.pack(">I", len(trk)) + trk
    )


def notes_events(
    ch: int, program: int, notes: list[tuple[int, int, int]]
) -> list[tuple[int, bytes]]:
    """notes: (start_ms, note, length_ms)."""
    ev = [(0, bytes([0xB0 | ch, 7, CC7])), (0, bytes([0xC0 | ch, program]))]
    for start, n, length in notes:
        ev += [
            (start + 20, bytes([0x90 | ch, n, VEL])),
            (start + 20 + length, bytes([0x80 | ch, n, 0])),
        ]
    return ev


def render(sf: str, events: list[tuple[int, bytes]], total_ms: int, wav: Path) -> np.ndarray:
    events = [*events, (total_ms, bytes([0xB0, 121, 0]))]  # pad the end
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        f.write(smf(events))
    subprocess.run(
        [
            "fluidsynth",
            "-ni",
            "-q",
            "-g",
            "0.8",
            "-r",
            str(SR),
            "-R",
            "0",
            "-C",
            "0",
            "-F",
            str(wav),
            sf,
            f.name,
        ],
        check=True,
        capture_output=True,
    )
    _, data = wavfile.read(wav)
    x = data.astype(np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1)
    return x / 32768.0


def envelope(x: np.ndarray, win_ms: float = 5.0) -> np.ndarray:
    w = int(SR * win_ms / 1000)
    n = len(x) // w
    return np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(axis=1) + 1e-12)


def measure(x: np.ndarray) -> dict[str, float]:
    env = envelope(x)
    on = int(np.argmax(env > env.max() * 0.01))
    pk = int(np.argmax(env))
    attack_ms = (int(np.argmax(env[on:] >= 0.9 * env.max()))) * 5.0
    below = np.nonzero(env[pk:] < env.max() * 0.1)[0]  # -20 dB
    decay_ms = (below[0] if len(below) else len(env) - pk) * 5.0
    seg = x[on * 220 : on * 220 + int(SR * NOTE_MS / 1000)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    freqs = np.fft.rfftfreq(len(seg), 1 / SR)
    tot = spec.sum() + 1e-18
    centroid = float((freqs * spec).sum() / tot)
    harsh = float(spec[(freqs >= 2000) & (freqs <= 5000)].sum() / tot)  # ear's most sensitive band
    hf = float(spec[freqs >= 5000].sum() / tot)
    peak_db = float(20 * np.log10(np.abs(x).max() + 1e-12))
    return {
        "attack_ms": attack_ms,
        "decay20_ms": decay_ms,
        "centroid_hz": centroid,
        "harsh_2_5k": harsh,
        "hf_5k": hf,
        "peak_db": peak_db,
    }


def per_program(sf: str, program: int, notes: list[int], tmp: Path) -> dict[str, float]:
    rows = []
    for n in notes:
        x = render(sf, notes_events(0, program, [(0, n, NOTE_MS)]), 1600, tmp / "n.wav")
        rows.append(measure(x))
    return {k: float(np.median([r[k] for r in rows])) for k in rows[0]}


def pair(sf: str, a: int, b: int, notes: list[int], tmp: Path) -> dict[str, float]:
    """Marimba and Xylophone struck together (same note): masking/blend proxy."""
    out = []
    for n in notes:
        ev = notes_events(0, a, [(0, n, NOTE_MS)]) + notes_events(1, b, [(0, n, NOTE_MS)])
        both = render(sf, ev, 1600, tmp / "p.wav")
        xa = render(sf, notes_events(0, a, [(0, n, NOTE_MS)]), 1600, tmp / "a.wav")
        xb = render(sf, notes_events(0, b, [(0, n, NOTE_MS)]), 1600, tmp / "b.wav")
        m = measure(both)
        ma, mb = measure(xa), measure(xb)
        m["centroid_ratio_b_over_a"] = mb["centroid_hz"] / ma["centroid_hz"]
        m["decay_ratio_a_over_b"] = ma["decay20_ms"] / max(mb["decay20_ms"], 1)
        out.append(m)
    return {k: float(np.median([r[k] for r in out])) for k in out[0]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("soundfont")
    ap.add_argument("--out", default="listen-check-out")
    ap.add_argument("--clips", action="store_true", help="also write short demo clips (ogg)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    classic = [0, 4, 11, 12, 24, 45, 46, 105]
    focus = sorted({*classic, 13, 108})
    res: dict = {"soundfont": Path(a.soundfont).name, "taskbar": {}, "desktop": {}, "full_gm": {}}
    for p in focus:
        res["taskbar"][p] = per_program(a.soundfont, p, TASKBAR_NOTES, tmp)
        res["desktop"][p] = per_program(a.soundfont, p, DESKTOP_NOTES, tmp)
    for p in range(128):  # the Full GM library set: rank harshness at C4/C6 only (speed)
        res["full_gm"][p] = per_program(a.soundfont, p, [60, 84], tmp)
    res["pair_12_13"] = pair(a.soundfont, 12, 13, TASKBAR_NOTES, tmp)
    res["pair_108_13"] = pair(a.soundfont, 108, 13, TASKBAR_NOTES, tmp)
    (out / "results.json").write_text(json.dumps(res, indent=1))
    if a.clips:  # a slow taskbar sweep, 10 slots of C pentatonic from C3 at ~4 notes/s
        sweep = [48, 50, 52, 55, 57, 60, 62, 64, 67, 69]
        seq = [(i * 250, n, NOTE_MS) for i, n in enumerate(sweep)]
        for p in (12, 13, 108):
            render(a.soundfont, notes_events(0, p, seq), 3200, tmp / "c.wav")
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp / "c.wav"),
                    "-ac",
                    "1",
                    "-c:a",
                    "libvorbis",
                    "-q:a",
                    "2",
                    str(out / f"sweep-gm{p}.ogg"),
                ],
                check=True,
            )
        ev = notes_events(0, 12, seq) + notes_events(1, 13, [(s + 125, n, ln) for s, n, ln in seq])
        render(a.soundfont, ev, 3400, tmp / "c.wav")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(tmp / "c.wav"),
                "-ac",
                "1",
                "-c:a",
                "libvorbis",
                "-q:a",
                "2",
                str(out / "sweep-gm12-plus-gm13.ogg"),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
