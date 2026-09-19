"""Deck quality: every page measured by PowerPoint and looked at by the vision model.

TWO KINDS OF EVIDENCE, AND WHY BOTH.

  Layout, measured. PowerPoint lays the deck out and reports where every
  paragraph actually lands (TextRange.Bound*). That catches, with certainty,
  text taller than its box, text over other text, anything off the page,
  type too small to read, and pages crammed with words. The deck design
  system is built not to do these; this is how we KNOW it did not.

  Design, judged. A slide can pass every measurement and still look bad:
  lopsided, crowded, empty, weak hierarchy. The local vision model
  (models.yaml `page-reviewer`) looks at each rendered page against a fixed
  rubric and scores it 1-10 with specific issues. It is a judgement, not a
  measurement, and it is reported as one.

The page score is the vision score less penalties for measured defects; a
deck with no vision model available is scored on layout alone and SAYS so.
Nothing is ever reported as reviewed that was not.

Requires PowerPoint (Windows) to render and measure. Where it is missing
the result says `method: "unavailable"` rather than inventing a score.
"""

from __future__ import annotations

import base64
import json
import logging
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.tools.generation.deck import theme

logger = logging.getLogger("pptx.qa")

# Measured-defect penalties, in score points.
PENALTY = {"overflow": 2.0, "overlap": 4.0, "off_page": 4.0, "small_type": 1.0, "dense": 1.0,
           "empty": 6.0}
MIN_FONT_PT = 10.5
MAX_WORDS_PER_PAGE = 110
PASS_SCORE = 7.0
FOOTER_TOP_PT = theme.FOOTER_Y * 72
BODY_TOP_PT = (theme.BODY_Y - 0.3) * 72

# The model rates what it can SEE on four named dimensions; the page score
# is computed here from those ratings (hard constraint #3: no arithmetic by
# a model). Overlap, overflow and tiny type are deliberately NOT asked:
# PowerPoint measures them exactly, and a first rubric that listed them
# was echoed back verbatim ("text overlapping other text") on pages
# measured to have none.
DIMENSIONS = ("balance", "readability", "hierarchy", "finish")
_RUBRIC = """Look at this presentation slide image and rate what you see.

balance: 1 = content bunched in one area with most of the slide blank, 5 = content fills the slide evenly
readability: 1 = walls of small text, 5 = can be read at a glance
hierarchy: 1 = no clear headline or main point, 5 = one clear headline and an obvious takeaway
finish: 1 = plain or amateur, 5 = looks professionally designed

Reply with ONLY this JSON:
{"balance": 1-5, "readability": 1-5, "hierarchy": 1-5, "finish": 1-5, "fix": "the single element that most needs fixing, described by where it is and what it says, or an empty string"}"""


@dataclass
class PageQuality:
    page: int
    title: str
    score: float | None
    vision_score: float | None = None
    ratings: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)


@dataclass
class DeckQuality:
    score: float | None
    grade: str
    method: str  # "layout+vision" | "layout" | "unavailable"
    pages: list[PageQuality]
    reviewed_by: str | None = None
    note: str = ""
    # Layout is measured on every page whatever else happens; this is the
    # count of pages with at least one measured defect.
    layout_defect_pages: int = 0
    pages_reviewed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def weak_pages(self) -> list[PageQuality]:
        return [p for p in self.pages if p.score is not None and p.score < PASS_SCORE]


def grade_for(score: float | None) -> str:
    if score is None:
        return "unrated"
    if score >= 8.5:
        return "A"
    if score >= 7.0:
        return "B"
    if score >= 5.5:
        return "C"
    return "D"


# ── PowerPoint: render + measure ────────────────────────────────────────────


def render_and_measure(pptx: str | Path, out_dir: str | Path, width_px: int = 960) -> dict | None:
    """Export every page to PNG and measure every text shape, via PowerPoint.

    Returns {"pngs": [path...], "defects": {page: [str]}, "titles": {page: str},
    "words": {page: int}} or None when PowerPoint is unavailable.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        pres = app.Presentations.Open(str(Path(pptx).resolve()), True, False, False)
        sw, sh = pres.PageSetup.SlideWidth, pres.PageSetup.SlideHeight
        height_px = int(width_px * sh / sw)
        pngs, defects, titles, words = [], {}, {}, {}
        for slide in pres.Slides:
            i = slide.SlideIndex
            png = out_dir / f"page_{i:02d}.png"
            slide.Export(str(png), "PNG", width_px, height_px)
            pngs.append(str(png))
            boxes, found, count, biggest = [], set(), 0, (0, "")
            body_content = 0
            for shape in slide.Shapes:
                # Anything centred in the body band that carries content: text, a
                # chart, a table or a picture. Rules and bars do not count.
                if BODY_TOP_PT <= shape.Top + shape.Height / 2 < FOOTER_TOP_PT - 1 and (
                        (shape.HasTextFrame and shape.TextFrame.HasText) or shape.HasChart
                        or shape.HasTable or shape.Type == 13):
                    body_content += 1
                if not (shape.HasTextFrame and shape.TextFrame.HasText):
                    continue
                tr = shape.TextFrame.TextRange
                text = tr.Text.strip()
                count += len(text.split())
                size = tr.Font.Size
                if size and size > biggest[0] and len(text) > 8:
                    biggest = (size, text)
                # The footer band (source line, classification, page number)
                # is 9 pt by design; the minimum applies to content.
                # Short all-caps labels (status pills, table headers, cover
                # metadata) are 10 pt caps by design and read at that size.
                in_footer = shape.Top >= FOOTER_TOP_PT - 1
                label = text.isupper() and len(text.split()) <= 3
                if size and 0 < size < MIN_FONT_PT and len(text) > 3 and not (in_footer or label):
                    found.add("small_type")
                bl, bt, bw, bh = tr.BoundLeft, tr.BoundTop, tr.BoundWidth, tr.BoundHeight
                if bh > shape.Height + 2:
                    found.add("overflow")
                if bl < -1 or bt < -1 or bl + bw > sw + 1 or bt + bh > sh + 1:
                    found.add("off_page")
                boxes.append((bl, bt, bw, bh))
            for a in range(len(boxes)):
                for b in range(a + 1, len(boxes)):
                    ax, ay, aw, ah = boxes[a]
                    bx, by, bw_, bh_ = boxes[b]
                    if min(ax + aw, bx + bw_) - max(ax, bx) > 2 and min(ay + ah, by + bh_) - max(ay, by) > 2:
                        found.add("overlap")
            if count > MAX_WORDS_PER_PAGE:
                found.add("dense")
            # A page with a header and nothing under it: the timeline whose
            # events all lacked a title rendered a bare axis like this.
            if body_content == 0:
                found.add("empty")
            defects[i] = sorted(found)
            words[i] = count
            titles[i] = biggest[1].replace("\r", " ")[:90]
        pres.Close()
        return {"pngs": pngs, "defects": defects, "titles": titles, "words": words}
    except Exception as exc:  # noqa: BLE001 - reported as unavailable, never as a score
        logger.warning("PowerPoint render/measure failed: %s: %s", type(exc).__name__, exc)
        return None
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:  # noqa: BLE001
                pass
        pythoncom.CoUninitialize()


# ── vision review ───────────────────────────────────────────────────────────


REVIEWER_ID = "page-reviewer"


def _parse_review(reply: str) -> dict | None:
    """Ratings -> a 1-10 page score, computed here. None when unusable."""
    from backend.utils.llm_output import strip_code_fences

    text = strip_code_fences(reply or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    ratings = {}
    for dim in DIMENSIONS:
        try:
            value = int(data.get(dim))
        except (TypeError, ValueError):  # missing, or a range like "2-5"
            return None
        if not 1 <= value <= 5:
            return None
        ratings[dim] = value
    # Mean rating 1..5 mapped linearly onto 1..10.
    score = round(1 + (sum(ratings.values()) / len(ratings) - 1) * 9 / 4, 1)
    fix = str(data.get("fix") or "").strip()
    return {"score": score, "ratings": ratings, "issues": [fix] if fix else []}


def review_page(png: str, *, model_id: str = REVIEWER_ID, timeout: int = 240) -> dict | None:
    """The reviewer model's score and issues for one rendered page, or None.

    Which model, and how it runs, is models.yaml's call: a `transformers`
    entry runs in-process with the GPU/CPU split its `placement` sets; an
    `ollama` entry goes to the daemon.
    """
    try:
        from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

        cfg = load_registry(_DEFAULT_REGISTRY_PATH)[model_id]
        if cfg.backend == "transformers":
            from backend.models import local_vision

            return _parse_review(local_vision.ask(model_id, png, _RUBRIC, max_new_tokens=160))

        import requests

        from backend.models.ollama_client import OLLAMA_HOST

        image = base64.b64encode(Path(png).read_bytes()).decode()
        res = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": cfg.model, "prompt": _RUBRIC, "images": [image],
                  "format": "json", "stream": False, "options": {"temperature": 0}},
            timeout=timeout,
        )
        res.raise_for_status()
        return _parse_review(res.json().get("response") or "")
    except Exception as exc:  # noqa: BLE001 - an unreviewed page is reported as such
        logger.warning("Page review failed for %s: %s: %s", png, type(exc).__name__, exc)
        return None


# ── the assessment ──────────────────────────────────────────────────────────


def assess(pptx: str | Path, *, vision: bool = True, pages: list[int] | None = None,
           previous: DeckQuality | None = None, progress=None,
           release_after: bool = True) -> DeckQuality:
    """Measure every page, and have the vision model review `pages` (default all).

    `previous` lets a re-assessment after a fix re-review only the pages
    that changed and carry the other pages' reviews forward. The reviewer
    stays loaded across pages and is released at the end unless
    `release_after` is False (an improve loop that will call again).
    """
    work = Path(tempfile.mkdtemp(prefix="deckqa-"))
    measured = render_and_measure(pptx, work)
    if measured is None:
        return DeckQuality(score=None, grade="unrated", method="unavailable", pages=[],
                           note="PowerPoint is not available on this machine, so the deck was not "
                                "rendered or reviewed. No score is given rather than a guessed one.")

    carried = {p.page: p for p in (previous.pages if previous else [])}
    out: list[PageQuality] = []
    reviewed_any = False
    total = len(measured["pngs"])
    for idx, png in enumerate(measured["pngs"], 1):
        defects = measured["defects"].get(idx, [])
        review = None
        if vision and (pages is None or idx in pages):
            if progress:
                progress(f"Reviewing page {idx} of {total}")
            review = review_page(png)
        elif idx in carried and carried[idx].vision_score is not None:
            review = {"score": carried[idx].vision_score, "issues": carried[idx].issues,
                      "ratings": carried[idx].ratings}
        reviewed_any = reviewed_any or review is not None
        penalty = sum(PENALTY[d] for d in defects)
        base = float(review["score"]) if review else 10.0
        score = max(1.0, min(10.0, base - penalty))
        out.append(PageQuality(
            page=idx, title=measured["titles"].get(idx, ""), score=round(score, 1),
            vision_score=review["score"] if review else None,
            issues=(review["issues"] if review else []), defects=defects,
            ratings=(review.get("ratings", {}) if review else {}),
        ))

    if release_after:
        from backend.models import local_vision

        local_vision.release()

    # The deck score and grade are a DESIGN judgement, so they exist only
    # where the reviewer looked, and cover only the pages it looked at. A
    # layout-only 10/10 would read as "excellent" when it means "no measured
    # defects"; a failed review counted as 10-minus-penalties would inflate
    # the average with pages nobody judged.
    reviewed = [p for p in out if p.vision_score is not None]
    deck_score = round(sum(p.score for p in reviewed) / len(reviewed), 1) if reviewed else None
    defect_pages = sum(1 for p in out if p.defects)
    method = "layout+vision" if reviewed_any else "layout"
    if not reviewed_any:
        note = (f"Layout was measured on all {len(out)} pages ({defect_pages} with defects). The design "
                "reviewer did not look at any page, so no design score or grade is given.")
    elif len(reviewed) < len(out):
        note = (f"The design reviewer scored {len(reviewed)} of {len(out)} pages; the deck score "
                "covers those pages only.")
    else:
        note = ""
    from backend.models.registry import resolve_model_name

    try:
        reviewer = resolve_model_name(REVIEWER_ID) if reviewed_any else None
    except Exception:  # noqa: BLE001
        reviewer = None
    return DeckQuality(score=deck_score, grade=grade_for(deck_score), method=method, pages=out,
                       reviewed_by=reviewer, note=note, layout_defect_pages=defect_pages,
                       pages_reviewed=len(reviewed))
