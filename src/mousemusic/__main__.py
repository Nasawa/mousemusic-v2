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
    return parser


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
    # App wiring (DPI awareness, single instance, engine, UI) arrives in later tasks (S4-S6).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
