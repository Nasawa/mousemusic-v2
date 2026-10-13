from mousemusic import app
from mousemusic.ui import strings
from mousemusic.ui.tray import STATES, icon_paths, menu_spec


def test_menu_spec_order_and_default():
    assert menu_spec(False) == [
        ("Start", "toggle", False),
        ("Show window", "show", True),
        ("-", "", False),
        ("Quit", "quit", False),
    ]
    assert menu_spec(True)[0] == (strings.TRAY_STOP, "toggle", False)


def test_state_icons_exist_in_assets():
    paths = icon_paths(app.assets_dir() / "icons")
    assert set(paths) == set(STATES)
    for p in paths.values():
        assert p.is_file(), p
