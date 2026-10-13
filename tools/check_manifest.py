"""Verify the built exe's embedded manifest declares DPI awareness (CI, Windows only).

python tools/check_manifest.py dist/MouseMusic.exe
"""

from __future__ import annotations

import sys

REQUIRED = ("<dpiAwareness", "PerMonitorV2", "<dpiAware", "true/pm")


def missing(manifest: str) -> list[str]:
    return [r for r in REQUIRED if r not in manifest]


def main(argv: list[str]) -> int:
    from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable

    raw = read_manifest_from_executable(argv[0])
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    print(text)
    gaps = missing(text)
    if gaps:
        print(f"manifest is missing: {gaps}", file=sys.stderr)
        return 1
    print("DPI awareness entries present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
