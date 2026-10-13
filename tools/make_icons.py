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
    # Mouse body (white) with an eighth note knocked out in indigo.
    # small=True drops the button seam so the glyph stays clean at 16-24 px.
    seam = (
        ""
        if small
        else f'<line x1="128" y1="40" x2="128" y2="92" stroke="{BG}" stroke-width="10"/>'
    )
    return f'''{SVG_OPEN}
  <rect x="8" y="8" width="240" height="240" rx="56" fill="{BG}"/>
  <rect x="64" y="28" width="128" height="200" rx="64" fill="{INK}"/>
  {seam}
  <g fill="{BG}">
    <ellipse cx="114" cy="182" rx="26" ry="20" transform="rotate(-20 114 182)"/>
    <rect x="128" y="104" width="14" height="80"/>
    <path d="M128 104 C150 104 168 116 168 140 C160 128 150 124 142 124 L142 104 Z"/>
  </g>
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
