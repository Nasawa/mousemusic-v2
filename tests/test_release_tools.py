import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release", ROOT / "tools" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize(
    ("tag", "version", "pre", "nums"),
    [
        ("v0.1.0", "0.1.0", False, (0, 1, 0, 0)),
        ("v1.12.3", "1.12.3", False, (1, 12, 3, 0)),
        ("v0.1.0-rc1", "0.1.0-rc1", True, (0, 1, 0, 0)),
        ("v2.0.0-beta.2", "2.0.0-beta.2", True, (2, 0, 0, 0)),
    ],
)
def test_parse_tag(tag, version, pre, nums):
    assert release.parse_tag(tag) == (version, pre, nums)


@pytest.mark.parametrize("bad", ["0.1.0", "v0.1", "v0.1.0-", "vx.1.0", "v0.1.0+meta"])
def test_parse_tag_rejects(bad):
    with pytest.raises(ValueError):
        release.parse_tag(bad)


def test_stamp_and_version_info(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text('"""doc"""\n\n__version__ = "0.0.0"\n', encoding="utf-8")
    info = tmp_path / "pk" / "version_info.txt"
    assert release.stamp("v0.2.0-rc3", init, info) == "0.2.0-rc3"
    assert release.current_version(init) == "0.2.0-rc3"
    text = info.read_text(encoding="utf-8")
    assert "filevers=(0, 2, 0, 0)" in text and "'ProductVersion', '0.2.0-rc3'" in text
    compile(text.split("\n", 1)[1], "version_info", "eval")  # PyInstaller evals this


def test_stamp_without_version_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        release.stamp("v1.0.0", init, tmp_path / "v.txt")
    with pytest.raises(ValueError):
        release.current_version(init)


def test_sha256sums(tmp_path):
    a = tmp_path / "a.exe"
    a.write_bytes(b"abc")
    b = tmp_path / "b.zip"
    b.write_bytes(b"")
    out = release.sha256sums([a, b])
    assert out.read_text(encoding="utf-8") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  a.exe\n"
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  b.zip\n"
    )


def test_main(capsys, tmp_path, monkeypatch):
    assert release.main([]) == 2
    assert release.main(["nope"]) == 2
    assert release.main(["meta", "v0.1.0-rc1"]) == 0
    assert capsys.readouterr().out.endswith("version=0.1.0-rc1\nprerelease=true\n")
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert release.main(["sums", str(f)]) == 0
    monkeypatch.setattr(release, "VERSION_INFO", tmp_path / "vi.txt")
    monkeypatch.setattr(release.write_version_info, "__defaults__", (tmp_path / "vi.txt",))
    assert release.main(["version-info"]) == 0
    assert (tmp_path / "vi.txt").is_file()
    init = tmp_path / "i.py"
    init.write_text('__version__ = "0"\n')
    monkeypatch.setattr(release.stamp, "__defaults__", (init, tmp_path / "vi2.txt"))
    assert release.main(["stamp", "v3.0.0"]) == 0
    assert release.current_version(init) == "3.0.0"
