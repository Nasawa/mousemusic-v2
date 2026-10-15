"""Main-window tests. Need a display: run under ``xvfb-run`` on Linux CI; skipped otherwise."""

import queue
import tkinter as tk

import pytest

from mousemusic.config import DEFAULTS
from mousemusic.engine import Event
from mousemusic.mapping import Rect
from mousemusic.midi import NoDevicesError
from mousemusic.ui import strings
from mousemusic.ui.controller import AppController
from mousemusic.ui.window import MainWindow, TkCursorCache, Tooltip
from test_controller import GS, Clock, FakeEngine, FakeSaver


@pytest.fixture(scope="session")
def tk_session():
    # One Tcl interpreter per session: creating many tk.Tk() instances is flaky on Windows
    # runners ("Can't find a usable tk.tcl"), so each test gets a Toplevel instead.
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def root(tk_session):
    top = tk.Toplevel(tk_session)
    top.withdraw()
    yield top
    top.destroy()


class FakeTray:
    def __init__(self):
        self.updates, self.notes, self.stopped = [], [], 0

    def update(self, state, tooltip, playing):
        self.updates.append((state, tooltip, playing))

    def notify(self, title, text):
        self.notes.append((title, text))

    def stop(self):
        self.stopped += 1


def build(root, settings=DEFAULTS, devices=(GS,), tray=True, **kw):
    dev = list(devices)
    e, s, c = FakeEngine(), FakeSaver(), Clock()
    ctl = AppController(settings, e, s, lambda: dev, c)
    q = queue.Queue()
    urls = []
    t = FakeTray() if tray else None
    w = MainWindow(root, ctl, ui_queue=q, tray=t, version="2.0.0", open_url=urls.append, **kw)
    ctl.startup()
    w.refresh()
    root.update()
    return w, ctl, e, q, urls, dev


def test_layout_labels_and_initial_focus(root):
    w, *_ = build(root)
    assert w.start_btn.cget("text") == strings.START
    assert w.hint.cget("text") == "Ctrl+Alt+M"
    assert w.root.title() == "MouseMusic"
    assert w.device.get() == GS
    assert w.volume_label.cget("text") == f"{DEFAULTS.volume} %"
    w.show_window()
    root.update()
    assert w.root.focus_lastfor() is w.start_btn  # Start gets focus when the window shows
    assert not w.root.resizable()[0]


def test_tab_order_follows_ux(root):
    w, *_ = build(root)
    w.show_window()
    root.update()

    # Tk's Tab traversal follows widget stacking (creation) order; walk it like tk_focusNext.
    def walk(widget):
        for child in widget.winfo_children():
            if str(child.cget("takefocus")) != "0" and child.winfo_class() in (
                "TButton", "TCombobox", "TScale", "TCheckbutton",
            ):  # fmt: skip
                yield child
            yield from walk(child)

    chain = list(walk(root))
    expected = [w.start_btn, w.scale, w.key, w.low, w.high, w.instruments, w.volume,
                w.note_length, w.legato, w.device, w.reconnect, w.hotkey, w.theme]  # fmt: skip
    assert chain == expected


def test_toggle_and_status_from_events(root):
    w, _ctl, e, q, *_ = build(root)
    w.start_btn.invoke()
    assert e.posted[-1][0] == "start"
    q.put(("event", Event("started", {"device": GS, "fallback": False})))
    w.drain()
    assert w.start_btn.cget("text") == strings.STOP
    assert w.tray.updates[-1][0] == "playing"
    q.put(("event", Event("note", {"note": 60, "program": 0})))
    w.drain()
    assert w.status.cget("text").startswith("C4 · ")


def test_e1_disables_start_and_shows_help_link(root):
    w, _ctl, _e, q, urls, dev = build(root, devices=())
    assert "disabled" in w.start_btn.state()
    assert "disabled" in w.device.state()
    assert w.device.get() == strings.NO_DEVICE_COMBO
    assert w.dot.cget("text") == strings.DOT_ERROR
    assert w.help.winfo_manager() == "grid"
    w.open_help()
    assert urls == [strings.help_url(strings.ANCHOR_NO_MIDI_DEVICE)]
    q.put(("event", Event("error", {"error": NoDevicesError("none")})))
    w.drain()
    dev.append(GS)
    w._on_device_dropdown()
    w.refresh()
    assert "disabled" not in w.start_btn.state()


def test_combobox_selection_updates_settings(root):
    w, ctl, *_ = build(root)
    opts = ctl.scale_options()
    w.scale.current(len(opts) - 1)
    w.scale.event_generate("<<ComboboxSelected>>")
    root.update()
    assert ctl.settings.scale == opts[-1].value == "chromatic"
    assert "disabled" in w.key.state()
    w.instruments.current(0)
    w.instruments.event_generate("<<ComboboxSelected>>")
    w.low.current(0)
    w.low.event_generate("<<ComboboxSelected>>")
    w.high.current(len(w.high.cget("values")) - 1)
    w.high.event_generate("<<ComboboxSelected>>")
    root.update()
    assert ctl.settings.low_note == 12 and ctl.settings.high_note == 108


def test_key_combo_and_legato(root):
    w, ctl, *_ = build(root)
    w.key.current(2)
    w.key.event_generate("<<ComboboxSelected>>")
    root.update()
    assert ctl.settings.root == "D"
    w.legato.invoke()
    assert ctl.settings.legato
    assert "disabled" in w.note_length.state()


def test_slider_keys(root):
    w, ctl, _e, *_ = build(root)
    v = ctl.settings.volume
    w.show_window()
    w.volume.focus_force()
    root.update()
    w.volume.event_generate("<Right>")
    w.volume.event_generate("<Prior>")
    root.update()
    assert ctl.settings.volume == min(100, v + 11)
    w.note_length.focus_force()
    root.update()
    w.note_length.event_generate("<Next>")
    root.update()
    assert ctl.settings.note_length_ms == DEFAULTS.note_length_ms - 100
    w._slider(ctl.set_volume, "30.0")
    assert ctl.settings.volume == 30


def test_close_hides_to_tray_and_escape(root):
    w, ctl, *_ = build(root)
    w.show_window()
    root.update()
    w.close()
    assert ctl.hidden and w.tray.notes  # first-close balloon
    w.show_window()
    w.close(balloon=False)
    assert ctl.hidden


def test_close_without_tray_quits(root):
    w, ctl, e, *_ = build(root, tray=False)
    w.close()
    assert ctl.quitting and e.shut == 1


def test_queue_quit_stops_drain(root):
    w, ctl, e, q, *_ = build(root)
    q.put(("quit", None))
    q.put(("toggle", None))
    w.drain()
    assert ctl.quitting and w.tray.stopped == 1
    assert ("start", None) not in e.posted


def test_polling_loop_runs_and_cancels(root):
    w, _ctl, *_ = build(root)
    w.start_polling()
    root.after(120, root.quit)
    root.mainloop()
    assert w._after_id is not None
    w.quit_app()
    assert w._after_id is None


def test_window_position_restore_and_offscreen(root):
    s = DEFAULTS.replace(window_x=10, window_y=20)
    w, *_ = build(root, settings=s, monitors=lambda: [Rect(0, 0, 1920, 1080)])
    assert w.placed == (10, 20)
    r2 = tk.Toplevel(root.master)
    try:
        w2, *_ = build(r2, settings=s, monitors=lambda: [Rect(5000, 0, 1920, 1080)])
        assert w2.placed != (10, 20)
    finally:
        r2.destroy()


def test_window_moved_saves(root):
    w, ctl, *_ = build(root)
    w.show_window()
    root.update()
    w.placed = (-1, -1)

    class Ev:
        widget = root

    w._on_configure(Ev())
    assert ctl.settings.window_x == root.winfo_x()


def test_tooltip_and_cursor_cache(root):
    w, ctl, *_ = build(root)
    w.show_window()
    root.update()
    tip = Tooltip(w.reconnect, "Reconnect")
    tip.show()
    tip.show()
    assert tip.tip is not None
    tip.hide()
    assert tip.tip is None
    assert w.instruments_tip.current_text() == ctl.instrument_tooltip()
    cache = TkCursorCache()
    assert cache.position() is None
    cache.update(root)
    assert cache.virtual_rect() == cache.primary_rect() and cache.position() is not None


def test_window_position_clamped_onto_visible_monitor(root):
    # Saved position hangs off the right edge of a 1920x1080 monitor: pulled fully onto it.
    s = DEFAULTS.replace(window_x=1900, window_y=-50)
    w, *_ = build(root, settings=s, monitors=lambda: [Rect(0, 0, 1920, 1080)])
    ww, _wh = w.size()
    assert w.placed == (1920 - ww, 0)


def test_window_monitor_enumeration_failure_falls_back(root):
    def boom():
        raise OSError("no monitors")

    w, *_ = build(root, settings=DEFAULTS.replace(window_x=10, window_y=10), monitors=boom)
    assert w.placed == (10, 10)


def test_long_warning_wraps_and_window_grows(root):
    w, ctl, *_ = build(root, settings=DEFAULTS.replace(first_run_done=True))
    base = w.height
    width, _ = w.size()
    ctl.status.add_warning("W4", strings.W4_HOTKEYS_OFF.format(
        hotkey="Ctrl+Alt+M", fallback="Ctrl+Alt+Shift+M"), 0, duration=None)  # fmt: skip
    w.refresh()
    root.update_idletasks()
    wrap = int(str(w.status.cget("wraplength")))
    assert 0 < wrap <= width
    assert w.status.winfo_reqwidth() <= wrap + 2  # text wrapped, not clipped at the edge
    assert w.height >= root.winfo_reqheight()  # everything fits vertically
    assert w.height >= base
    # back to a short status: shrinks to the minimum again
    ctl.status.clear_warning("W4")
    w.refresh()
    assert w.height == max(w.size()[1], root.winfo_reqheight())


def test_hotkey_picker(root):
    w, ctl, *_ = build(root)
    labels = list(w.hotkey.cget("values"))
    assert labels[0] == "Ctrl+Alt+M" and labels[-1] == "Off"
    w.hotkey.current(labels.index("Ctrl+Alt+P"))
    w.hotkey.event_generate("<<ComboboxSelected>>")
    root.update()
    assert ctl.settings.hotkey == "Ctrl+Alt+P"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_palette_applied(root, theme):
    from mousemusic.ui.theme import PALETTES

    calls = []
    w, _ctl, *_ = build(root, settings=DEFAULTS.replace(theme=theme),
                       title_bar=lambda r, dark: calls.append(dark))  # fmt: skip
    p = PALETTES[theme]
    assert w.applied_theme == theme and calls[-1] == (theme == "dark")
    assert w.style.theme_use() == "clam"
    assert str(root.cget("bg")).upper() == p["bg"]
    assert str(w.style.lookup("Hint.TLabel", "foreground")).upper() == p["text_secondary"]
    assert str(w.style.lookup("Accent.TButton", "background")).upper() == p["accent"]
    assert str(w.style.lookup("Link.TLabel", "foreground")).upper() == p["link"]
    assert str(w.dot.cget("foreground")).upper() == p["dot_idle"]
    assert w.start_btn.cget("style") == "Accent.TButton"
    pd = root.tk.call("ttk::combobox::PopdownWindow", w.scale)
    assert str(root.tk.call(f"{pd}.f.l", "cget", "-background")).upper() == p["surface"]


def test_live_theme_switch_and_high_contrast(root):
    probe = [(True, False)]
    dev = [GS]
    from mousemusic.ui.controller import AppController as AC

    ctl = AC(DEFAULTS, FakeEngine(), FakeSaver(), lambda: dev, Clock(),
             theme_probe=lambda: probe[-1])  # fmt: skip
    w = MainWindow(root, ctl, tray=FakeTray(), open_url=lambda u: None)
    ctl.startup()
    assert w.applied_theme == "light"
    assert list(w.theme.cget("values")) == ["System (Light)", "Light", "Dark"]
    probe.append((False, False))  # Windows switched to dark
    ctl.clock.t = 5
    ctl.dispatch(("theme_changed", None))
    assert w.applied_theme == "dark" and w.theme.get() == "System (Dark)"
    probe.append((False, True))  # high contrast on
    ctl.clock.t = 6
    w._on_focus_in(type("E", (), {"widget": root})())
    assert w.applied_theme == "high_contrast"
    assert w.style.theme_use() != "clam"
    assert ctl.theme_tooltip() == strings.THEME_TOOLTIP_HC
    # picker still works (saved) while high contrast wins
    w.theme.current(1)
    w.theme.event_generate("<<ComboboxSelected>>")
    root.update()
    assert ctl.settings.theme == "light" and w.applied_theme == "high_contrast"
    probe.append((False, False))  # high contrast off -> saved explicit theme
    ctl.clock.t = 7
    ctl.dispatch(("theme_changed", None))
    assert w.applied_theme == "light"
    w._on_focus_in(type("E", (), {"widget": w.start_btn})())  # child focus: ignored


def test_tooltip_uses_palette(root):
    w, *_ = build(root, settings=DEFAULTS.replace(theme="dark"))
    w.show_window()
    root.update()
    w.theme_tip.show()
    assert str(w.theme_tip.tip.cget("bg")).upper() == "#2D2D2D"
    w.theme_tip.hide()


def test_preview_button(root):
    from test_controller import FakePreviewer

    p = FakePreviewer()
    ctl = AppController(DEFAULTS, FakeEngine(), FakeSaver(), lambda: [GS], Clock(), previewer=p)
    w = MainWindow(root, ctl, tray=FakeTray(), open_url=lambda u: None)
    ctl.startup()
    root.update()
    assert w.preview_btn.cget("text") == strings.PREVIEW
    assert w.instruments.master.winfo_reqwidth() <= w.device.master.winfo_reqwidth()
    assert not w.preview_btn.instate(["disabled"])
    w.preview_btn.invoke()
    assert len(p.started) == 1 and w.preview_btn.instate(["disabled"])
    p.active = False
    ctl.dispatch(("preview_done", None))
    assert not w.preview_btn.instate(["disabled"])


def test_no_preview_button_without_previewer(root):
    w, *_ = build(root)
    assert w.preview_btn is None
