"""Command-line entry point: ``python -m mousemusic``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from mousemusic import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mousemusic",
        description="Cursor position drives MIDI output (X -> pitch, Y -> instrument).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    # App wiring (DPI awareness, single instance, engine, UI) arrives in later tasks (S4-S6).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
