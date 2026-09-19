"""Review, fix, re-review: weak pages are repaired at the spec slide they came from.

WHAT IT CAN FIX. Pages that are crowded -- measured overflow, overlap,
off-page text, type under the minimum, too many words, or a reviewer
rating readability 2 or less -- are given fewer items per page
(`max_items` on the spec slide). The renderer then paginates that slide
more finely, so each page has room and its text is set larger. Nothing
about the content changes: the same items, split differently.

WHAT IT CANNOT. A page with a weak headline or a thin argument needs
different content, not different packaging. Those are left alone and
reported, never "fixed" by a model rewriting validated slides after the
fact.

EVERY CHANGE MUST EARN ITS PLACE. After re-rendering, only the changed
slides' pages are reviewed again; the rest carry their reviews forward.
A change is kept only if that slide's pages score higher than before;
otherwise the slide goes back to how it was. The history of every round
is returned with the result, so the operator sees what was tried.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import qa, render

logger = logging.getLogger("pptx.improve")

# The list field each layout paginates, and so the one max_items acts on.
ITEM_FIELD = {"points": "bullets", "kpis": "items", "table": "rows", "process": "steps",
              "timeline": "events", "comparison": "columns", "actions": "items"}
CROWDED = {"overflow", "overlap", "off_page", "small_type", "dense"}
MAX_ROUNDS = 2
MIN_GAIN = 0.1


@dataclass
class Round:
    round: int
    tried: dict[str, int]      # "section/slide" -> max_items tried
    kept: list[str]
    reverted: list[str]
    score_before: float | None
    score_after: float | None


@dataclass
class Improvement:
    quality: qa.DeckQuality
    spec: dict
    path: str
    rounds: list[Round] = field(default_factory=list)
    unfixable: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"quality": self.quality.to_dict(), "path": self.path,
                "rounds": [asdict(r) for r in self.rounds], "unfixable": self.unfixable}


def page_keys(page_map: list) -> list[tuple]:
    """A stable identity per rendered page: (spec slide or None, n-th page of it).

    Page NUMBERS shift when one slide paginates differently; these keys do
    not, so a review can follow its page into the next render.
    """
    keys, seen = [], {}
    for entry in page_map:
        base = tuple(entry) if entry is not None else None
        n = seen.get(base, 0)
        seen[base] = n + 1
        keys.append((base, n))
    return keys


def _slide(spec: dict, key: tuple) -> dict:
    return spec["sections"][key[0]]["slides"][key[1]]


def _label(key: tuple) -> str:
    return f"{key[0]}/{key[1]}"


def remedy(page: qa.PageQuality, sd: dict, pages_of_slide: int) -> int | None:
    """Fewer items per page for a crowded page, or None when that cannot help."""
    crowded = bool(CROWDED & set(page.defects)) or page.ratings.get("readability", 5) <= 2
    field_name = ITEM_FIELD.get(sd.get("type"))
    if not crowded or not field_name:
        return None
    n = len(sd.get(field_name) or [])
    per_page = math.ceil(n / max(1, pages_of_slide))
    if per_page <= 1:
        return None
    return per_page - 1


def _needs_work(page: qa.PageQuality) -> bool:
    return (page.score is not None and page.score < qa.PASS_SCORE) or bool(CROWDED & set(page.defects))


def _slide_scores(quality: qa.DeckQuality, keys: list[tuple]) -> dict[tuple, float]:
    by: dict[tuple, list[float]] = {}
    for page, key in zip(quality.pages, keys):
        if key[0] is not None and page.score is not None:
            by.setdefault(key[0], []).append(page.score)
    return {k: sum(v) / len(v) for k, v in by.items()}


def _carry(old_quality: qa.DeckQuality, old_keys: list, new_keys: list, changed: set) -> qa.DeckQuality:
    """Old reviews renumbered onto the new render's pages, for unchanged slides only."""
    by_key = {k: p for p, k in zip(old_quality.pages, old_keys)}
    pages = []
    for i, key in enumerate(new_keys, 1):
        old = by_key.get(key)
        if old is not None and key[0] not in changed:
            pages.append(replace(old, page=i))
    return replace(old_quality, pages=pages)


def _assess(path: str, keys: list, *, vision: bool, review: set, previous, progress):
    pages = [i for i, k in enumerate(keys, 1) if k[0] in review] if previous is not None else None
    return qa.assess(path, vision=vision, pages=pages, previous=previous, progress=progress,
                     release_after=False)


def improve(spec: dict, out_path: str | Path, *, vision: bool = True, max_rounds: int = MAX_ROUNDS,
            progress=None) -> Improvement:
    """Render `spec` to `out_path`, assess it, and repair weak pages round by round."""
    spec = copy.deepcopy(spec)
    out_path = str(out_path)
    try:
        result = render.render_deck(spec, out_path)
        keys = page_keys(result["page_map"])
        quality = _assess(out_path, keys, vision=vision, review=set(), previous=None, progress=progress)
        rounds: list[Round] = []
        if quality.method == "unavailable":
            return Improvement(quality, spec, out_path, rounds)

        for rnd in range(1, max_rounds + 1):
            pages_per_slide: dict[tuple, int] = {}
            for k in keys:
                if k[0] is not None:
                    pages_per_slide[k[0]] = pages_per_slide.get(k[0], 0) + 1
            tried: dict[tuple, int] = {}
            for page, key in zip(quality.pages, keys):
                # A measured defect is worth fixing even on a page that scores
                # above the pass mark: overflow alone leaves a page at 8/10.
                if key[0] is None or key[0] in tried or not _needs_work(page):
                    continue
                fix = remedy(page, _slide(spec, key[0]), pages_per_slide[key[0]])
                if fix is not None:
                    tried[key[0]] = fix
            if not tried:
                break

            before_scores = _slide_scores(quality, keys)
            candidate = copy.deepcopy(spec)
            for sk, max_items in tried.items():
                _slide(candidate, sk)["max_items"] = max_items
            trial_path = str(Path(out_path).with_suffix(f".round{rnd}.pptx"))
            trial = render.render_deck(candidate, trial_path)
            trial_keys = page_keys(trial["page_map"])
            trial_quality = _assess(trial_path, trial_keys, vision=vision, review=set(tried),
                                    previous=_carry(quality, keys, trial_keys, set(tried)),
                                    progress=progress)
            after_scores = _slide_scores(trial_quality, trial_keys)
            kept = {sk for sk in tried if after_scores.get(sk, 0) >= before_scores.get(sk, 10) + MIN_GAIN}
            reverted = set(tried) - kept

            if kept and not reverted:
                spec, keys, quality = candidate, trial_keys, trial_quality
                Path(trial_path).replace(out_path)
            elif kept:
                for sk in kept:
                    _slide(spec, sk)["max_items"] = tried[sk]
                result = render.render_deck(spec, out_path)
                new_keys = page_keys(result["page_map"])
                # Every page already has a review: kept slides' from the
                # trial, everything else's from before. Measure, review nothing.
                by_page = {p.page: p for p in _carry(quality, keys, new_keys, kept).pages}
                by_page.update({p.page: p for p in _carry(trial_quality, trial_keys, new_keys, reverted).pages})
                merged = replace(quality, pages=[by_page[i] for i in sorted(by_page)])
                quality = _assess(out_path, new_keys, vision=vision, review=set(),
                                  previous=merged, progress=progress)
                keys = new_keys
                Path(trial_path).unlink(missing_ok=True)
            else:
                Path(trial_path).unlink(missing_ok=True)

            rounds.append(Round(
                round=rnd, tried={_label(k): v for k, v in tried.items()},
                kept=sorted(_label(k) for k in kept), reverted=sorted(_label(k) for k in reverted),
                score_before=round(sum(before_scores.values()) / len(before_scores), 2) if before_scores else None,
                score_after=quality.score,
            ))
            if not kept:
                break

        unfixable = [
            {"page": p.page, "title": p.title, "score": p.score, "defects": p.defects, "issues": p.issues}
            for p in quality.pages if _needs_work(p)
        ]
        return Improvement(quality, spec, out_path, rounds, unfixable)
    finally:
        from backend.models import local_vision

        local_vision.release()
