# MouseMusic icons

Motif: a wide white computer mouse (left/right button split and a cord) with an eighth note above-right of it, on an indigo (#4F46E5) rounded square. The solid tile
reads on both light (#F3F3F3) and dark (#202020) Windows 11 taskbars. See `preview.png` and `preview-16px-zoom.png`.

| File | Use | docs/ux.md state |
|---|---|---|
| `../icon.ico` | App/exe icon + Tk window icon (`ARCHITECTURE.md` §3 path) | — |
| `tray-idle.ico` | Tray, stopped | Stopped (grey ●) |
| `tray-playing.ico` | Tray, playing: green ▶ badge | Playing (green ●) |
| `tray-error.ico` | Tray, error: red ! badge | Error (red ■, E1–E5) |
| `png/<variant>-<size>.png` | Same artwork as PNG (pystray/Pillow can load these directly) | |

Every .ico contains 16, 20, 24, 32, 40, 48, 64 and 256 px frames. Sizes ≤ 24 px use the `*-small.svg` artwork, which
uses thicker seams and cord and a larger note. Badge state is shown by both shape and colour, so it doesn't rely on colour alone.
Warnings (amber ▲) keep the idle or playing icon. Only errors switch to `tray-error`.

**Regenerate:** `pip install cairosvg Pillow && python tools/make_icons.py`. Edit the artwork in `svg()` and `BADGES`
in that script. The `.svg` files are written out from it, so don't hand-edit them.

`preview-before-after.png` compares the old "feather" design with the current one at 16/32/48 px, with 4x zooms (`ux/icon-readability`).
