import json
import sys
from pathlib import Path

import pytest

from mousemusic import instruments
from mousemusic.instruments import (
    BUILTIN_DEFAULT_SET,
    BUILTIN_INSTRUMENT_SETS,
    DEFAULT_INSTRUMENT_SET,
    GM_PROGRAM_NAMES,
    INSTRUMENT_SETS,
    InstrumentSet,
    get_instrument_set,
    load_instrument_sets,
    parse_curation,
    program_name,
)

PR4 = Path(__file__).parent / "data" / "curation_pr4.json"

SPEC_SETS = {
    "classic": (0, 11, 24, 40, 42, 56, 73, 71),
    "mellow": (4, 11, 12, 46, 48, 52, 89),
    "percussive": (8, 9, 12, 13, 14, 108, 114),
    "single_piano": (0,),
    "full_gm": tuple(range(128)),
}


def test_gm_has_128_unique_names():
    assert len(GM_PROGRAM_NAMES) == 128
    assert len(set(GM_PROGRAM_NAMES)) == 128


@pytest.mark.parametrize(("name", "programs"), sorted(SPEC_SETS.items()))
def test_builtin_sets_match_spec(name, programs):
    s = BUILTIN_INSTRUMENT_SETS[name]
    assert s.name == name
    assert s.programs == programs
    assert s.label


def test_builtin_no_extra_sets_and_default():
    assert set(BUILTIN_INSTRUMENT_SETS) == set(SPEC_SETS)
    assert BUILTIN_DEFAULT_SET == "classic"


def test_module_sets_come_from_loader():
    assert load_instrument_sets() == (INSTRUMENT_SETS, DEFAULT_INSTRUMENT_SET)
    assert DEFAULT_INSTRUMENT_SET in INSTRUMENT_SETS
    assert get_instrument_set(DEFAULT_INSTRUMENT_SET) is INSTRUMENT_SETS[DEFAULT_INSTRUMENT_SET]


def test_pr4_curation_shape():
    sets, default = load_instrument_sets(PR4)
    assert default == "classic"
    assert set(sets) == set(SPEC_SETS)
    assert sets["classic"].programs == (0, 4, 11, 12, 24, 45, 46, 105)
    assert sets["mellow"].programs == (4, 11, 10, 108, 46, 88)
    assert sets["single_piano"].label == "Piano only"
    assert sets["full_gm"].programs == tuple(range(128))


def test_plain_int_lists_and_label_fallback():
    sets, default = parse_curation(
        {"instrument_sets": [{"id": "a", "programs": [1, 2]}], "default_instrument_set": "zz"}
    )
    assert sets["a"] == InstrumentSet("a", "a", (1, 2)) and default == "a"


def test_invalid_entries_skipped(caplog):
    data = {
        "default_instrument_set": "ok",
        "instrument_sets": [
            "nope",
            {"programs": [1]},
            {"id": "badrange", "programs": "5..1"},
            {"id": "badstr", "programs": "lots"},
            {"id": "badtype", "programs": 3},
            {"id": "badentry", "programs": [{"program": "x"}]},
            {"id": "boolentry", "programs": [True]},
            {"id": "outofrange", "programs": [200]},
            {"id": "empty", "programs": []},
            {"id": "ok", "label": "OK", "programs": " 0 .. 2 "},
            {"id": "ok", "programs": [9]},
        ],
    }
    sets, default = parse_curation(data)
    assert list(sets) == ["ok"] and sets["ok"].programs == (0, 1, 2) and default == "ok"
    assert caplog.text.count("skipping") == 10


@pytest.mark.parametrize("data", [None, [], {}, {"instrument_sets": {}}, {"instrument_sets": []}])
def test_unusable_curation_raises(data):
    with pytest.raises(ValueError):
        parse_curation(data)


@pytest.mark.parametrize("content", [None, "{bad", '{"instrument_sets": []}', b"\xff\xfe"])
def test_loader_falls_back_to_builtin(tmp_path, content):
    p = tmp_path / "curation.json"
    if isinstance(content, str):
        p.write_text(content, encoding="utf-8")
    elif content is not None:
        p.write_bytes(content)
    assert load_instrument_sets(p) == (BUILTIN_INSTRUMENT_SETS, BUILTIN_DEFAULT_SET)


def test_curation_path_source_and_bundle(monkeypatch, tmp_path):
    assert instruments.curation_path().parts[-2:] == ("data", "curation.json")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert instruments.curation_path() == tmp_path / "data" / "curation.json"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "curation.json").write_text(
        json.dumps({"instrument_sets": [{"id": "x", "programs": [7]}]})
    )
    assert load_instrument_sets()[0]["x"].programs == (7,)


@pytest.mark.parametrize(
    ("p", "name"),
    [(0, "Acoustic Grand Piano"), (11, "Vibraphone"), (24, "Acoustic Guitar (nylon)"),
     (40, "Violin"), (42, "Cello"), (56, "Trumpet"), (71, "Clarinet"), (73, "Flute"),
     (89, "Pad 2 (warm)"), (108, "Kalimba"), (114, "Steel Drums"), (127, "Gunshot")],
)  # fmt: skip
def test_program_names(p, name):
    assert program_name(p) == name


@pytest.mark.parametrize("p", [-1, 128])
def test_program_name_out_of_range(p):
    with pytest.raises(ValueError):
        program_name(p)


def test_unknown_set():
    with pytest.raises(ValueError):
        get_instrument_set("kazoo")


@pytest.mark.parametrize("programs", [(), (128,), (-1,)])
def test_invalid_set(programs):
    with pytest.raises(ValueError):
        InstrumentSet("bad", "Bad", programs)
