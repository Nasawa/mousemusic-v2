"""Logging (§4): ``%LOCALAPPDATA%\\MouseMusic\\logs\\mousemusic.log``, rotating 3 x 1 MB."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_BYTES = 1_000_000
BACKUP_COUNT = 2  # the live file + 2 backups = 3 files
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"


def log_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "MouseMusic" / "logs"


def setup_logging(
    level: str = "INFO", directory: Path | None = None, *, console: bool | None = None
) -> Path | None:
    """Configure the root logger. Returns the log file path, or None if it couldn't be created
    (logging then goes to stderr only). Console output is on when running from source."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(FORMAT)
    path: Path | None = (directory or log_dir()) / "mousemusic.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                 encoding="utf-8")  # fmt: skip
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:
        path = None
        print(f"mousemusic: cannot write log file: {exc}", file=sys.stderr)
    if console is None:
        console = not getattr(sys, "frozen", False)
    if console or path is None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return path
