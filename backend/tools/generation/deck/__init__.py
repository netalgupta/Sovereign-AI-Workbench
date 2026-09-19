"""Presentation design system: DeckSpec (content) -> .pptx (design).

The model decides WHAT a deck says, as validated structured data
(spec.py). Everything about how it LOOKS is deterministic code here:
theme tokens, a layout grid, text measured against the real font so it
fits its box, native PowerPoint charts and tables, and continuation
slides when content is longer than one slide can hold.

Replaces template cloning (slide_kit.py + MRPL_Template.pptx). Cloning
19 sample slides and swapping their text could not look designed: each
sample was laid out for its own example text, broke on real text that
was longer or shorter, carried labels baked into the sample ("INCIDENT
DETAIL", "CURRENT"/"TARGET"), and rendered empty picture placeholders
as broken-image icons.
"""

from .render import render_deck

__all__ = ["render_deck"]
