"""WCAG 2.x contrast check for the docs/ux.md §11 palette. Run: python tools/contrast.py"""

PALETTE = {
    "light": {
        "bg": "#F3F3F3",
        "surface": "#FFFFFF",
        "text": "#1B1B1B",
        "text_secondary": "#5C5C5C",
        "border": "#8A8A8A",
        "accent": "#4F46E5",
        "on_accent": "#FFFFFF",
        "focus": "#4F46E5",
        "disabled_text": "#9E9E9E",
        "track": "#8A8A8A",
        "thumb": "#4F46E5",
        "select_bg": "#4F46E5",
        "select_fg": "#FFFFFF",
        "link": "#4338CA",
        "dot_idle": "#6B6B6B",
        "dot_ok": "#15803D",
        "warn": "#A14A06",
        "error": "#B91C1C",
    },
    "dark": {
        "bg": "#202020",
        "surface": "#2D2D2D",
        "text": "#F3F3F3",
        "text_secondary": "#B8B8B8",
        "border": "#8A8A8A",
        "accent": "#5B54E8",
        "on_accent": "#FFFFFF",
        "focus": "#A5A0FF",
        "disabled_text": "#6E6E6E",
        "track": "#8A8A8A",
        "thumb": "#A5A0FF",
        "select_bg": "#4F46E5",
        "select_fg": "#FFFFFF",
        "link": "#A5A0FF",
        "dot_idle": "#A3A3A3",
        "dot_ok": "#4ADE80",
        "warn": "#FBBF24",
        "error": "#F87171",
    },
}

# (foreground token, background token, minimum ratio, kind)
PAIRS = [
    ("text", "bg", 4.5, "text"),
    ("text", "surface", 4.5, "text"),
    ("text_secondary", "bg", 4.5, "text"),
    ("text_secondary", "surface", 4.5, "text"),
    ("on_accent", "accent", 4.5, "text"),
    ("select_fg", "select_bg", 4.5, "text"),
    ("link", "bg", 4.5, "text"),
    ("warn", "bg", 4.5, "text"),
    ("error", "bg", 4.5, "text"),
    ("border", "surface", 3.0, "ui"),
    ("border", "bg", 3.0, "ui"),
    ("focus", "bg", 3.0, "ui"),
    ("focus", "surface", 3.0, "ui"),
    ("track", "bg", 3.0, "ui"),
    ("thumb", "bg", 3.0, "ui"),
    ("accent", "bg", 3.0, "ui"),
    ("dot_idle", "bg", 3.0, "ui"),
    ("dot_ok", "bg", 3.0, "ui"),
    ("disabled_text", "bg", 0.0, "exempt"),
]


def lum(h: str) -> float:
    c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main() -> int:
    bad = 0
    print("| Theme | Foreground | Background | Ratio | Min | Result |\n|---|---|---|---|---|---|")
    for theme, p in PALETTE.items():
        for fg, bg, need, kind in PAIRS:
            r = ratio(p[fg], p[bg])
            ok = r >= need
            bad += not ok
            res = "exempt (disabled)" if kind == "exempt" else ("pass" if ok else "**FAIL**")
            pair = f"`{fg}` {p[fg]} | `{bg}` {p[bg]}"
            print(f"| {theme} | {pair} | {r:.2f}:1 | {need or '—'} | {res} |")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
