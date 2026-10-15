"""Tk/ttk control window (docs/ux.md §1). The only thread that touches Tk widgets (§6).

A thin view over :class:`~mousemusic.ui.controller.AppController`: widgets call controller
actions; :meth:`MainWindow.refresh` copies controller state back into the widgets; a 50 ms
``after`` loop drains the cross-thread queue (engine events, tray, hotkey window, saver).
"""

from __future__ import annotations

import contextlib
import logging
import queue
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from mousemusic.mapping import Rect
from mousemusic.ui import strings
from mousemusic.ui.controller import AppController, Option
from mousemusic.ui.fit import HomePosition, fit_height, truncate, work_area_for
from mousemusic.ui.placement import place_window
from mousemusic.ui.theme import DARK, HIGH_CONTRAST, PALETTES, role_color

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 340, 360  # logical px at 100 %; minimum height, grows to fit (ux §1, Q-D1)
DRAIN_MS = 50


class Tooltip:
    """Minimal hover tooltip; ``text`` may be a callable for live text."""

    bg: str | None = None  # tk Toplevel background, set by MainWindow.apply_theme

    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def current_text(self) -> str:
        return self.text() if callable(self.text) else self.text

    def show(self, _event: Any = None) -> None:
        if self.tip is not None or not self.current_text():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        if Tooltip.bg:
            self.tip.configure(bg=Tooltip.bg)
        ttk.Label(
            self.tip,
            style="Tooltip.TLabel",
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
        title_bar: Callable[[Any, bool], Any] | None = None,
        announce: Callable[[int, str], Any] | None = None,
    ) -> None:
        self.root = root
        self.ctl = controller
        self.ui_queue = ui_queue
        self.tray = tray
        self.version = version
        self.open_url = open_url
        self.monitors = monitors
        self.cursor_cache = cursor_cache
        self.announce = announce  # (status hwnd, full text) -> screen readers (C-2)
        self.full_status = ""
        self.truncated = False
        self.title_bar = title_bar  # (root, dark) -> DWM immersive dark title bar (Windows)
        self.applied_theme: str | None = None
        self.style = ttk.Style(root)
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
            f, text=strings.START, command=self.ctl.toggle, default="active",
            style="Accent.TButton",
        )  # fmt: skip
        self.start_btn.grid(row=0, column=0, sticky="w", **pad)
        self.hint = ttk.Label(f, style="Hint.TLabel")
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
        inf = ttk.Frame(f)
        inf.grid(row=5, column=1, sticky="w", **pad)
        preview = self.ctl.previewer is not None  # same width as the MIDI row when shown
        self.instruments = ttk.Combobox(inf, state="readonly", width=17 if preview else 24)
        self.instruments.grid(row=0, column=0)
        self.preview_btn: ttk.Button | None = None
        if preview:
            self.preview_btn = ttk.Button(
                inf, text=strings.PREVIEW, width=7, command=self.ctl.preview
            )
            self.preview_btn.grid(row=0, column=1, padx=(4, 0))
            Tooltip(self.preview_btn, self.ctl.preview_tooltip)
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
        self.volume_label = ttk.Label(vf, width=7, style="Value.TLabel")
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
        self.note_length_label = ttk.Label(nf, width=7, style="Value.TLabel")
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

        label(11, strings.LABEL_THEME)
        self.theme = ttk.Combobox(f, state="readonly", width=18)
        self.theme.grid(row=11, column=1, sticky="w", **pad)
        self.theme.bind(
            "<<ComboboxSelected>>",
            lambda e: self._pick(self.theme, self.ctl.theme_options(), self.ctl.set_theme),
        )
        self.theme_tip = Tooltip(self.theme, self.ctl.theme_tooltip)
        r.bind("<FocusIn>", self._on_focus_in, add="+")

        ttk.Separator(f).grid(row=12, column=0, columnspan=2, sticky="ew", pady=4)
        sf = ttk.Frame(f)
        sf.grid(row=13, column=0, columnspan=2, sticky="ew")
        sf.columnconfigure(1, weight=1)
        self.dot = ttk.Label(sf, takefocus=0)
        self.dot.grid(row=0, column=0)
        # No fixed width: wraplength follows the window width (see _fit) so long warnings
        # wrap onto more lines and the window grows instead of truncating.
        self.status = ttk.Label(sf, justify="left", anchor="w", style="Status.TLabel",
                                takefocus=0)  # fmt: skip
        self.status.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        # Full text when truncated (B-2); always available to keyboard users (C-2).
        self.status_tip = Tooltip(self.status, lambda: self.full_status if self.truncated else "")
        self.help = ttk.Label(sf, text=strings.HELP_LINK, cursor="hand2", style="Link.TLabel")
        self.help.bind("<Button-1>", lambda e: self.open_help())
        self.help_anchor: str | None = None
        self._status_in_tab_order()
        self._focused_once = False
        self._fit_key: tuple | None = None
        self.height = 0

    def _status_in_tab_order(self) -> None:
        """C-2: the status line is focusable right after Reconnect (it lives in another
        frame, so the stacking order alone would put it last)."""

        def jump(target: tk.Widget) -> Callable[[Any], str]:
            def go(_e: Any) -> str:
                target.focus_set()
                return "break"

            return go

        self.reconnect.bind("<Tab>", jump(self.status))
        self.status.bind("<Tab>", jump(self.hotkey))
        self.status.bind("<Shift-Tab>", jump(self.reconnect))
        self.status.bind("<ISO_Left_Tab>", jump(self.reconnect))
        self.hotkey.bind("<Shift-Tab>", jump(self.status))
        self.hotkey.bind("<ISO_Left_Tab>", jump(self.status))
        self.status.bind("<FocusIn>", lambda e: self.status.state(["focus"]), add="+")
        self.status.bind("<FocusOut>", lambda e: self.status.state(["!focus"]), add="+")

    def _on_focus_in(self, event: Any) -> None:
        if event.widget is self.root:  # backup for a missed WM_SETTINGCHANGE (ux §11.2)
            self.ctl.request_theme_refresh()

    # -- theme (docs/ux.md §11.4-§11.6) --------------------------------------------------

    def comboboxes(self) -> list[ttk.Combobox]:
        return [self.scale, self.key, self.low, self.high, self.instruments, self.device,
                self.hotkey, self.theme]  # fmt: skip

    def apply_theme(self, effective: str) -> None:
        self.applied_theme = effective
        if effective == HIGH_CONTRAST:
            self._apply_high_contrast()
        else:
            self._apply_palette(PALETTES[effective])
        if self.title_bar is not None:
            self.title_bar(self.root, effective == DARK)

    def _apply_high_contrast(self) -> None:
        """No palette: native theme and system colours so the user's contrast colours win."""
        names = self.style.theme_names()
        self.style.theme_use(next(t for t in ("vista", "winnative", "default") if t in names))
        Tooltip.bg = None
        for opt in ("background", "foreground", "selectBackground", "selectForeground"):
            self.root.option_add(f"*TCombobox*Listbox.{opt}", "")
        with contextlib.suppress(tk.TclError):
            self.root.configure(bg="SystemButtonFace")
        font = ("TkDefaultFont", 9, "underline")
        for name in ("Hint.TLabel", "Value.TLabel", "Status.TLabel", "Tooltip.TLabel"):
            self.style.configure(name, foreground="", background="")
        self.style.configure("Link.TLabel", foreground="", background="", font=font)

    def _apply_palette(self, p: dict[str, str]) -> None:
        st = self.style
        st.theme_use("clam")
        self.root.configure(bg=p["bg"])
        Tooltip.bg = p["surface"]
        st.configure(
            ".", background=p["bg"], foreground=p["text"], bordercolor=p["border"],
            focuscolor=p["focus"], troughcolor=p["track"], selectbackground=p["select_bg"],
            selectforeground=p["select_fg"], insertcolor=p["text"],
        )  # fmt: skip
        st.map(".", foreground=[("disabled", p["disabled_text"])])
        for name in ("TFrame", "TLabel", "Status.TLabel"):
            st.configure(name, background=p["bg"], foreground=p["text"])
        for name in ("Hint.TLabel", "Value.TLabel"):
            st.configure(name, background=p["bg"], foreground=p["text_secondary"])
        st.configure("Link.TLabel", background=p["bg"], foreground=p["link"],
                     font=("TkDefaultFont", 9, "underline"))  # fmt: skip
        st.configure("Tooltip.TLabel", background=p["surface"], foreground=p["text"],
                     bordercolor=p["border"])  # fmt: skip
        surf = p["surface"]
        st.configure("TButton", background=surf, foreground=p["text"],
                     bordercolor=p["border"], lightcolor=surf, darkcolor=surf)  # fmt: skip
        st.map(
            "TButton",
            background=[("disabled", p["disabled_surface"]), ("pressed", p["border"]),
                        ("active", p["surface_hover"])],
            foreground=[("disabled", p["disabled_text"])],
            bordercolor=[("focus", p["focus"])],
        )  # fmt: skip
        st.configure("Accent.TButton", background=p["accent"], foreground=p["on_accent"],
                     lightcolor=p["accent"], darkcolor=p["accent"])  # fmt: skip
        st.map(
            "Accent.TButton",
            background=[("disabled", p["disabled_surface"]), ("active", p["accent_hover"])],
            foreground=[("disabled", p["disabled_text"])],
            bordercolor=[("focus", p["focus"])],
        )  # fmt: skip
        st.configure(
            "TCombobox", fieldbackground=p["surface"], background=p["surface"],
            foreground=p["text"], arrowcolor=p["text"], bordercolor=p["border"],
            lightcolor=p["surface"], darkcolor=p["surface"],
        )  # fmt: skip
        st.map(
            "TCombobox",
            fieldbackground=[("disabled", p["disabled_surface"]), ("readonly", p["surface"])],
            foreground=[("disabled", p["disabled_text"])],
            arrowcolor=[("disabled", p["disabled_text"])],
            bordercolor=[("focus", p["focus"])],
            selectbackground=[("readonly", p["surface"])],
            selectforeground=[("readonly", p["text"])],
        )  # fmt: skip
        st.configure(
            "TCheckbutton", background=p["bg"], foreground=p["text"],
            indicatorbackground=p["surface"], indicatorforeground=p["on_accent"],
            upperbordercolor=p["border"], lowerbordercolor=p["border"],
        )  # fmt: skip
        st.map(
            "TCheckbutton",
            indicatorbackground=[("selected", p["accent"])],
            background=[("active", p["bg"])],
            foreground=[("disabled", p["disabled_text"])],
        )  # fmt: skip
        th = p["thumb"]
        st.configure("Horizontal.TScale", troughcolor=p["track"], background=th,
                     bordercolor=p["track"], lightcolor=th, darkcolor=th)  # fmt: skip
        st.map("Horizontal.TScale",
               background=[("disabled", p["disabled_text"]), ("active", p["focus"])])  # fmt: skip
        st.configure("Vertical.TScrollbar", background=p["surface"], troughcolor=p["bg"],
                     arrowcolor=p["text"])  # fmt: skip
        st.configure("TSeparator", background=p["border"])
        lb = {"background": p["surface"], "foreground": p["text"],
              "selectBackground": p["select_bg"], "selectForeground": p["select_fg"]}  # fmt: skip
        for opt, val in lb.items():
            self.root.option_add(f"*TCombobox*Listbox.{opt}", val)
        for combo in self.comboboxes():  # option_add only affects new widgets: re-skin popdowns
            with contextlib.suppress(tk.TclError):
                pd = self.root.tk.call("ttk::combobox::PopdownWindow", combo)
                args = [x for k, v in lb.items() for x in (f"-{k.lower()}", v)]
                self.root.tk.call(f"{pd}.f.l", "configure", *args)

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
        self.work_areas, self.primary = monitors, primary
        self.home = HomePosition((x, y))  # C-1
        self.placed = (x, y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.height = h
        self.root.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, event: Any) -> None:
        if event.widget is not self.root:
            return
        pos = (self.root.winfo_x(), self.root.winfo_y())
        if self.placed is None or not self.root.winfo_viewable():
            return
        if self.home.user_moved(pos):  # not our own geometry(): becomes home, is saved
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
        if self.preview_btn is not None:
            self.preview_btn.state(["!disabled"] if c.can_preview else ["disabled"])
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
        if c.effective_theme != self.applied_theme:
            self.apply_theme(c.effective_theme)
        self._set_combo(self.theme, c.theme_options(), s.theme)
        try:
            self.dot.configure(
                text=status.dot, foreground=role_color(c.effective_theme, status.role)
            )
        except tk.TclError:  # system colour names (high contrast) exist only on Windows Tk
            self.dot.configure(text=status.dot, foreground="")
        self.full_status = status.text
        self.status.configure(text=status.text)
        if self.announce is not None:
            self.announce(self.status.winfo_id(), status.text)
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

    def chrome_height(self) -> int:
        """Title bar + frame, so the whole window (not just the client) fits the work area."""
        return round(40 * self.size()[0] / WIDTH)

    def _fit(self) -> None:
        """Re-wrap the status, follow the content height within [360, work area] (B-2),
        truncate past the cap, and re-place from home (B-3, C-1)."""
        key = (self.full_status, self.help_anchor)
        if key == self._fit_key:
            return
        self._fit_key = key
        wl = self.status_wraplength()
        self.status.configure(text=self.full_status, wraplength=wl)
        self.root.update_idletasks()
        w, base_h = self.size()
        required = self.root.winfo_reqheight()
        area = work_area_for(self.home.home, (w, required), self.work_areas, self.primary)
        cap = max(1, area.h - self.chrome_height())
        h = fit_height(required, base_h, cap)
        self.truncated = required > cap
        if self.truncated:
            font = tkfont.nametofont("TkDefaultFont")
            avail = self.status.winfo_reqheight() - (required - cap)
            lines = max(1, avail // max(1, font.metrics("linespace")))
            self.status.configure(text=truncate(self.full_status, wl, lines, font.measure))
            log.info("status truncated to %d line(s); full text: %s", lines, self.full_status)
        pos = self.home.position((w, h), self.work_areas, self.primary)
        if h != self.height or pos != self.placed:
            self.height = h
            self.placed = pos
            self.root.geometry(f"{w}x{h}+{pos[0]}+{pos[1]}")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if not self._focused_once and self.title_bar is not None and self.applied_theme:
            # The frame window may only exist once mapped: set the title bar again (ux §11.3).
            self.title_bar(self.root, self.applied_theme == DARK)
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
