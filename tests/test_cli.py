import subprocess
import sys

import pytest

from mousemusic import __version__
from mousemusic.__main__ import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"mousemusic {__version__}"


def test_no_args_returns_zero():
    assert main([]) == 0


def test_python_dash_m_version():
    out = subprocess.run(
        [sys.executable, "-m", "mousemusic", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"mousemusic {__version__}"
