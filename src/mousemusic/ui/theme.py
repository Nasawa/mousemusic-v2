"""Dark mode: palette tokens and theme resolution (docs/ux.md §11). Pure, no Tk import."""

from __future__ import annotations

LIGHT, DARK, HIGH_CONTRAST = "light", "dark", "high_contrast"

PALETTES: dict[str, dict[str, str]] = {
    LIGHT: {
        "bg": "#F3F3F3",
        "surface": "#FFFFFF",
        "surface_hover": "#F0F0F0",
        "text": "#1B1B1B",
        "text_secondary": "#5C5C5C",
        "border": "#8A8A8A",
        "accent": "#4F46E5",
        "on_accent": "#FFFFFF",
        "focus": "#4F46E5",
        "disabled_text": "#9E9E9E",
        "disabled_surface": "#F7F7F7",
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
    DARK: {
        "bg": "#202020",
        "surface": "#2D2D2D",
        "surface_hover": "#383838",
        "text": "#F3F3F3",
        "text_secondary": "#B8B8B8",
        "border": "#8A8A8A",
        "accent": "#5B54E8",
        "on_accent": "#FFFFFF",
        "focus": "#A5A0FF",
        "disabled_text": "#6E6E6E",
        "disabled_surface": "#262626",
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

#: Status dot role (ui/status.py) → palette token.
ROLE_TOKENS = {"idle": "dot_idle", "ok": "dot_ok", "warn": "warn", "error": "error"}
#: High contrast: Tk system colour names so the user's contrast colours win (§11.6).
HC_TEXT = "SystemWindowText"

#: Coalesce bursts of WM_SETTINGCHANGE into at most one re-apply per this many seconds.
REAPPLY_INTERVAL_S = 0.25


def resolve(theme: str, apps_use_light: bool | None, high_contrast: bool) -> str:
    """Effective theme: high contrast wins, then an explicit choice, then Windows' app theme
    (``AppsUseLightTheme``; unknown → light)."""
    if high_contrast:
        return HIGH_CONTRAST
    if theme in (LIGHT, DARK):
        return theme
    return DARK if apps_use_light is False else LIGHT


def lighten(hex_color: str, amount: float) -> str:
    """Mix ``hex_color`` towards white by ``amount`` (0..1)."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


for _p in PALETTES.values():  # Start button hover: accent lightened 8 % (§11.5)
    _p["accent_hover"] = lighten(_p["accent"], 0.08)


def role_color(effective: str, role: str) -> str:
    if effective == HIGH_CONTRAST:
        return HC_TEXT
    return PALETTES[effective][ROLE_TOKENS[role]]
