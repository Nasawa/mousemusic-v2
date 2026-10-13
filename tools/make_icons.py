"""Regenerate MouseMusic icons from SVG sources.

Usage:  pip install cairosvg Pillow   then   python tools/make_icons.py
Writes assets/icons/*.svg (sources), assets/icons/png/*.png, assets/icon.ico,
assets/icons/tray-*.ico and assets/icons/preview.png.
"""

from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
PNG = OUT / "png"
SIZES = [16, 20, 24, 32, 40, 48, 64, 256]
BG = "#4F46E5"  # indigo: contrasts with both light (#F3F3F3) and dark (#202020) taskbars
INK = "#FFFFFF"
SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
BADGE_RING = 'cx="200" cy="200" r="50" stroke="#FFFFFF" stroke-width="14"'

BADGES = {
    "idle": "",
    "playing": f'<circle {BADGE_RING} fill="#16A34A"/>'
    '<path d="M184 176 L226 200 L184 224 Z" fill="#FFFFFF"/>',
    "error": f'<circle {BADGE_RING} fill="#DC2626"/>'
    '<rect x="192" y="168" width="16" height="40" rx="6" fill="#FFFFFF"/>'
    '<circle cx="200" cy="226" r="9" fill="#FFFFFF"/>',
}


def svg(badge: str = "", small: bool = False) -> str:
    # A wide, rounded computer mouse (white) with a visible left/right button split and a cord,
    # plus an eighth note above-right of it. small=True (<= 24 px) thickens the strokes and
    # enlarges the note so the mouse silhouette and button split survive at 16 px.
    seam_w = 14 if small else 9
    cord_w = 16 if small else 11
    note = (
        '<g fill="{ink}"><ellipse cx="184" cy="96" rx="26" ry="20" transform="rotate(-20 184 96)"/>'
        '<rect x="196" y="24" width="16" height="74"/>'
        '<path d="M196 24 C222 26 238 40 236 66 C228 54 218 50 212 50 L212 24 Z"/></g>'
    ) if small else (
        '<g fill="{ink}"><ellipse cx="190" cy="88" rx="22" ry="17" transform="rotate(-20 190 88)"/>'
        '<rect x="200" y="28" width="12" height="62"/>'
        '<path d="M200 28 C222 30 236 42 234 64 C226 54 218 50 212 50 L212 28 Z"/></g>'
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <rect x="8" y="8" width="240" height="240" rx="56" fill="{BG}"/>
  <path d="M100 96 C100 70 110 52 128 40" fill="none" stroke="{INK}" stroke-width="{cord_w}" stroke-linecap="round"/>
  <path d="M100 92 C144 92 160 124 160 160 C160 200 136 226 100 226 C64 226 40 200 40 160 C40 124 56 92 100 92 Z" fill="{INK}"/>
  <path d="M40 150 L160 150 M100 92 L100 150" stroke="{BG}" stroke-width="{seam_w}" fill="none"/>
  {note.format(ink=INK)}
  {badge}
</svg>'''


def render(src: str, size: int) -> Image.Image:
    return Image.open(
        BytesIO(cairosvg.svg2png(bytestring=src.encode(), output_width=size, output_height=size))
    ).convert("RGBA")


def main() -> None:
    PNG.mkdir(parents=True, exist_ok=True)
    variants = {"app": ""} | {f"tray-{k}": v for k, v in BADGES.items()}
    imgs = {}
    for name, badge in variants.items():
        (OUT / f"{name}.svg").write_text(svg(badge))
        (OUT / f"{name}-small.svg").write_text(svg(badge, small=True))
        frames = []
        for s in SIZES:
            im = render(svg(badge, small=s <= 24), s)
            im.save(PNG / f"{name}-{s}.png")
            frames.append(im)
        imgs[name] = frames
        target = ROOT / "assets" / "icon.ico" if name == "app" else OUT / f"{name}.ico"
        frames[-1].save(
            target,
            format="ICO",
            sizes=[(s, s) for s in SIZES],
            append_images=frames[:-1],
        )
    # preview sheet: each variant at every size on light and dark taskbar colours
    cell, pad = 72, 12
    w = 120 + len(SIZES) * cell
    h = pad + len(variants) * 2 * (cell + 4)
    sheet = Image.new("RGBA", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(sheet)
    y = pad
    for name, frames in imgs.items():
        for bg, fg in (("#F3F3F3", "#000000"), ("#202020", "#FFFFFF")):
            d.rectangle([0, y, w, y + cell], fill=bg)
            d.text((6, y + cell // 2 - 6), name, fill=fg)
            for i, im in enumerate(frames):
                show = im if im.width <= 64 else im.resize((64, 64), Image.LANCZOS)
                x = 120 + i * cell + (cell - show.width) // 2
                sheet.alpha_composite(show, (x, y + (cell - show.height) // 2))
            y += cell + 4
    sheet.save(OUT / "preview.png")
    # 4x zoom of the 16px tray icons, to check legibility
    z = Image.new("RGBA", (3 * 2 * 80, 80), "#000000")
    for i, n in enumerate(["tray-idle", "tray-playing", "tray-error"]):
        for j, bg in enumerate(("#F3F3F3", "#202020")):
            tile = Image.new("RGBA", (80, 80), bg)
            tile.alpha_composite(imgs[n][0].resize((64, 64), Image.NEAREST), (8, 8))
            z.paste(tile, ((i * 2 + j) * 80, 0))
    z.save(OUT / "preview-16px-zoom.png")


if __name__ == "__main__":
    main()
