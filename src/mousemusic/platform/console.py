"""Console output for the windowed (PyInstaller ``--windowed``) exe's CLI flags.

A GUI-subsystem exe gets no console, and PyInstaller sets ``sys.stdout``/``sys.stderr`` to
None, so ``--self-test``/``--list-devices``/``--version`` printed nothing from a terminal.
:func:`attach_console` fixes that without a second exe:

1. If the parent redirected our output (``exe --self-test | more``, CI capture), the inherited
   std handles are valid: wrap them.
2. Otherwise ``AttachConsole(ATTACH_PARENT_PROCESS)``; on success write to ``CONOUT$``.
   If there is no parent console (double-click, Explorer), do nothing.

Only streams that are None are rebound, so ``python -m mousemusic`` is untouched.
Everything OS-specific is injectable so this is tested with fakes on any platform.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any

ATTACH_PARENT_PROCESS = -1  # (DWORD)-1
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
INVALID_HANDLE_VALUE = -1
FILE_TYPE_UNKNOWN = 0

# Flags that print and exit; anything else starts the GUI and needs no console.
CLI_FLAGS = frozenset({"--self-test", "--list-devices", "--version", "-h", "--help"})


def wants_console(argv: Sequence[str]) -> bool:
    return any(a in CLI_FLAGS for a in argv)


def _load_kernel32() -> Any:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.AttachConsole.argtypes = [wintypes.DWORD]
    k32.AttachConsole.restype = wintypes.BOOL
    k32.GetStdHandle.argtypes = [wintypes.DWORD]
    k32.GetStdHandle.restype = wintypes.HANDLE
    k32.GetFileType.argtypes = [wintypes.HANDLE]
    k32.GetFileType.restype = wintypes.DWORD
    return k32


def _wrap_handle(handle: int) -> Any:  # pragma: no cover - Windows only
    import msvcrt

    fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
    return os.fdopen(fd, "w", encoding="utf-8", errors="replace", buffering=1)


def _valid(handle: Any) -> bool:
    return handle not in (None, 0, INVALID_HANDLE_VALUE)


def attach_console(
    *,
    platform: str = sys.platform,
    sys_module: Any = sys,
    kernel32: Any = None,
    wrap_handle: Callable[[int], Any] | None = None,
    open_file: Callable[..., Any] = open,
) -> str:
    """Rebind missing stdout/stderr. Returns what happened: ``"skipped"`` (not Windows or
    streams already present), ``"inherited"``, ``"attached"`` or ``"none"``."""
    if platform != "win32":
        return "skipped"
    names = [n for n in ("stdout", "stderr") if getattr(sys_module, n) is None]
    if not names:
        return "skipped"
    k32 = kernel32 if kernel32 is not None else _load_kernel32()
    wrap = wrap_handle or _wrap_handle
    std = {"stdout": STD_OUTPUT_HANDLE, "stderr": STD_ERROR_HANDLE}

    inherited = False
    for name in names:
        h = k32.GetStdHandle(std[name])
        if _valid(h) and k32.GetFileType(h) != FILE_TYPE_UNKNOWN:
            try:
                setattr(sys_module, name, wrap(h))
                inherited = True
            except OSError:
                pass
    names = [n for n in names if getattr(sys_module, n) is None]
    if not names:
        return "inherited"
    if not k32.AttachConsole(ATTACH_PARENT_PROCESS & 0xFFFFFFFF):
        return "inherited" if inherited else "none"  # no parent console: do nothing
    for name in names:
        with contextlib.suppress(OSError):
            stream = open_file("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            setattr(sys_module, name, stream)
            if name == "stdout":
                stream.write("\n")  # start below the prompt the shell already printed
    return "attached"
