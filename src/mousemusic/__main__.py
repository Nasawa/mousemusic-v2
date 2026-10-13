"""Command-line entry point: ``python -m mousemusic``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence

from mousemusic import __version__
from mousemusic.midi import MidiOut, default_backend
from mousemusic.ui import strings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mousemusic",
        description="Cursor position drives MIDI output (X -> pitch, Y -> instrument).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--list-devices", action="store_true", help="list MIDI output devices and exit"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="check settings, mapping and MIDI enumeration without a window, then exit",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print MIDI messages instead of sending them"
    )
    parser.add_argument(
        "--portable", action="store_true", help="keep settings.json next to the program"
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="log verbosity (default: info)",
    )
    return parser


def self_test(backend_factory: Callable[[], MidiOut] | None = None, out=print) -> int:
    """``--self-test`` (§11): no GUI. Settings round-trip in a temp folder, the mapping for
    every instrument set x scale, and MIDI enumeration (0 devices is fine). Exit 0 = pass."""
    import tempfile
    from dataclasses import replace
    from pathlib import Path

    from mousemusic import config
    from mousemusic.instruments import load_instrument_sets, load_scale_order
    from mousemusic.mapping import Rect, build_grid, map_position

    failures: list[str] = []

    def check(name: str, fn: Callable[[], object]) -> None:
        try:
            fn()
            out(f"PASS {name}")
        except Exception as exc:
            logging.getLogger(__name__).exception("self-test %s failed", name)
            failures.append(name)
            out(f"FAIL {name}: {exc}")

    def settings_round_trip() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / config.SETTINGS_FILE
            want = replace(config.DEFAULTS, volume=42, legato=True)
            config.save(want, path)
            got = config.load_report(path)
            assert got.settings == want and not got.issues, "settings did not round-trip"

    def mapping() -> None:
        rect = Rect(0, 0, 1920, 1080)
        for set_name in load_instrument_sets()[0]:
            for scale in load_scale_order():
                grid = build_grid(scale, "C", 48, 84, set_name)
                for x, y in ((0, 0), (959, 540), (1919, 1079)):
                    note, program = map_position(x, y, rect, grid)
                    assert 0 <= note <= 127 and 0 <= program <= 127, (set_name, scale)

    def midi() -> None:
        names = (backend_factory or default_backend)().list_devices()
        out(f"     {len(names)} MIDI output device(s)")

    check("settings", settings_round_trip)
    check("mapping", mapping)
    check("midi", midi)
    return 1 if failures else 0


def list_devices(backend_factory: Callable[[], MidiOut] | None = None, out=print) -> int:
    """``--list-devices`` (docs/ux.md §4 CLI copy). Never a traceback; always exits 0."""
    try:
        names = (backend_factory or default_backend)().list_devices()
    except Exception:
        logging.getLogger(__name__).exception("enumerating MIDI devices failed")
        names = []
    if not names:
        out(strings.CLI_NO_DEVICES)
    for i, name in enumerate(names):
        out(strings.CLI_DEVICE_LINE.format(index=i, name=name))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_devices:
        return list_devices()
    if args.self_test:
        return self_test()
    from mousemusic.app import Options, run

    return run(Options(dry_run=args.dry_run, portable=args.portable, log_level=args.log_level))


if __name__ == "__main__":
    raise SystemExit(main())
