"""Summarising a book the way a reader would: by its own chapters.

WHY THIS EXISTS. The generic long-source path plans a report from
passages sampled across the document. On a 437-page textbook that
produced sections on whatever the samples happened to hit -- ARP table
entries and a list of keylogger product names -- while phishing was
spread over four sections and the law over five, with no overview and no
sense of the book's own argument. A book already has a structure; a
summary should follow it.

THE PIPELINE.

  1. STRUCTURE. The table of contents gives the chapters' numbers and
     titles (one model call over the front matter). Where each chapter
     STARTS in the scan is found from the book's own numbering: every page
     carries section, figure and table numbers ("4.4.2 Offline Attacks",
     "Figure 4.12") whose first number is its chapter, and the best
     non-decreasing chapter labelling of the pages marks the boundaries.
     Printed page numbers are not used -- in a scan they do not line up
     with the file's pages.
  2. READ. Every page of every chapter is read, in windows, and each
     window's key points are extracted with the page they came from.
  3. WRITE. Each chapter is written from its own points only.
  4. CHECK. Every chapter's sentences are checked against its points and
     the unsupported ones are removed -- the numeric check proves a figure
     exists in the source, this checks what is said about it.
  5. OVERVIEW. Written last, from the checked chapters.
  6. COVERAGE is stated: which chapters the file holds, and which the
     contents list but the file does not.

Everything here is local model calls through the registry; nothing is
written to disk.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from backend.orchestrator.deck_agent import _ask_json, _numbers, writer_timeout

logger = logging.getLogger("documents.book")

# Front matter is looked at for a table of contents only within this share
# of the book.
FRONT_MATTER_SHARE = 0.08
# A window of chapter text read in one extraction call.
WINDOW_CHARS = 7000
# Calls in flight at once (Ollama serves them from one resident model).
WORKERS = 5
# Points handed to one chapter-writing call; beyond this the chapter is
# written in consecutive parts.
POINTS_PER_WRITE = 70

_SECTION_NUMBER = re.compile(
    r"(?:(?:Figure|Fig\.|Table|Box)\s+(\d{1,2})\.\d{1,2}"
    r"|(?:^|\s)(\d{1,2})\.\d{1,2}(?:\.\d{1,2})?\s+[A-Z][a-z])"
)
# Things a model says about the task instead of about the book.
_META = re.compile(
    r"\[S\d+\]|according to the (?:text|passages?|sources?|extract)|as requested|"
    r"this (?:report )?section|not provided in the (?:sources?|passages?|text)|"
    r"the (?:passages?|extracts?) (?:above|below|provided)|it is known that",
    re.I,
)


@dataclass
class Chapter:
    number: int
    title: str
    first_page: int | None = None
    last_page: int | None = None
    points: list[dict] = field(default_factory=list)
    body: str = ""
    removed: list[str] = field(default_factory=list)

    @property
    def in_file(self) -> bool:
        return self.first_page is not None


# ── 1. structure ────────────────────────────────────────────────────────────


def pages_of(chunks: list, document: str) -> dict[int, str]:
    """The document's text by page number, in reading order."""
    by_page: dict[int, list[tuple[int, str]]] = {}
    for c in chunks:
        if c.metadata.source_document != document or not c.metadata.page_number:
            continue
        by_page.setdefault(c.metadata.page_number, []).append((c.metadata.chunk_index or 0, c.text))
    return {p: "\n".join(t for _i, t in sorted(parts)) for p, parts in sorted(by_page.items())}


def contents_pages(pages: dict[int, str]) -> list[int]:
    """Front-matter pages that look like a table of contents."""
    limit = max(12, int(max(pages or [0]) * FRONT_MATTER_SHARE))
    found = [p for p, t in pages.items() if p <= limit and re.search(r"\bcont[ae]nt", t, re.I)]
    return found


def read_contents(pages: dict[int, str], *, writer: str) -> tuple[str, list[Chapter]]:
    """The book's title and its chapters, from its own table of contents."""
    toc = contents_pages(pages)
    first = "\n".join(pages.get(p, "") for p in sorted(pages)[:3])[:2500]
    toc_text = "\n".join(pages[p] for p in toc)[:14000]
    if not toc_text.strip():
        return "", []
    prompt = f"""Below are the title pages and the table of contents of a book, from OCR of a scan
(expect OCR noise and numbers out of place).

TITLE PAGES:
{first}

TABLE OF CONTENTS:
{toc_text}

Give the book's full title, and its CHAPTERS only -- numbered top-level chapters, not
sections like 4.2 or front matter like Preface, not appendices. Correct obvious OCR
spelling. Keep the chapters in order.

Reply with ONLY this JSON object:
{{"title": "...", "chapters": [{{"number": 1, "title": "..."}}]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=8192)
    if not isinstance(data, dict):
        return "", []
    chapters: list[Chapter] = []
    for item in data.get("chapters") or []:
        try:
            number = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        title = " ".join(str(item.get("title") or "").split())
        if title and number == len(chapters) + 1:
            chapters.append(Chapter(number=number, title=title))
    return " ".join(str(data.get("title") or "").split()), chapters


def chapter_votes(pages: dict[int, str], after: int, n_chapters: int) -> dict[int, Counter]:
    """Per page, which chapter numbers its section/figure/table numbers name."""
    votes: dict[int, Counter] = {}
    for p, text in pages.items():
        if p <= after:
            continue
        c: Counter = Counter()
        for m in _SECTION_NUMBER.finditer(text):
            n = int(m.group(1) or m.group(2))
            if 1 <= n <= n_chapters:
                c[n] += 1
        votes[p] = c
    return votes


def locate_chapters(votes: dict[int, Counter], n_chapters: int) -> dict[int, int]:
    """First page of each chapter: the best NON-DECREASING labelling of pages.

    A page's own votes are noisy -- OCR, cross-references to other chapters,
    decimals that look like section numbers -- so no single page decides.
    The labelling that disagrees least with all the votes, subject to
    chapters only ever increasing through the book, does. A greedy first-
    appearance rule failed on this exactly: one early page naming chapter 11
    blocked every chapter after it.
    """
    pages = sorted(votes)
    if not pages:
        return {}
    k_max = n_chapters
    inf = float("inf")
    cost = [[inf] * (k_max + 1) for _ in pages]
    back = [[0] * (k_max + 1) for _ in pages]
    for i, p in enumerate(pages):
        total = sum(votes[p].values())
        for k in range(1, k_max + 1):
            here = total - votes[p].get(k, 0)
            if i == 0:
                cost[i][k] = here
                continue
            j = min(range(1, k + 1), key=lambda j: cost[i - 1][j])
            cost[i][k] = cost[i - 1][j] + here
            back[i][k] = j
    k = min(range(1, k_max + 1), key=lambda k: cost[-1][k])
    labels = [0] * len(pages)
    for i in range(len(pages) - 1, -1, -1):
        labels[i] = k
        k = back[i][k]
    starts: dict[int, int] = {}
    for p, label in zip(pages, labels):
        # A chapter is only placed where its own numbers actually appear:
        # the labelling may carry a chapter over blank or unnumbered pages,
        # but it must not invent one the pages never mention.
        if label not in starts and votes[p].get(label):
            starts[label] = p
    return starts


# ── 2. read ─────────────────────────────────────────────────────────────────


def windows(pages: dict[int, str], first: int, last: int) -> list[tuple[int, int, str]]:
    """Consecutive pages of a chapter, grouped into windows of about WINDOW_CHARS."""
    out: list[tuple[int, int, str]] = []
    start, buf = None, []
    size = 0
    for p in range(first, last + 1):
        text = pages.get(p, "").strip()
        if not text:
            continue
        if start is None:
            start = p
        buf.append(f"[page {p}]\n{text}")
        size += len(text)
        if size >= WINDOW_CHARS:
            out.append((start, p, "\n\n".join(buf)))
            start, buf, size = None, [], 0
    if buf:
        out.append((start, last, "\n\n".join(buf)))
    return out


def extract_points(chapter: Chapter, window: tuple[int, int, str], *, writer: str) -> list[dict]:
    """The key points one window of a chapter makes, each with its page."""
    first, last, text = window
    prompt = f"""Below are pages {first}-{last} of chapter {chapter.number}, "{chapter.title}", of a book.
The text is OCR of a scanned page: correct obvious OCR spelling errors, but never change a
fact, name, section number or figure.

PAGES:
{text}

List the important points these pages make: definitions, classifications, how something
works, legal provisions (with their section numbers), cases and examples, figures that
matter. Each point is one or two complete sentences in the book's own terms. Skip running
headers, page numbers, review questions, reference lists and bare figure captions.
Between 4 and 12 points.

Reply with ONLY this JSON object:
{{"points": [{{"point": "...", "page": {first}}}]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=8192)
    points = []
    items = data.get("points") if isinstance(data, dict) else None
    for item in items or []:
        if not isinstance(item, dict):
            continue
        point = " ".join(str(item.get("point") or "").split())
        if len(point) < 25:
            continue
        try:
            page = int(item.get("page"))
        except (TypeError, ValueError):
            page = first
        points.append({"point": point, "page": min(max(page, first), last)})
    return points


# ── 3-4. write and check ────────────────────────────────────────────────────


def write_chapter(chapter: Chapter, request: str, *, writer: str) -> str:
    """The chapter's summary, from its points only, in consecutive parts."""
    parts: list[str] = []
    batches = [chapter.points[i:i + POINTS_PER_WRITE]
               for i in range(0, len(chapter.points), POINTS_PER_WRITE)]
    for index, batch in enumerate(batches, 1):
        listing = "\n".join(f"- (p.{pt['page']}) {pt['point']}" for pt in batch)
        position = (f" This is part {index} of {len(batches)} of the chapter; continue from the "
                    "previous part without repeating an introduction." if len(batches) > 1 and index > 1
                    else "")
        prompt = f"""You are writing the summary of chapter {chapter.number}, "{chapter.title}", for a
reader who has not read the book. Use ONLY the points below, which were taken from the
chapter itself, in the order the chapter makes them.{position}

REQUEST THE SUMMARY SERVES: {request}

POINTS:
{listing}

Write 3 to 5 paragraphs of clear, connected prose that explain what the chapter teaches,
in its own terms. Group related points; keep definitions, section numbers, cases and
figures exactly as given. Do not add anything the points do not say. Do not mention
"points", "the text", "the passage" or page numbers. No headings, no bullet points.

Reply with ONLY this JSON object:
{{"paragraphs": ["...", "..."]}}"""
        data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=12288)
        raw = data.get("paragraphs") if isinstance(data, dict) else None
        parts.extend(" ".join(str(p).split()) for p in (raw or []) if str(p).strip())
    return "\n\n".join(parts)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text) if s.strip()]


def check_chapter(chapter: Chapter, source_text: str, *, writer: str) -> None:
    """Remove the chapter summary's sentences its points do not support.

    Three layers, cheapest first: sentences talking about the task rather
    than the book; sentences with a figure the whole book does not contain;
    then the model is asked which remaining sentences the points do not
    support. What is removed is kept on the chapter, for the report.
    """
    sourced = _numbers(source_text)
    kept_paragraphs = []
    for paragraph in chapter.body.split("\n\n"):
        kept = []
        for sentence in _sentences(paragraph):
            if _META.search(sentence):
                chapter.removed.append(f"talks about the task: {sentence[:90]}")
                continue
            if {n for n in _numbers(sentence) if n >= 10 and n not in sourced}:
                chapter.removed.append(f"figure not in the book: {sentence[:90]}")
                continue
            kept.append(sentence)
        if kept:
            kept_paragraphs.append(" ".join(kept))
    chapter.body = "\n\n".join(kept_paragraphs)
    if not chapter.body:
        return

    numbered = _sentences(chapter.body)
    listing = "\n".join(f"- {pt['point']}" for pt in chapter.points)
    claims = "\n".join(f"{i}. {s}" for i, s in enumerate(numbered, 1))
    prompt = f"""Check a summary of chapter {chapter.number}, "{chapter.title}", against the points it was
written from.

POINTS (the only evidence):
{listing}

SUMMARY SENTENCES:
{claims}

List the numbers of the sentences that state something the points do NOT support: a claim,
a qualification, a cause, a legal consequence or a figure that is not in the points.
Rewording and combining supported points is fine. When in doubt, the sentence is
unsupported.

Reply with ONLY this JSON object:
{{"unsupported": [3, 7]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=12288)
    raw = data.get("unsupported") if isinstance(data, dict) else None
    try:
        bad = {int(n) for n in (raw or [])}
    except (TypeError, ValueError):
        bad = set()
    # A checker that rejects most of a chapter is more likely wrong than the
    # chapter: that result is recorded and the chapter kept as written.
    if len(bad) > len(numbered) * 0.5:
        chapter.removed.append(f"checker rejected {len(bad)} of {len(numbered)} sentences; not applied")
        return
    if not bad:
        return
    drop = {numbered[i - 1] for i in bad if 1 <= i <= len(numbered)}
    chapter.removed.extend(f"unsupported by the chapter: {s[:90]}" for s in drop)
    chapter.body = "\n\n".join(
        " ".join(s for s in _sentences(par) if s not in drop)
        for par in chapter.body.split("\n\n")
        if any(s not in drop for s in _sentences(par))
    )


def write_overview(title: str, chapters: list[Chapter], request: str, *, writer: str) -> str:
    """An overview of the whole book, from the checked chapter summaries."""
    digest = "\n\n".join(f"Chapter {c.number}, {c.title}:\n{c.body[:2200]}" for c in chapters if c.body)
    prompt = f"""Write the opening overview of a summary of the book "{title}", for a reader deciding
whether and where to read it. Use ONLY the chapter summaries below.

REQUEST THE SUMMARY SERVES: {request}

CHAPTER SUMMARIES:
{digest}

Write 3 or 4 paragraphs: what the book is about and who it is for, how its argument
develops across the chapters, and the ideas a reader should take away. Do not add facts
the summaries do not contain. No headings, no bullet points.

Reply with ONLY this JSON object:
{{"paragraphs": ["...", "..."]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=12288)
    paragraphs = data.get("paragraphs") if isinstance(data, dict) else None
    return "\n\n".join(" ".join(str(p).split()) for p in (paragraphs or []) if str(p).strip())


# ── the whole thing ─────────────────────────────────────────────────────────


def summarise_book(request: str, document: str, chunks: list, *, writer: str, progress=None) -> dict | None:
    """A chapter-by-chapter summary, or None when the book's structure is not found.

    None is not a failure: the caller falls back to the generic long-source
    path for a document with no table of contents.
    """
    say = progress or (lambda _msg: None)
    pages = pages_of(chunks, document)
    if len(pages) < 40:
        return None

    say("Reading the table of contents")
    title, chapters = read_contents(pages, writer=writer)
    if len(chapters) < 2:
        return None
    toc_end = max(contents_pages(pages) or [0])
    starts = locate_chapters(chapter_votes(pages, toc_end, len(chapters)), len(chapters))
    for ch in chapters:
        ch.first_page = starts.get(ch.number)
    placed = [c for c in chapters if c.in_file]
    if len(placed) < 2:
        return None
    last_text_page = max(p for p, t in pages.items() if t.strip())
    for this, nxt in zip(placed, placed[1:] + [None]):
        this.last_page = (nxt.first_page - 1) if nxt else last_text_page

    work = [(ch, w) for ch in placed for w in windows(pages, ch.first_page, ch.last_page)]
    say(f"Reading {len(work)} stretches of {len(placed)} chapters")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda cw: (cw[0], extract_points(cw[0], cw[1], writer=writer)), work))
    for ch, points in results:
        ch.points.extend(points)
    for ch in placed:
        ch.points.sort(key=lambda pt: pt["page"])

    say(f"Writing {len(placed)} chapter summaries")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        bodies = list(pool.map(lambda ch: write_chapter(ch, request, writer=writer),
                               [c for c in placed if c.points]))
    for ch, body in zip([c for c in placed if c.points], bodies):
        ch.body = body

    say("Checking every chapter against what the book says")
    source_text = "\n".join(pages.values())
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(lambda ch: check_chapter(ch, source_text, writer=writer),
                      [c for c in placed if c.body]))

    say("Writing the overview")
    written = [c for c in placed if c.body]
    overview = write_overview(title or document, written, request, writer=writer)

    missing = [c for c in chapters if not c.in_file]
    coverage = (f"This summary covers chapters {written[0].number} to {written[-1].number} of "
                f"{len(chapters)}, from pages {written[0].first_page} to {written[-1].last_page} of the file."
                if written else "")
    if missing:
        names = "; ".join(f"chapter {c.number}, {c.title}" for c in missing)
        verb = "is" if len(missing) == 1 else "are"
        coverage += (f" The file ends before the rest of the book: {names} {verb} listed in its "
                     "contents but not contained in the file, and so not summarised here.")

    return {
        "title": title or document,
        "overview": overview,
        "coverage": coverage,
        "chapters": [
            {"number": c.number, "title": c.title, "pages": [c.first_page, c.last_page],
             "body": c.body, "points": len(c.points), "removed": c.removed}
            for c in written
        ],
        "missing_chapters": [{"number": c.number, "title": c.title} for c in missing],
    }
