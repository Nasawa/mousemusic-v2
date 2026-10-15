"""Tk/ttk control window (docs/ux.md §1). The only thread that touches Tk widgets (§6).

A thin view over :class:`~mousemusic.ui.controller.AppController`: widgets call controller
actions; :meth:`MainWindow.refresh` copies controller state back into the widgets; a 50 ms
``after`` loop drains the cross-thread queue (engine events, tray, hotkey window, saver).
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from mousemusic.mapping import Rect
from mousemusic.ui import strings
from mousemusic.ui.controller import AppController, Option
from mousemusic.ui.placement import place_window

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 340, 330  # logical px at 100 %; minimum height, grows to fit (ux §1)
DRAIN_MS = 50


class Tooltip:
    """Minimal hover tooltip; ``text`` may be a callable for live text."""

    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def current_text(self) -> str:
        return self.text() if callable(self.text) else self.text

    def show(self, _event: Any = None) -> None:
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            self.tip,
            text=self.current_text(),
            relief="solid",
            borderwidth=1,
            padding=(4, 2),
            wraplength=320,
        ).pack()

    def hide(self, _event: Any = None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class TkCursorCache:
    """Cursor source for non-Windows dry runs: the Tk main loop refreshes cached values, the
    engine thread only reads them (Tk is not thread-safe)."""

    def __init__(self) -> None:
        self.pos: tuple[int, int] | None = None
        self.rect: Rect | None = None

    def update(self, root: tk.Misc) -> None:
        self.pos = root.winfo_pointerxy()
        self.rect = Rect(0, 0, max(1, root.winfo_screenwidth()), max(1, root.winfo_screenheight()))

    def position(self) -> tuple[int, int] | None:
        return self.pos

    def virtual_rect(self) -> Rect | None:
        return self.rect

    def primary_rect(self) -> Rect | None:
        return self.rect


def _index(options: list[Option], value: Any) -> int:
    for i, o in enumerate(options):
        if o.value == value:
            return i
    return -1


class MainWindow:
    def __init__(
        self,
        root: tk.Tk,
        controller: AppController,
        *,
        ui_queue: queue.Queue | None = None,
        tray: Any = None,
        version: str = "",
        open_url: Callable[[str], Any] = webbrowser.open,
        monitors: Callable[[], list[Rect]] | None = None,
        cursor_cache: TkCursorCache | None = None,
    ) -> None:
        self.root = root
        self.ctl = controller
        self.ui_queue = ui_queue
        self.tray = tray
        self.version = version
        self.open_url = open_url
        self.monitors = monitors
        self.cursor_cache = cursor_cache
        self.placed: tuple[int, int] | None = None
        self._refreshing = False
        self._after_id: str | None = None
        controller.view = self
        self._build()
        self._place()
        self.refresh()

    # -- construction --------------------------------------------------------------------

    def _build(self) -> None:
        r = self.root
        r.title(strings.WINDOW_TITLE)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self.close)
        r.bind("<Escape>", lambda e: self.close(balloon=False))
        f = ttk.Frame(r, padding=8)
        f.grid(sticky="nsew")
        f.columnconfigure(1, weight=1)
        pad = {"pady": 2}

        self.start_btn = ttk.Button(
            f, text=strings.START, command=self.ctl.toggle, default="active"
        )
        self.start_btn.grid(row=0, column=0, sticky="w", **pad)
        self.hint = ttk.Label(f, foreground="grey")
        self.hint.grid(row=0, column=1, sticky="e", **pad)
        r.bind("<Return>", lambda e: self._invoke_if_focused(e))
        ttk.Separator(f).grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        def label(row: int, text: str) -> None:
            ttk.Label(f, text=text).grid(row=row, column=0, sticky="e", padx=(0, 8), **pad)

        label(2, strings.LABEL_SCALE)
        self.scale = ttk.Combobox(f, state="readonly", width=24)
        self.scale.grid(row=2, column=1, sticky="w", **pad)
        self.scale.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(self.scale, self.ctl.scale_options(), self.ctl.set_scale),
        )

        label(3, strings.LABEL_KEY)
        self.key = ttk.Combobox(f, state="readonly", width=4)
        self.key.grid(row=3, column=1, sticky="w", **pad)
        self.key.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(self.key, self.ctl.key_options(), self.ctl.set_root),
        )

        label(4, strings.LABEL_RANGE)
        rf = ttk.Frame(f)
        rf.grid(row=4, column=1, sticky="w", **pad)
        self.low = ttk.Combobox(rf, state="readonly", width=4)
        self.low.grid(row=0, column=0)
        ttk.Label(rf, text=strings.LABEL_RANGE_TO).grid(row=0, column=1, padx=6)
        self.high = ttk.Combobox(rf, state="readonly", width=4)
        self.high.grid(row=0, column=2)
        self.low.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(
                self.low, self.ctl.range_options(self.ctl.settings.low_note), self.ctl.set_low
            ),
        )
        self.high.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(
                self.high, self.ctl.range_options(self.ctl.settings.high_note), self.ctl.set_high
            ),
        )

        label(5, strings.LABEL_INSTRUMENTS)
        self.instruments = ttk.Combobox(f, state="readonly", width=24)
        self.instruments.grid(row=5, column=1, sticky="w", **pad)
        self.instruments.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(
                self.instruments, self.ctl.instrument_options(), self.ctl.set_instrument_set
            ),
        )
        self.instruments_tip = Tooltip(self.instruments, self.ctl.instrument_tooltip)

        label(6, strings.LABEL_VOLUME)
        vf = ttk.Frame(f)
        vf.grid(row=6, column=1, sticky="w", **pad)
        self.volume = ttk.Scale(
            vf, from_=0, to=100, length=150, command=lambda v: self._slider(self.ctl.set_volume, v)
        )
        self.volume.grid(row=0, column=0)
        self.volume_label = ttk.Label(vf, width=7)
        self.volume_label.grid(row=0, column=1, padx=6)
        self._slider_keys(self.volume, 1, 10, self.ctl.set_volume, lambda: self.ctl.settings.volume)

        label(7, strings.LABEL_NOTE_LENGTH)
        nf = ttk.Frame(f)
        nf.grid(row=7, column=1, sticky="w", **pad)
        self.note_length = ttk.Scale(
            nf,
            from_=50,
            to=2000,
            length=150,
            command=lambda v: self._slider(self.ctl.set_note_length, v),
        )
        self.note_length.grid(row=0, column=0)
        self.note_length_label = ttk.Label(nf, width=7)
        self.note_length_label.grid(row=0, column=1, padx=6)
        self._slider_keys(
            self.note_length,
            10,
            100,
            self.ctl.set_note_length,
            lambda: self.ctl.settings.note_length_ms,
        )

        self.legato_var = tk.BooleanVar(value=False)
        self.legato = ttk.Checkbutton(
            f,
            text=strings.LABEL_LEGATO,
            variable=self.legato_var,
            command=lambda: self.ctl.set_legato(self.legato_var.get()),
        )
        self.legato.grid(row=8, column=1, sticky="w", **pad)

        label(9, strings.LABEL_MIDI)
        mf = ttk.Frame(f)
        mf.grid(row=9, column=1, sticky="w", **pad)
        self.device = ttk.Combobox(
            mf, state="readonly", width=22, postcommand=self._on_device_dropdown
        )
        self.device.grid(row=0, column=0)
        self.device.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(self.device, self.ctl.device_options(), self.ctl.pick_device),
        )
        self.device_tip = Tooltip(self.device, lambda: self.ctl.selected_device or "")
        self.reconnect = ttk.Button(
            mf, text=strings.RECONNECT_BUTTON, width=3, command=self.ctl.reconnect
        )
        self.reconnect.grid(row=0, column=1, padx=(4, 0))
        Tooltip(self.reconnect, strings.RECONNECT_TOOLTIP)

        label(10, strings.LABEL_HOTKEY)
        self.hotkey = ttk.Combobox(f, state="readonly", width=18)
        self.hotkey.grid(row=10, column=1, sticky="w", **pad)
        self.hotkey.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(self.hotkey, self.ctl.hotkey_options(), self.ctl.set_hotkey),
        )

        ttk.Separator(f).grid(row=11, column=0, columnspan=2, sticky="ew", pady=4)
        sf = ttk.Frame(f)
        sf.grid(row=12, column=0, columnspan=2, sticky="ew")
        sf.columnconfigure(1, weight=1)
        self.dot = ttk.Label(sf, takefocus=0)
        self.dot.grid(row=0, column=0)
        # No fixed width: wraplength follows the window width (see _fit) so long warnings
        # wrap onto more lines and the window grows instead of truncating.
        self.status = ttk.Label(sf, justify="left", anchor="w")
        self.status.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.help = ttk.Label(
            sf,
            text=strings.HELP_LINK,
            foreground="#2563EB",
            cursor="hand2",
            font=("TkDefaultFont", 9, "underline"),
        )
        self.help.bind("<Button-1>", lambda e: self.open_help())
        self.help_anchor: str | None = None
        self._focused_once = False
        self._fit_key: tuple | None = None
        self.height = 0

    def close(self, *, balloon: bool = True) -> None:
        """✕ / Esc: hide to tray (§2.1). Without a tray (non-Windows dev runs) there would be
        no way back, so closing quits instead."""
        if self.tray is None:
            self.ctl.quit()
        else:
            self.ctl.close_window(balloon=balloon)

    def _invoke_if_focused(self, event: Any) -> None:
        if self.root.focus_get() is self.start_btn:
            self.start_btn.invoke()

    def _pick(self, combo: ttk.Combobox, options: list[Option], action: Callable) -> None:
        i = combo.current()
        if 0 <= i < len(options) and options[i].value is not None:
            action(options[i].value)

    def _slider(self, action: Callable[[float], None], value: str) -> None:
        if not self._refreshing:
            action(float(value))

    def _slider_keys(
        self, w: ttk.Scale, step: int, page: int, action: Callable, get: Callable[[], int]
    ) -> None:
        for key, delta in (
            ("<Left>", -step),
            ("<Right>", step),
            ("<Prior>", page),
            ("<Next>", -page),
        ):
            w.bind(key, lambda e, d=delta: (action(get() + d), "break")[1])

    def _on_device_dropdown(self) -> None:
        self.ctl.refresh_devices()  # §9: re-enumerate every time the dropdown opens

    def open_help(self) -> None:
        if self.help_anchor:
            self.open_url(strings.help_url(self.help_anchor))

    # -- placement -----------------------------------------------------------------------

    def size(self) -> tuple[int, int]:
        scale = self.root.winfo_fpixels("1i") / 96.0
        return round(WIDTH * scale), round(HEIGHT * scale)

    def _place(self) -> None:
        w, h = self.size()
        s = self.ctl.settings
        x, y = s.window_x, s.window_y
        primary = Rect(0, 0, max(1, self.root.winfo_screenwidth()),
                       max(1, self.root.winfo_screenheight()))  # fmt: skip
        try:
            monitors = self.monitors() if self.monitors else [primary]
        except Exception:
            log.exception("enumerating monitors failed")
            monitors = [primary]
        # Primary is the monitor containing (0, 0) on Windows; fall back to Tk's screen.
        primary = next((m for m in monitors if m.x <= 0 < m.x + m.w and m.y <= 0 < m.y + m.h),
                       primary)  # fmt: skip
        x, y = place_window((x, y), (w, h), monitors, primary)
        self.placed = (x, y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.height = h
        self.root.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, event: Any) -> None:
        if event.widget is not self.root:
            return
        pos = (self.root.winfo_x(), self.root.winfo_y())
        if self.placed is not None and pos != self.placed and self.root.winfo_viewable():
            self.placed = pos
            self.ctl.window_moved(*pos)

    # -- View protocol --------------------------------------------------------------------

    def refresh(self) -> None:
        self._refreshing = True
        try:
            self._refresh()
        finally:
            self._refreshing = False

    def _set_combo(self, combo: ttk.Combobox, options: list[Option], value: Any) -> None:
        labels = [o.label for o in options]
        if list(combo.cget("values")) != labels:
            combo.configure(values=labels)
        i = _index(options, value)
        if i >= 0 and combo.current() != i:
            combo.current(i)
        elif i < 0 and options:
            combo.set(options[0].label)

    def _refresh(self) -> None:
        c, s, st = self.ctl, self.ctl.settings, self.ctl.status
        playing = st.playing
        self.start_btn.configure(text=strings.STOP if playing else strings.START)
        self.start_btn.state(["!disabled"] if (c.can_start or playing) else ["disabled"])
        self.hint.configure(text=st.hotkey_hint())
        self._set_combo(self.hotkey, c.hotkey_options(), s.hotkey)
        self._set_combo(self.scale, c.scale_options(), s.scale)
        self._set_combo(self.key, c.key_options(), s.root)
        self.key.state(["!disabled"] if c.key_enabled else ["disabled"])
        self._set_combo(self.low, c.range_options(s.low_note), s.low_note)
        self._set_combo(self.high, c.range_options(s.high_note), s.high_note)
        self._set_combo(self.instruments, c.instrument_options(), s.instrument_set)
        if round(float(self.volume.get())) != s.volume:
            self.volume.set(s.volume)
        self.volume_label.configure(text=strings.VOLUME_VALUE.format(value=s.volume))
        if round(float(self.note_length.get())) != s.note_length_ms:
            self.note_length.set(s.note_length_ms)
        self.note_length_label.configure(
            text=strings.NOTE_LENGTH_VALUE.format(value=s.note_length_ms)
        )
        self.note_length.state(["!disabled"] if c.note_length_enabled else ["disabled"])
        self.note_length_label.state(["!disabled"] if c.note_length_enabled else ["disabled"])
        self.legato_var.set(s.legato)
        opts = c.device_options()
        self._set_combo(self.device, opts, c.selected_device)
        self.device.state(["!disabled"] if c.devices else ["disabled"])
        status = st.current(c.clock())
        self.dot.configure(text=status.dot, foreground=status.color)
        self.status.configure(text=status.text)
        self.help_anchor = status.help_anchor
        if status.help_anchor:
            self.help.grid(row=0, column=2, padx=(4, 0))
        else:
            self.help.grid_remove()
        self._fit()
        if self.tray is not None:
            self.tray.update(st.tray_icon(), st.tray_tooltip(self.version), playing)

    def status_wraplength(self) -> int:
        """Pixels available for the status text: window width minus padding, dot and link."""
        w, _ = self.size()
        scale = w / WIDTH
        used = self.dot.winfo_reqwidth() + round(28 * scale)
        if self.help_anchor:
            used += self.help.winfo_reqwidth() + round(4 * scale)
        return max(50, w - used)

    def _fit(self) -> None:
        """Re-wrap the status text and grow (or shrink back) the window height to fit."""
        key = (self.status.cget("text"), self.help_anchor)
        if key == self._fit_key:
            return
        self._fit_key = key
        self.status.configure(wraplength=self.status_wraplength())
        self.root.update_idletasks()
        w, base_h = self.size()
        h = max(base_h, self.root.winfo_reqheight())
        if h != self.height:
            self.height = h
            x, y = self.placed or (self.root.winfo_x(), self.root.winfo_y())
            self.root.geometry(f"{w}x{h}+{x}+{y}")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if not self._focused_once:  # ux §1.1: Start has focus when the window first opens
            self._focused_once = True
            self.start_btn.focus_set()

    def hide_window(self) -> None:
        self.root.withdraw()

    def notify(self, title: str, text: str) -> None:
        if self.tray is not None:
            self.tray.notify(title, text)

    def quit_app(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        if self.tray is not None:
            self.tray.stop()
        self.root.quit()

    # -- 50 ms drain (§6) ------------------------------------------------------------------

    def drain(self) -> None:
        if self.cursor_cache is not None:
            self.cursor_cache.update(self.root)
        if self.ui_queue is not None:
            while True:
                try:
                    item = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                self.ctl.dispatch(item)
                if self.ctl.quitting:
                    return
        self.ctl.tick()

    def start_polling(self) -> None:
        def loop() -> None:
            self.drain()
            if not self.ctl.quitting:
                self._after_id = self.root.after(DRAIN_MS, loop)

        self._after_id = self.root.after(DRAIN_MS, loop)
