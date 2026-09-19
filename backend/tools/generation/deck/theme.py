"""Design tokens. Every colour, size and position a slide uses comes from here.

Units: inches for geometry (the grid is easier to reason about in
inches on a 13.333 x 7.5 in 16:9 page), points for type.
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.dml.color import RGBColor


def rgb(hex_code: str) -> RGBColor:
    return RGBColor.from_string(hex_code.lstrip("#"))


@dataclass(frozen=True)
class Palette:
    navy: str = "0B1F33"        # primary dark: cover, dividers, table headers
    navy_2: str = "15314D"      # raised surface on navy
    teal: str = "0E7C86"        # primary accent: data, markers, links
    teal_light: str = "D7EEF0"  # teal tint for panels
    amber: str = "E09A2B"       # highlight: the one number that matters
    amber_light: str = "FBEBD2"
    red: str = "C8413B"         # critical / exceeded / incident
    red_light: str = "F8DEDC"
    green: str = "2E8B57"       # within limits
    green_light: str = "DCEFE3"
    ink: str = "17232F"         # body text
    ink_2: str = "3D4B59"       # secondary text
    muted: str = "7A8896"       # captions, footers
    rule: str = "D9E0E6"        # hairlines
    panel: str = "F3F6F8"       # light panels, zebra rows
    white: str = "FFFFFF"


PALETTE = Palette()

# Status words the renderer colours consistently wherever they appear
# (table cells, KPI cards, pills). Matching is on the normalised word.
STATUS_COLOURS = {
    "critical": ("red", "red_light"),
    "exceeded": ("red", "red_light"),
    "below": ("red", "red_light"),
    "high": ("red", "red_light"),
    "failed": ("red", "red_light"),
    "watch": ("amber", "amber_light"),
    "warning": ("amber", "amber_light"),
    "medium": ("amber", "amber_light"),
    "elevated": ("amber", "amber_light"),
    "normal": ("green", "green_light"),
    "within": ("green", "green_light"),
    "ok": ("green", "green_light"),
    "low": ("green", "green_light"),
    "pass": ("green", "green_light"),
    "complete": ("green", "green_light"),
    "completed": ("green", "green_light"),
}


# What a pill SAYS for a status word, where the bare word would mislead.
# "below" alone reads as a direction, not a verdict.
STATUS_LABELS = {"below": "below range"}


def status_label(word: str) -> str:
    return STATUS_LABELS.get(word.strip().lower(), word)


def status_colours(word: str | None) -> tuple[str, str] | None:
    if not word:
        return None
    key = word.strip().lower().split()[0] if word.strip() else ""
    names = STATUS_COLOURS.get(key)
    if not names:
        return None
    return getattr(PALETTE, names[0]), getattr(PALETTE, names[1])


# Typography. Segoe UI ships with Windows and Office, which is where these
# decks are opened; the measurement code reads the same TTFs.
FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
FONT_LIGHT = "Segoe UI Light"

# Page grid (inches).
PAGE_W = 13.333
PAGE_H = 7.5
MARGIN_X = 0.72
CONTENT_W = PAGE_W - 2 * MARGIN_X
EYEBROW_Y = 0.48
TITLE_Y = 0.78
TITLE_H = 1.22
BODY_Y = 1.92
BODY_BOTTOM = 6.62
BODY_H = BODY_BOTTOM - BODY_Y
FOOTER_Y = 6.98

# Type scale (points).
SIZE_COVER_TITLE = 40
SIZE_TITLE = 28
SIZE_TITLE_MIN = 20
SIZE_EYEBROW = 11
SIZE_BODY = 18
SIZE_BODY_MIN = 13
SIZE_SMALL = 12
SIZE_FOOTER = 9
