"""Measure text against the real font, so every text box fits what it holds.

python-pptx cannot ask PowerPoint how tall a paragraph will be, and
PowerPoint's own shrink-to-fit only applies when the file is opened and
edited. So the wrap is computed here, with the same TrueType files the
viewer uses (Segoe UI on Windows), and the renderer picks the largest
size that fits -- or splits the content onto another slide.

Where the fonts are not installed (the Linux sandbox), measurement falls
back to an average character width that errs WIDE, so text is sized
smaller rather than overflowing.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

_FONT_FILES = {
    "regular": "segoeui.ttf",
    "semibold": "seguisb.ttf",
    "bold": "segoeuib.ttf",
    "light": "segoeuil.ttf",
}
_FONT_DIRS = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path("/usr/share/fonts/truetype/segoe"),
]
# Average advance width as a fraction of the point size, used only when
# the TTF is unavailable. Segoe UI's real average is ~0.50; 0.56 is
# deliberately pessimistic.
_FALLBACK_EM = 0.56


@functools.lru_cache(maxsize=64)
def _font(weight: str, size_pt: float):
    try:
        from PIL import ImageFont
    except ImportError:  # pragma: no cover - PIL is a dependency
        return None
    name = _FONT_FILES.get(weight, _FONT_FILES["regular"])
    for d in _FONT_DIRS:
        path = d / name
        if path.exists():
            # Size in "pixels" at 72 dpi == points, so widths come back in points.
            return ImageFont.truetype(str(path), size=max(1, round(size_pt * 4)))
    return None


def text_width_pt(text: str, size_pt: float, weight: str = "regular") -> float:
    font = _font(weight, size_pt)
    if font is None:
        return len(text) * size_pt * _FALLBACK_EM
    return font.getlength(text) / 4.0


# PowerPoint wraps slightly earlier than these metrics predict -- kerning
# and its own internal padding -- so a paragraph measured as exactly
# fitting came out one line taller and ran past its panel. Measuring
# against a slightly narrower box costs a few characters per line and
# makes overflow impossible rather than marginal.
WRAP_SAFETY = 0.96


def wrap_lines(text: str, width_in: float, size_pt: float, weight: str = "regular") -> list[str]:
    """Greedy word wrap, the way PowerPoint wraps, in the box's inner width."""
    width_pt = width_in * 72.0 * WRAP_SAFETY
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if text_width_pt(candidate, size_pt, weight) <= width_pt:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def text_height_in(text: str, width_in: float, size_pt: float, weight: str = "regular",
                   line_spacing: float = 1.18) -> float:
    return len(wrap_lines(text, width_in, size_pt, weight)) * size_pt * line_spacing / 72.0


def fit_size(text: str, width_in: float, height_in: float, max_pt: float, min_pt: float,
             weight: str = "regular", line_spacing: float = 1.18, max_lines: int | None = None) -> float | None:
    """Largest size in [min_pt, max_pt] at which `text` fits, or None."""
    size = max_pt
    while size >= min_pt - 1e-6:
        lines = wrap_lines(text, width_in, size, weight)
        fits_h = len(lines) * size * line_spacing / 72.0 <= height_in
        fits_n = max_lines is None or len(lines) <= max_lines
        if fits_h and fits_n:
            return size
        size -= 1
    return None


def fit_many(texts: list[str], width_in: float, height_in: float, max_pt: float, min_pt: float,
             gap_in: float, weight: str = "regular", line_spacing: float = 1.18) -> float | None:
    """One size for a stack of paragraphs (bullets) that must all fit together."""
    size = max_pt
    while size >= min_pt - 1e-6:
        total = sum(text_height_in(t, width_in, size, weight, line_spacing) for t in texts)
        total += gap_in * max(0, len(texts) - 1)
        if total <= height_in:
            return size
        size -= 1
    return None
