"""App/window icon wiring (P2 assets). Without this, Tk shows its default "feather" icon.

- ``set_app_user_model_id()`` must run before the first window exists, so the Windows taskbar
  groups the window under MouseMusic (and uses its icon) instead of python/pythonw/Tk.
- ``apply_window_icon(root)`` sets ``iconbitmap(default=icon.ico)`` on Windows (so every
  Toplevel inherits it), then also ``iconphoto(True, <PNGs>)`` as a cross-platform fallback.
  It never raises: a missing asset just leaves Tk's default icon and logs a warning.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = "Nasawa.MouseMusic"
PHOTO_SIZES: tuple[int, ...] = (256, 64, 48, 32, 16)  # largest first; Tk picks per use


def asset_candidates() -> list[Path]:
    """Where ``assets/`` can live, in priority order."""
    out: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:  # PyInstaller onefile (temp dir) and onedir (_internal)
        out.append(Path(meipass) / "assets")
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / "assets")
    # Package data (src/mousemusic/assets/): the same path from a source checkout, an editable
    # install and a regular `pip install`, so it must come last (find_assets_dir's fallback).
    out.append(Path(__file__).resolve().parents[1] / "assets")
    return out


def find_assets_dir(candidates: Sequence[Path] | None = None) -> Path:
    """First candidate that contains ``icon.ico``; else the last one (the package's own)."""
    cands = list(candidates) if candidates is not None else asset_candidates()
    for c in cands:
        if (c / "icon.ico").is_file():
            return c
    log.warning("icon assets not found in any of: %s", ", ".join(map(str, cands)))
    return cands[-1]


def png_paths(assets: Path) -> list[Path]:
    return [p for s in PHOTO_SIZES if (p := assets / "icons" / "png" / f"app-{s}.png").is_file()]


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    if sys.platform != "win32":
        return False
    try:  # pragma: no cover - Windows only
        import ctypes

        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
        return hr == 0
    except Exception:  # pragma: no cover
        log.warning("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)
        return False


def apply_window_icon(
    root: Any, assets: Path | None = None, *, windows: bool | None = None
) -> list[str]:
    """Apply the app icon to ``root`` and all future Toplevels. Returns the methods that worked."""
    assets = assets or find_assets_dir()
    windows = sys.platform == "win32" if windows is None else windows
    applied: list[str] = []
    ico = assets / "icon.ico"
    if windows and ico.is_file():
        try:
            root.iconbitmap(default=str(ico))
            applied.append("iconbitmap")
        except Exception:
            log.warning("iconbitmap(%s) failed", ico, exc_info=True)
    pngs = png_paths(assets)
    if pngs:
        try:
            import tkinter as tk

            photos = [tk.PhotoImage(master=root, file=str(p)) for p in pngs]
            root.iconphoto(True, *photos)
            root._mm_icon_photos = photos  # keep references alive (Tk drops GC'd images)
            applied.append("iconphoto")
        except Exception:
            log.warning("iconphoto fallback failed", exc_info=True)
    if not applied:
        log.warning("no app icon applied; Tk default icon will show (assets=%s)", assets)
    return applied
