import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "mousemusic.manifest"
spec = importlib.util.spec_from_file_location(
    "check_manifest", ROOT / "tools" / "check_manifest.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_manifest_survives_pyinstaller_merge():
    # The same merge EXE(manifest=...) performs; must keep our windowsSettings.
    from PyInstaller.utils.win32.winmanifest import create_application_manifest

    merged = create_application_manifest(MANIFEST.read_bytes(), False, False).decode("utf-8")
    assert check.missing(merged) == []
    assert "Microsoft.Windows.Common-Controls" in merged  # PyInstaller defaults kept


def test_missing_detects_absent_entries():
    assert check.missing("<assembly/>") == list(check.REQUIRED)


def test_spec_references_manifest():
    assert "manifest=str(MANIFEST)" in (ROOT / "mousemusic.spec").read_text(encoding="utf-8")
