"""Deck quality: every page measured by PowerPoint and looked at by the vision model.

TWO KINDS OF EVIDENCE, AND WHY BOTH.

  Layout, measured. PowerPoint lays the deck out and reports where every
  paragraph actually lands (TextRange.Bound*). That catches, with certainty,
  text taller than its box, text over other text, anything off the page,
  type too small to read, and pages crammed with words. The deck design
  system is built not to do these; this is how we KNOW it did not.

  Design, judged. A slide can pass every measurement and still look bad:
  lopsided, crowded, empty, weak hierarchy. The local vision model
  (models.yaml `vision-model`) looks at each rendered page against a fixed
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

logger = logging.getLogger("pptx.qa")

# Measured-defect penalties, in score points.
PENALTY = {"overflow": 2.0, "overlap": 4.0, "off_page": 4.0, "small_type": 1.0, "dense": 1.0}
MIN_FONT_PT = 10.5
MAX_WORDS_PER_PAGE = 110
PASS_SCORE = 7.0

_RUBRIC = """You are a senior presentation designer reviewing ONE slide from a corporate
refinery operations briefing. Judge ONLY how it looks and reads, never the facts.

Check: text overlapping other text or cut off; text too small to read; crowding
(too much text for the space); awkward empty space or a sparse, unfinished look;
alignment and balance; visual hierarchy (is the takeaway obvious?); contrast.

Score from 1 to 10:
 10 = boardroom-ready, nothing to change
  8 = good, one minor issue
  6 = acceptable, noticeable issues
  4 = poor, several problems
  2 = broken: overlapping or cut-off text, unreadable

Reply with ONLY: {"score": <integer 1-10>, "issues": ["short specific issue", ...]}
List at most 3 issues. An empty list means you found none."""


@dataclass
class PageQuality:
    page: int
    title: str
    score: float | None
    vision_score: int | None = None
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
            for shape in slide.Shapes:
                if not (shape.HasTextFrame and shape.TextFrame.HasText):
                    continue
                tr = shape.TextFrame.TextRange
                text = tr.Text.strip()
                count += len(text.split())
                size = tr.Font.Size
                if size and size > biggest[0] and len(text) > 8:
                    biggest = (size, text)
                if size and 0 < size < MIN_FONT_PT and len(text) > 3 and not text.isdigit():
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


def review_page(png: str, *, model_id: str = "vision-model", timeout: int = 240) -> dict | None:
    """The vision model's score and issues for one rendered page, or None."""
    try:
        import requests

        from backend.models.ollama_client import OLLAMA_HOST
        from backend.models.registry import resolve_model_name

        image = base64.b64encode(Path(png).read_bytes()).decode()
        res = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": resolve_model_name(model_id), "prompt": _RUBRIC, "images": [image],
                  "format": "json", "stream": False, "options": {"temperature": 0}},
            timeout=timeout,
        )
        res.raise_for_status()
        data = json.loads(res.json().get("response") or "{}")
        score = int(data.get("score"))
        if not 1 <= score <= 10:
            return None
        issues = [str(i).strip() for i in (data.get("issues") or []) if str(i).strip()][:3]
        return {"score": score, "issues": issues}
    except Exception as exc:  # noqa: BLE001 - an unreviewed page is reported as such
        logger.info("Vision review failed for %s: %s", png, exc)
        return None


# ── the assessment ──────────────────────────────────────────────────────────


def assess(pptx: str | Path, *, vision: bool = True, pages: list[int] | None = None,
           previous: DeckQuality | None = None, progress=None) -> DeckQuality:
    """Measure every page, and have the vision model review `pages` (default all).

    `previous` lets a re-assessment after a fix re-review only the pages
    that changed and carry the other pages' reviews forward.
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
            review = {"score": carried[idx].vision_score, "issues": carried[idx].issues}
        reviewed_any = reviewed_any or review is not None
        penalty = sum(PENALTY[d] for d in defects)
        base = float(review["score"]) if review else 10.0
        score = max(1.0, min(10.0, base - penalty))
        out.append(PageQuality(
            page=idx, title=measured["titles"].get(idx, ""), score=round(score, 1),
            vision_score=review["score"] if review else None,
            issues=(review["issues"] if review else []), defects=defects,
        ))

    deck_score = round(sum(p.score for p in out) / len(out), 1) if out else None
    method = "layout+vision" if reviewed_any else "layout"
    note = "" if reviewed_any else (
        "Layout was measured on every page; the vision model did not review any page, so the "
        "score reflects measured defects only.")
    from backend.models.registry import resolve_model_name

    try:
        reviewer = resolve_model_name("vision-model") if reviewed_any else None
    except Exception:  # noqa: BLE001
        reviewer = None
    return DeckQuality(score=deck_score, grade=grade_for(deck_score), method=method, pages=out,
                       reviewed_by=reviewer, note=note)
