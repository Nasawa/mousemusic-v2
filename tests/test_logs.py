import logging
from pathlib import Path

from mousemusic import logs


def test_log_dir(tmp_path, monkeypatch):
    assert logs.log_dir({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "MouseMusic" / "logs"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert logs.log_dir({}) == tmp_path / ".cache" / "MouseMusic" / "logs"
    assert logs.log_dir().name == "logs"


def test_setup_rotating(tmp_path):
    path = logs.setup_logging("debug", tmp_path, console=False)
    try:
        assert path == tmp_path / "mousemusic.log"
        fh = logging.getLogger().handlers[0]
        assert fh.maxBytes == 1_000_000 and fh.backupCount == 2
        assert logging.getLogger().level == logging.DEBUG
        logging.getLogger("x").info("hello")
        fh.flush()
        assert "hello" in path.read_text(encoding="utf-8")
    finally:
        logs.setup_logging("WARNING", tmp_path, console=False)
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers.clear()


def test_setup_unwritable_falls_back_to_stderr(tmp_path, capsys):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    try:
        assert logs.setup_logging("INFO", blocker / "sub") is None
        assert "cannot write log file" in capsys.readouterr().err
        assert isinstance(logging.getLogger().handlers[-1], logging.StreamHandler)
    finally:
        logging.getLogger().handlers.clear()
