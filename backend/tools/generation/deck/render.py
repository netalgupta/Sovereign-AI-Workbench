"""DeckSpec -> .pptx. Layouts, pagination, and the deck's fixed frame.

DECK SPEC (all content; validated upstream in slide_agent):

    {
      "title": str, "subtitle": str, "date": str,
      "sources": [{"id": "S1", "document": str, "pages": [int], "used_for": str}],
      "sections": [{"title": str, "summary": str, "slides": [SLIDE, ...]}],
    }

    SLIDE: {"type": ..., "title": <action title: the takeaway, as a sentence>,
            "sources": ["S1", ...], "notes": str, ...type fields}

      points      bullets: [str], callout: {value, label}?
      big_stat    value, unit?, label, context, status?, compare: {value, label}?
      kpis        items: [{value, unit?, label, note?, status?}]
      chart       chart_type: column|bar|line, categories: [str],
                  series: [{name, values: [number]}], unit?, highlight?: str,
                  takeaways: [str]
      table       columns: [str], rows: [[str]], caption?
      process     steps: [{title, detail?}]
      timeline    events: [{date, title, detail?}]
      alert       severity, headline, what, impact, action
      quote       text (the source's own sentence), attribution
      matrix      axes: {x, y}?, cells: [{title, items: [str], status?}] (4)
      comparison  columns: [{title, points: [str], status?}]
      actions     items: [{action, owner?, due?, priority?}]
      exhibit     image_path (a REAL file from the corpus), caption?,
                  observations: [str]?

The cover, agenda, section dividers and sources appendix are generated
here from the spec, not written by the model.

PAGINATION IS WHY THERE IS NO SLIDE LIMIT. A slide type that holds a list
splits across as many continuation slides as its content needs, each
carrying the same action title marked "(continued)", rather than
shrinking text past legibility or dropping items.
"""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

from . import fit, primitives as P, theme
from .theme import PALETTE as C
from .theme import rgb

# Items per slide before a list continues on the next slide.
MAX_BULLETS = 5
MAX_KPIS = 4
MAX_TABLE_ROWS = 8
MAX_STEPS = 5
MAX_EVENTS = 5
MAX_ACTIONS = 6
MAX_COMPARE = 3
MAX_AGENDA = 7


# ── frame ───────────────────────────────────────────────────────────────────


class _Ctx:
    def __init__(self, spec: dict):
        self.spec = spec
        self.page = 0
        # Generated artwork is OPT-IN per spec: the deck pipeline sets it,
        # tests and quick renders do not, so they never load an image model.
        self.artwork = bool(spec.get("artwork"))
        # page_map[i] = (section index, slide index) of the spec slide that
        # produced rendered page i+1, or None for cover/agenda/dividers/
        # appendix. Quality review uses it to fix the slide a bad page came
        # from, including every continuation page of it.
        self.page_map: list = []
        self.current = None
        self.source_names = {s["id"]: s for s in spec.get("sources", [])}

    def source_line(self, ids: list[str] | None) -> str:
        parts = []
        for sid in ids or []:
            src = self.source_names.get(sid)
            if not src:
                continue
            pages = src.get("pages") or []
            label = Path(src["document"]).stem.replace("_", " ")
            parts.append(label + (f", p.{', '.join(str(p) for p in pages)}" if pages else ""))
        return "Source: " + "; ".join(parts) if parts else ""


def _artwork(ctx: _Ctx, key: str, width_in: float, height_in: float, **kw):
    """Styled local-model artwork for a slide region, or None (vector fallback)."""
    if not ctx.artwork:
        return None
    try:
        from . import art

        return art.styled(key, width_in, height_in, **kw)
    except Exception:  # noqa: BLE001 - artwork never blocks a deck
        return None


def _new_slide(prs, ctx: _Ctx, dark: bool = False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx.page += 1
    ctx.page_map.append(None)
    P.background(slide, C.navy if dark else C.white)
    return slide


def _footer(slide, ctx: _Ctx, sources: list[str] | None, dark: bool = False):
    fg = "8FA3B8" if dark else C.muted
    y = theme.FOOTER_Y
    P.hline(slide, theme.MARGIN_X, y - 0.14, theme.PAGE_W - theme.MARGIN_X, "22415F" if dark else C.rule, 0.5)
    P.text(slide, theme.MARGIN_X, y, 2.2, 0.25, f"{theme.ORG}  ·  INTERNAL", size=theme.SIZE_FOOTER,
           colour=fg, weight="semibold", tracking=1.0)
    line = ctx.source_line(sources)
    if line:
        P.text(slide, theme.MARGIN_X + 2.2, y, 8.6, 0.25, line, size=theme.SIZE_FOOTER, colour=fg)
    P.text(slide, theme.PAGE_W - theme.MARGIN_X - 0.8, y, 0.8, 0.25, f"{ctx.page:02d}",
           size=theme.SIZE_FOOTER, colour=fg, weight="semibold", align="right")


def _header(slide, eyebrow: str, title: str, *, width: float = theme.CONTENT_W):
    x = theme.MARGIN_X
    P.rect(slide, x, theme.EYEBROW_Y + 0.05, 0.28, 0.06, C.amber)
    P.text(slide, x + 0.4, theme.EYEBROW_Y - 0.03, width - 0.4, 0.25, eyebrow or "", size=theme.SIZE_EYEBROW,
           colour=C.teal, weight="semibold", caps=True, tracking=1.5)
    size = fit.fit_size(title, width, theme.TITLE_H, theme.SIZE_TITLE, theme.SIZE_TITLE_MIN,
                        "semibold", 1.08, max_lines=2) or theme.SIZE_TITLE_MIN
    P.text(slide, x, theme.TITLE_Y, width, theme.TITLE_H, title, size=size, colour=C.navy,
           weight="semibold", line_spacing=1.08)


def _notes(slide, text: str | None, source_line: str):
    body = "\n\n".join(t for t in (text, source_line) if t)
    if body:
        slide.notes_slide.notes_text_frame.text = body


def _content_slide(prs, ctx, section_title: str, slide_spec: dict, title_suffix: str = ""):
    s = _new_slide(prs, ctx)
    ctx.page_map[-1] = ctx.current
    title = (slide_spec.get("title") or "").strip() + title_suffix
    _header(s, section_title, title)
    _footer(s, ctx, slide_spec.get("sources"))
    _notes(s, slide_spec.get("notes"), ctx.source_line(slide_spec.get("sources")))
    return s


def _centre_y(block_h: float) -> float:
    """Top edge that centres a block of this height in the body area.

    Layouts whose height depends on how many items they hold (cards,
    rows, steps) looked top-heavy with a band of empty slide beneath
    them. Centring costs nothing and makes a 2-row and a 6-row slide
    look equally deliberate.
    """
    return theme.BODY_Y + max(0.0, (theme.BODY_H - block_h) / 2)


def _limit(sd: dict, default: int) -> int:
    """Items per page for this slide: the layout default, or fewer when
    quality review asked for it (sd["max_items"])."""
    try:
        return max(1, min(default, int(sd.get("max_items") or default)))
    except (TypeError, ValueError):
        return default


def _chunks(items: list, size: int) -> list[list]:
    """Split into pages of NEARLY EQUAL size, not greedy full pages.

    Greedy splitting put five cards on one slide and one on the next,
    where the lone card stretched the full width of the slide and looked
    like a mistake. Five split 3+2 reads as two deliberate slides.
    """
    n = len(items)
    if n == 0:
        return [[]]
    pages = math.ceil(n / size)
    per = math.ceil(n / pages)
    return [items[i:i + per] for i in range(0, n, per)]


def _cont(i: int, n: int) -> str:
    return "" if n == 1 or i == 0 else "  (continued)"


# ── fixed slides ─────────────────────────────────────────────────────────────


def _cover(prs, ctx):
    spec = ctx.spec
    s = _new_slide(prs, ctx, dark=True)
    # Right-hand structure: a slab of navy_2 and fine teal rules, echoing a
    # process flow diagram without pretending to be one.
    art_w = theme.PAGE_W - 8.9
    art_path = _artwork(ctx, f"cover|{spec.get('title', '')}", art_w, theme.PAGE_H)
    if art_path:
        # Local-model artwork, abstract only, pulled into the palette.
        s.shapes.add_picture(str(art_path), Inches(8.9), 0, Inches(art_w), Inches(theme.PAGE_H))
        P.rect(s, 8.9, 0, 0.06, theme.PAGE_H, C.amber)
    else:
        P.rect(s, 8.9, 0, art_w, theme.PAGE_H, C.navy_2)
        for i in range(7):
            y = 1.05 + i * 0.8
            P.hline(s, 9.35, y, theme.PAGE_W - 0.6, C.teal, 0.75 if i % 3 else 2.25)
        P.oval(s, 11.35, 2.55, 1.45, C.navy_2, line=C.amber, line_pt=2.5)
        P.oval(s, 11.83, 3.03, 0.49, C.amber)

    x = theme.MARGIN_X
    P.rect(s, x, 1.25, 0.08, 3.9, C.amber)
    P.text(s, x + 0.35, 1.2, 7.6, 0.3, "Mangalore Refinery and Petrochemicals Limited", size=12,
           colour="8FB8C9", weight="semibold", caps=True, tracking=1.6)
    title = spec.get("title") or "Briefing"
    size = fit.fit_size(title, 7.6, 2.3, theme.SIZE_COVER_TITLE, 28, "semibold", 1.05, max_lines=3) or 28
    P.text(s, x + 0.35, 1.72, 7.6, 2.4, title, size=size, colour=C.white, weight="semibold", line_spacing=1.05)
    if spec.get("subtitle"):
        P.text(s, x + 0.35, 4.2, 7.4, 0.95, spec["subtitle"], size=16, colour="C6D3DF", line_spacing=1.2)

    n_docs = len(spec.get("sources", []))
    date = spec.get("date") or _dt.date.today().strftime("%d %B %Y")
    meta = [("Date", date), ("Grounded in", f"{n_docs} source document{'s' if n_docs != 1 else ''}"),
            ("Prepared", "Sovereign Workbench · offline")]
    for i, (k, v) in enumerate(meta):
        mx = x + 0.35 + i * 2.6
        P.text(s, mx, 5.75, 2.4, 0.25, k, size=10, colour="8FA3B8", weight="semibold", caps=True, tracking=1.2)
        P.text(s, mx, 6.02, 2.5, 0.35, v, size=13, colour=C.white)


def _agenda(prs, ctx, sections: list[dict]):
    pages = _chunks(sections, MAX_AGENDA)
    for pi, page in enumerate(pages):
        s = _new_slide(prs, ctx)
        _header(s, "Contents", "What this briefing covers" + _cont(pi, len(pages)))
        _footer(s, ctx, None)
        row_h = min(0.82, theme.BODY_H / max(len(page), 1))
        top = _centre_y(row_h * len(page))
        for i, sec in enumerate(page):
            n = pi * MAX_AGENDA + i + 1
            y = top + i * row_h
            P.text(s, theme.MARGIN_X, y, 0.9, row_h, f"{n:02d}", size=26, colour=C.teal, weight="light",
                   anchor="middle")
            P.text(s, theme.MARGIN_X + 1.0, y, 7.2, row_h, sec.get("title", ""), size=19, colour=C.navy,
                   weight="semibold", anchor="middle")
            if sec.get("summary"):
                P.text(s, theme.MARGIN_X + 8.3, y, theme.CONTENT_W - 8.3, row_h, sec["summary"], size=12,
                       colour=C.ink_2, anchor="middle")
            if i < len(page) - 1:
                P.hline(s, theme.MARGIN_X, y + row_h, theme.PAGE_W - theme.MARGIN_X, C.rule, 0.5)


def _divider(prs, ctx, number: int, section: dict):
    s = _new_slide(prs, ctx, dark=True)
    art_path = _artwork(ctx, f"divider|{number}|{section.get('title', '')}", 4.6, theme.PAGE_H, tint=0.5)
    if art_path:
        s.shapes.add_picture(str(art_path), 0, 0, Inches(4.6), Inches(theme.PAGE_H))
    else:
        P.rect(s, 0, 0, 4.6, theme.PAGE_H, C.navy_2)
    title = section.get("title", "")
    size = fit.fit_size(title, 7.2, 1.8, 40, 26, "semibold", 1.05, max_lines=2) or 26
    title_h = fit.text_height_in(title, 7.2, size, "semibold", 1.05)
    summary = section.get("summary") or ""
    sum_h = fit.text_height_in(summary, 7.0, 15, "regular", 1.25) if summary else 0
    block_h = 0.07 + 0.32 + title_h + (0.45 + sum_h if summary else 0)
    top = (theme.PAGE_H - block_h) / 2
    P.text(s, 0.72, top, 3.6, block_h, f"{number:02d}", size=110, colour=C.amber, weight="light",
           anchor="middle")
    P.rect(s, 5.3, top, 0.6, 0.07, C.teal)
    P.text(s, 5.3, top + 0.32, 7.3, title_h + 0.1, title, size=size, colour=C.white, weight="semibold",
           line_spacing=1.05)
    if summary:
        P.text(s, 5.3, top + 0.32 + title_h + 0.45, 7.0, sum_h + 0.1, summary, size=15, colour="C6D3DF",
               line_spacing=1.25)
    _footer(s, ctx, None, dark=True)


def _sources_appendix(prs, ctx):
    sources = ctx.spec.get("sources") or []
    if not sources:
        return
    pages = _chunks(sources, 6)
    for pi, page in enumerate(pages):
        s = _new_slide(prs, ctx)
        _header(s, "Appendix", "Every figure in this deck traces to these documents" + _cont(pi, len(pages)))
        _footer(s, ctx, None)
        row_h = min(0.72, theme.BODY_H / max(len(page), 1))
        top = _centre_y(row_h * len(page))
        for i, src in enumerate(page):
            y = top + i * row_h
            P.rect(s, theme.MARGIN_X, y + 0.14, 0.62, 0.36, C.teal_light, radius=0.3)
            P.text(s, theme.MARGIN_X, y + 0.14, 0.62, 0.36, src["id"], size=11, colour=C.teal, weight="semibold",
                   align="center", anchor="middle")
            pages_txt = (", p." + ", ".join(str(p) for p in src.get("pages") or [])) if src.get("pages") else ""
            P.text(s, theme.MARGIN_X + 0.85, y + 0.08, 6.3, 0.5, src["document"] + pages_txt, size=13,
                   colour=C.navy, weight="semibold", anchor="middle")
            if src.get("used_for"):
                P.text(s, theme.MARGIN_X + 7.3, y + 0.08, theme.CONTENT_W - 7.3, 0.5, src["used_for"], size=11,
                       colour=C.ink_2, anchor="middle")
            P.hline(s, theme.MARGIN_X, y + row_h, theme.PAGE_W - theme.MARGIN_X, C.rule, 0.5)


# ── content layouts ─────────────────────────────────────────────────────────


def _points(prs, ctx, sec_title, sd):
    bullets = [b if isinstance(b, str) else b.get("text", "") for b in sd.get("bullets", [])]
    bullets = [b for b in bullets if b.strip()]
    callout = sd.get("callout") if isinstance(sd.get("callout"), dict) and sd["callout"].get("value") else None
    pages = _chunks(bullets, _limit(sd, MAX_BULLETS))
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        with_callout = bool(callout and pi == 0)
        # FEW, SHORT POINTS BECOME CARDS. Two one-line bullets at the top of
        # an otherwise empty slide looked unfinished -- MEASURED on a real
        # incident deck. Up to three short statements read better as a row
        # of numbered cards that use the page.
        if not with_callout and 1 <= len(page) <= 3 and all(len(b) <= 130 for b in page):
            _statement_cards(s, page, pi * _limit(sd, MAX_BULLETS))
            continue
        text_w = theme.CONTENT_W - (3.9 if with_callout else 0) - 0.75
        # Larger type when there is room: fit from 26pt down, so a short
        # list fills the slide instead of hugging its top edge.
        size = fit.fit_many(page, text_w, theme.BODY_H - 0.3, 26, theme.SIZE_BODY_MIN, 0.28)             or theme.SIZE_BODY_MIN
        gap = 0.28 if size >= 20 else 0.22
        block_h = sum(fit.text_height_in(b, text_w, size) for b in page) + gap * (len(page) - 1)
        y = _centre_y(block_h)
        marker = 0.36 if size < 20 else 0.44
        for i, b in enumerate(page):
            h = fit.text_height_in(b, text_w, size)
            n = pi * MAX_BULLETS + i + 1
            line_h = size * fit.LINE_EM * 1.18 / 72.0
            my = y + max(0.0, (line_h - marker) / 2)
            P.oval(s, theme.MARGIN_X, my, marker, C.teal_light)
            P.text(s, theme.MARGIN_X, my, marker, marker, str(n), size=11 if marker < 0.4 else 13,
                   colour=C.teal, weight="semibold", align="center", anchor="middle")
            P.text(s, theme.MARGIN_X + 0.75, y, text_w, h + 0.05, b, size=size, colour=C.ink)
            y += h + gap
        if with_callout:
            _callout_panel(s, theme.PAGE_W - theme.MARGIN_X - 3.5, theme.BODY_Y, 3.5, theme.BODY_H - 0.3, callout)


def _statement_cards(s, page: list[str], offset: int):
    n = len(page)
    gap = 0.35
    w = (theme.CONTENT_W - gap * (n - 1)) / n
    h = 3.4
    y = _centre_y(h)
    size = min(
        (fit.fit_size(b, w - 0.8, h - 1.55, 22, 13, "regular", 1.22) or 13) for b in page
    )
    for i, b in enumerate(page):
        x = theme.MARGIN_X + i * (w + gap)
        P.rect(s, x, y, w, h, C.panel, radius=0.04)
        P.rect(s, x, y, 0.08, h, C.teal)
        P.text(s, x + 0.4, y + 0.35, 1.5, 0.7, f"{offset + i + 1:02d}", size=34, colour=C.teal, weight="light")
        P.hline(s, x + 0.4, y + 1.15, x + 1.1, C.amber, 2.25)
        P.text(s, x + 0.4, y + 1.4, w - 0.8, h - 1.6, b, size=size, colour=C.ink, line_spacing=1.22)


def _callout_panel(s, x, y, w, h, callout: dict):
    P.rect(s, x, y, w, h, C.navy, radius=0.04)
    P.rect(s, x, y, 0.07, h, C.amber)
    value = str(callout.get("value", ""))
    unit = callout.get("unit") or ""
    size = fit.fit_size(value + unit, w - 0.6, 1.2, 48, 26, "semibold", 1.0, max_lines=1) or 26
    P.text(s, x + 0.35, y + 0.5, w - 0.6, 1.2,
           [(value, {"size": size}), (f" {unit}" if unit else "", {"size": size * 0.5, "colour": "C6D3DF"})],
           size=size, colour=C.white, weight="semibold", anchor="bottom")
    P.text(s, x + 0.35, y + 1.85, w - 0.6, h - 2.1, callout.get("label", ""), size=14, colour="C6D3DF",
           line_spacing=1.25)


def _big_stat(prs, ctx, sec_title, sd):
    s = _content_slide(prs, ctx, sec_title, sd)
    status = theme.status_colours(sd.get("status"))
    accent = status[0] if status else C.teal
    value, unit = str(sd.get("value", "")), sd.get("unit") or ""
    left_w = 5.6
    size = fit.fit_size(value, left_w - 0.2, 2.0, 110, 54, "semibold", 1.0, max_lines=1) or 54
    P.text(s, theme.MARGIN_X, theme.BODY_Y + 0.2, left_w, 2.1,
           [(value, {"size": size, "colour": accent}), (f" {unit}" if unit else "", {"size": size * 0.34, "colour": C.ink_2})],
           size=size, weight="semibold", anchor="bottom", line_spacing=1.0)
    P.rect(s, theme.MARGIN_X, theme.BODY_Y + 2.5, 0.9, 0.07, accent)
    P.text(s, theme.MARGIN_X, theme.BODY_Y + 2.72, left_w, 1.0, sd.get("label", ""), size=18, colour=C.navy,
           weight="semibold", line_spacing=1.15)
    if status:
        P.pill(s, theme.MARGIN_X, theme.BODY_Y + 3.65, theme.status_label(sd["status"]), status[0], status[1])

    px = theme.MARGIN_X + left_w + 0.6
    pw = theme.PAGE_W - theme.MARGIN_X - px
    P.rect(s, px, theme.BODY_Y, pw, theme.BODY_H - 0.25, C.panel, radius=0.03)
    context = sd.get("context", "")
    csize = fit.fit_size(context, pw - 0.8, 2.6, 18, 13, "regular", 1.3) or 13
    P.text(s, px + 0.4, theme.BODY_Y + 0.4, pw - 0.8, 2.7, context, size=csize, colour=C.ink, line_spacing=1.3)
    cmp_ = sd.get("compare")
    if isinstance(cmp_, dict) and cmp_.get("value"):
        P.hline(s, px + 0.4, theme.BODY_Y + 3.15, px + pw - 0.4, C.rule)
        P.text(s, px + 0.4, theme.BODY_Y + 3.35, 2.4, 0.7, str(cmp_["value"]), size=30, colour=C.navy,
               weight="semibold", anchor="middle")
        P.text(s, px + 2.8, theme.BODY_Y + 3.35, pw - 3.2, 0.7, cmp_.get("label", ""), size=13, colour=C.ink_2,
               anchor="middle")


def _kpis(prs, ctx, sec_title, sd):
    items = [i for i in sd.get("items", []) if isinstance(i, dict) and str(i.get("value", "")).strip()]
    pages = _chunks(items, _limit(sd, MAX_KPIS))
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        n = max(len(page), 1)
        gap = 0.3
        # Capped at the width a full page of four would give, so a page
        # of two is two cards, not two banners.
        w = min((theme.CONTENT_W - gap * (n - 1)) / n, (theme.CONTENT_W - gap * 3) / 4 + 0.35)
        h = 3.6
        y = _centre_y(h)
        row_w = w * n + gap * (n - 1)
        x0 = theme.MARGIN_X + (theme.CONTENT_W - row_w) / 2
        for i, it in enumerate(page):
            x = x0 + i * (w + gap)
            status = theme.status_colours(it.get("status"))
            accent = status[0] if status else C.teal
            P.rect(s, x, y, w, h, C.panel, radius=0.04)
            P.rect(s, x, y, w, 0.08, accent)
            value, unit = str(it.get("value", "")), it.get("unit") or ""
            vsize = fit.fit_size(value + " " + unit, w - 0.6, 1.1, 44, 24, "semibold", 1.0, max_lines=1) or 24
            P.text(s, x + 0.3, y + 0.45, w - 0.6, 1.1,
                   [(value, {"size": vsize}), (f" {unit}" if unit else "", {"size": vsize * 0.45, "colour": C.ink_2})],
                   size=vsize, colour=C.navy, weight="semibold", anchor="bottom", line_spacing=1.0)
            P.text(s, x + 0.3, y + 1.72, w - 0.6, 0.8, it.get("label", ""), size=12, colour=C.ink_2,
                   weight="semibold", caps=True, tracking=0.8, line_spacing=1.15)
            if it.get("note"):
                P.text(s, x + 0.3, y + 2.45, w - 0.6, 0.85, it["note"], size=12, colour=C.ink_2, line_spacing=1.2)
            if status:
                P.pill(s, x + 0.3, y + h - 0.5, theme.status_label(it["status"]), status[0], status[1],
                       size=9, h=0.26)


def _chart(prs, ctx, sec_title, sd):
    s = _content_slide(prs, ctx, sec_title, sd)
    cats = [str(c) for c in sd.get("categories", [])]
    series = [x for x in sd.get("series", []) if isinstance(x, dict) and x.get("values")]
    kind = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
            "line": XL_CHART_TYPE.LINE_MARKERS}.get(sd.get("chart_type"), XL_CHART_TYPE.COLUMN_CLUSTERED)
    data = CategoryChartData()
    data.categories = cats
    for ser in series:
        data.add_series(ser.get("name") or "", [float(v) for v in ser["values"]][: len(cats)])
    takeaways = [t for t in sd.get("takeaways", []) if t]
    chart_w = theme.CONTENT_W - (4.1 if takeaways else 0)
    gf = s.shapes.add_chart(kind, Inches(theme.MARGIN_X), Inches(theme.BODY_Y), Inches(chart_w),
                            Inches(theme.BODY_H - 0.2), data)
    chart = gf.chart
    chart.has_title = False  # the slide's action title is the title
    chart.font.name = theme.FONT
    chart.font.size = Pt(12)
    chart.font.color.rgb = rgb(C.ink_2)
    chart.has_legend = len(series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
    palette = [C.teal, C.navy, C.amber, C.muted]
    plot = chart.plots[0]
    if kind != XL_CHART_TYPE.LINE_MARKERS:
        plot.gap_width = 55
        plot.overlap = -10
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.font.size = Pt(12)
    dl.font.bold = True
    dl.font.color.rgb = rgb(C.navy)
    dl.number_format = sd.get("number_format") or "General"
    dl.number_format_is_linked = False
    if kind != XL_CHART_TYPE.LINE_MARKERS:
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
    highlight = str(sd.get("highlight")) if sd.get("highlight") is not None else None
    for si, ser in enumerate(chart.series):
        colour = palette[si % len(palette)]
        if kind == XL_CHART_TYPE.LINE_MARKERS:
            ser.format.line.color.rgb = rgb(colour)
            ser.format.line.width = Pt(2.75)
            ser.smooth = False
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = rgb(colour)
            ser.marker.format.line.color.rgb = rgb(C.white)
            ser.marker.size = 8
        else:
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = rgb(colour)
        if highlight and highlight in cats and len(series) == 1:
            pt = ser.points[cats.index(highlight)]
            if kind == XL_CHART_TYPE.LINE_MARKERS:
                pt.marker.format.fill.solid()
                pt.marker.format.fill.fore_color.rgb = rgb(C.amber)
                pt.marker.size = 12
            else:
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(C.amber)
    va = chart.value_axis
    # BARS START AT ZERO. PowerPoint auto-scaled a two-bar chart of 31 and 34
    # hours to begin at 29.5, so a 10% rise was drawn as a tripling. A bar's
    # length IS its value; truncating the axis misreports it. Line charts
    # may zoom, because a line encodes change, not magnitude.
    if kind != XL_CHART_TYPE.LINE_MARKERS:
        va.minimum_scale = 0
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb(C.rule)
    va.major_gridlines.format.line.width = Pt(0.5)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(11)
    va.tick_labels.font.color.rgb = rgb(C.muted)
    if sd.get("unit"):
        va.has_title = True
        va.axis_title.text_frame.text = sd["unit"]
        tr = va.axis_title.text_frame.paragraphs[0].runs[0]
        tr.font.size = Pt(11)
        tr.font.color.rgb = rgb(C.muted)
        tr.font.bold = False
    ca = chart.category_axis
    ca.format.line.color.rgb = rgb(C.rule)
    ca.tick_labels.font.size = Pt(12)
    ca.tick_labels.font.color.rgb = rgb(C.ink_2)

    if takeaways:
        px = theme.PAGE_W - theme.MARGIN_X - 3.7
        P.rect(s, px, theme.BODY_Y, 3.7, theme.BODY_H - 0.25, C.panel, radius=0.03)
        P.text(s, px + 0.35, theme.BODY_Y + 0.3, 3.0, 0.3, "What it shows", size=11, colour=C.teal,
               weight="semibold", caps=True, tracking=1.2)
        size = fit.fit_many(takeaways[:4], 2.75, theme.BODY_H - 1.2, 16, 12, 0.2) or 12
        y = theme.BODY_Y + 0.8
        for t in takeaways[:4]:
            h = fit.text_height_in(t, 2.75, size)
            P.rect(s, px + 0.35, y + 0.09, 0.1, 0.1, C.amber)
            P.text(s, px + 0.6, y, 2.75, h + 0.05, t, size=size, colour=C.ink)
            y += h + 0.2


def _table(prs, ctx, sec_title, sd):
    columns = [str(c) for c in sd.get("columns", [])]
    rows = [[str(c) for c in r] for r in sd.get("rows", []) if isinstance(r, (list, tuple))]
    if not columns or not rows:
        return
    pages = _chunks(rows, _limit(sd, MAX_TABLE_ROWS))
    ncol = len(columns)
    # Column widths proportional to content, but never narrower than the
    # column's longest WORD: "Exceeded" in a status column was wrapping
    # mid-word as "Exceede / d".
    cells_by_col = [[columns[c]] + [r[c] if c < len(r) else "" for r in rows] for c in range(ncol)]
    weights = [max(6, min(max(len(v) for v in col), 48)) for col in cells_by_col]
    total = sum(weights)
    widths = [theme.CONTENT_W * w / total for w in weights]
    pad = 0.30  # cell margins, both sides
    for c, col in enumerate(cells_by_col):
        longest_word = max((w for v in col for w in v.split()), key=len, default="")
        needed = fit.text_width_pt(longest_word, 14, "semibold") / 72.0 + pad
        widths[c] = max(widths[c], min(needed, theme.CONTENT_W / 2))
    scale = theme.CONTENT_W / sum(widths)
    widths = [w * scale for w in widths]
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        caption_h = 0.35 if sd.get("caption") else 0
        avail = theme.BODY_H - caption_h - 0.15
        row_h = min(0.56, avail / (len(page) + 1))
        size = 14 if row_h >= 0.5 else 12
        table_top = _centre_y(row_h * (len(page) + 1) + caption_h)
        gf = s.shapes.add_table(len(page) + 1, ncol, Inches(theme.MARGIN_X), Inches(table_top),
                                Inches(theme.CONTENT_W), Inches(row_h * (len(page) + 1)))
        tbl = gf.table
        tbl.first_row = True
        tbl.horz_banding = False
        for c, w in enumerate(widths):
            tbl.columns[c].width = Inches(w)
        for r in range(len(page) + 1):
            tbl.rows[r].height = Inches(row_h)
            for c in range(ncol):
                cell = tbl.cell(r, c)
                value = columns[c] if r == 0 else (page[r - 1][c] if c < len(page[r - 1]) else "")
                cell.margin_left = cell.margin_right = Inches(0.14)
                cell.margin_top = cell.margin_bottom = Inches(0.04)
                cell.vertical_anchor = P.ANCHOR["middle"]
                cell.fill.solid()
                if r == 0:
                    cell.fill.fore_color.rgb = rgb(C.navy)
                else:
                    cell.fill.fore_color.rgb = rgb(C.panel if r % 2 == 0 else C.white)
                tf = cell.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.text = ""
                run = p.add_run()
                run.text = value
                run.font.name = theme.FONT_SEMIBOLD if (r == 0 or c == 0) else theme.FONT
                run.font.size = Pt(11 if r == 0 else size)
                status = theme.status_colours(value) if r > 0 else None
                if r == 0:
                    run.font.color.rgb = rgb(C.white)
                elif status:
                    run.font.color.rgb = rgb(status[0])
                    run.font.name = theme.FONT_SEMIBOLD
                else:
                    run.font.color.rgb = rgb(C.ink)
        if sd.get("caption"):
            P.text(s, theme.MARGIN_X, table_top + row_h * (len(page) + 1) + 0.18, theme.CONTENT_W, 0.3,
                   sd["caption"], size=11, colour=C.muted)


def _process(prs, ctx, sec_title, sd):
    steps = [st if isinstance(st, dict) else {"title": str(st)} for st in sd.get("steps", [])]
    steps = [st for st in steps if st.get("title")]
    pages = _chunks(steps, _limit(sd, MAX_STEPS))
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        n = max(len(page), 1)
        gap = 0.28
        # Capped and centred: two steps spread across the full slide read
        # as a mistake rather than a sequence.
        w = min((theme.CONTENT_W - gap * (n - 1)) / n, (theme.CONTENT_W - gap * 2) / 3)
        row_w = w * n + gap * (n - 1)
        x0 = theme.MARGIN_X + (theme.CONTENT_W - row_w) / 2
        has_detail = any(st.get("detail") for st in page)
        y = _centre_y(3.2 if has_detail else 1.9)
        P.hline(s, x0 + w / 2, y + 0.33, x0 + (n - 1) * (w + gap) + w / 2, C.rule, 2)
        for i, st in enumerate(page):
            x = x0 + i * (w + gap)
            num = pi * MAX_STEPS + i + 1
            P.oval(s, x + w / 2 - 0.33, y, 0.66, C.navy)
            P.text(s, x + w / 2 - 0.33, y, 0.66, 0.66, str(num), size=18, colour=C.white, weight="semibold",
                   align="center", anchor="middle")
            tsize = fit.fit_size(st["title"], w - 0.1, 0.95, 16, 12, "semibold", 1.12) or 12
            P.text(s, x, y + 0.95, w, 1.0, st["title"], size=tsize, colour=C.navy, weight="semibold",
                   align="center", line_spacing=1.12)
            if st.get("detail"):
                dsize = fit.fit_size(st["detail"], w - 0.1, 2.2, 13, 10, "regular", 1.22) or 10
                P.text(s, x, y + 2.0, w, 2.3, st["detail"], size=dsize, colour=C.ink_2, align="center",
                       line_spacing=1.22)


def _timeline(prs, ctx, sec_title, sd):
    events = [e for e in sd.get("events", []) if isinstance(e, dict) and e.get("title")]
    pages = _chunks(events, _limit(sd, MAX_EVENTS))
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        n = max(len(page), 1)
        axis_y = theme.BODY_Y + 2.05
        # Capped and centred, like the step row: two events spread across
        # the full slide read as a mistake rather than a sequence.
        w = min(theme.CONTENT_W / n, theme.CONTENT_W / 3)
        row_w = w * n
        x0 = theme.MARGIN_X + (theme.CONTENT_W - row_w) / 2
        P.hline(s, x0, axis_y, x0 + row_w, C.teal, 2.25)
        for i, e in enumerate(page):
            cx = x0 + w * i + w / 2
            up = i % 2 == 0
            P.oval(s, cx - 0.13, axis_y - 0.13, 0.26, C.white, line=C.teal, line_pt=3)
            P.vline(s, cx, axis_y - (0.45 if up else -0.13), axis_y - (0.13 if up else -0.45), C.rule, 1)
            by = axis_y - 1.95 if up else axis_y + 0.55
            P.text(s, cx - w / 2 + 0.08, by, w - 0.16, 0.32, e.get("date", ""), size=12, colour=C.teal,
                   weight="semibold", align="center", caps=True, tracking=0.6)
            P.text(s, cx - w / 2 + 0.08, by + 0.34, w - 0.16, 0.6, e["title"], size=14, colour=C.navy,
                   weight="semibold", align="center", line_spacing=1.1)
            if e.get("detail"):
                P.text(s, cx - w / 2 + 0.08, by + 0.92, w - 0.16, 0.95, e["detail"], size=11, colour=C.ink_2,
                       align="center", line_spacing=1.18)


ALERT_BODY_TOP = 2.35  # panel top to the first line of column text
ALERT_PAD = 0.35


def _alert(prs, ctx, sec_title, sd):
    s = _content_slide(prs, ctx, sec_title, sd)
    status = theme.status_colours(sd.get("severity")) or (C.red, C.red_light)
    cols_preview = [t for t in (sd.get("what"), sd.get("impact"), sd.get("action")) if t]
    col_w = (theme.CONTENT_W - 0.9 - 0.4 * (max(len(cols_preview), 1) - 1)) / max(len(cols_preview), 1)
    body_h = max((fit.text_height_in(t, col_w, 15, "regular", 1.25) for t in cols_preview), default=0.6)
    # The panel is built from what goes in it, top to bottom: pill 0.35,
    # headline from 0.8, column labels at 1.95, column text from 2.35 for
    # its measured height, then 0.35 of padding.
    h = min(theme.BODY_H - 0.2, ALERT_BODY_TOP + body_h + ALERT_PAD)
    y = _centre_y(h)
    P.rect(s, theme.MARGIN_X, y, theme.CONTENT_W, h, C.panel, radius=0.02)
    P.rect(s, theme.MARGIN_X, y, 0.12, h, status[0])
    x = theme.MARGIN_X + 0.45
    if sd.get("severity"):
        P.pill(s, x, y + 0.35, f"{sd['severity']} severity", status[0], status[1])
    headline = sd.get("headline", "")
    hs = fit.fit_size(headline, theme.CONTENT_W - 0.9, 0.9, 22, 15, "semibold", 1.12, max_lines=2) or 15
    P.text(s, x, y + 0.8, theme.CONTENT_W - 0.9, 0.9, headline, size=hs, colour=C.navy, weight="semibold",
           line_spacing=1.12)
    cols = [("What happened", sd.get("what", "")), ("Impact", sd.get("impact", "")),
            ("Required action", sd.get("action", ""))]
    cols = [c for c in cols if c[1]]
    cw = (theme.CONTENT_W - 0.9 - 0.4 * (len(cols) - 1)) / max(len(cols), 1)
    body_y = y + 1.95
    # ONE size for all three columns, fitted to the space left inside the
    # panel. Sized per column against a fixed height, long text ran out of
    # the panel and over the footer.
    # WAS `y + h - body_y - 0.85`, a margin added before line height was
    # calibrated (LINE_EM): for a SHORT alert that is negative, and a
    # negative text box makes PowerPoint refuse the whole file. Measured
    # on a live deck. The space is now exactly what the panel was sized for.
    avail = h - ALERT_BODY_TOP - ALERT_PAD
    body_size = min(
        (fit.fit_size(body, cw, avail, 15, 9, "regular", 1.25) or 9) for _label, body in cols
    ) if cols else 11
    for i, (label, body) in enumerate(cols):
        cx = x + i * (cw + 0.4)
        P.text(s, cx, body_y, cw, 0.3, label, size=11, colour=status[0] if i == 2 else C.teal,
               weight="semibold", caps=True, tracking=1.1)
        P.text(s, cx, body_y + 0.4, cw, avail, body, size=body_size, colour=C.ink, line_spacing=1.25)


def _comparison(prs, ctx, sec_title, sd):
    cols = [c for c in sd.get("columns", []) if isinstance(c, dict) and c.get("title")]
    pages = _chunks(cols, _limit(sd, MAX_COMPARE))
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        n = max(len(page), 1)
        gap = 0.35
        w = (theme.CONTENT_W - gap * (n - 1)) / n
        for i, col in enumerate(page):
            x = theme.MARGIN_X + i * (w + gap)
            status = theme.status_colours(col.get("status"))
            head = status[0] if status else (C.navy if i % 2 == 0 else C.teal)
            P.rect(s, x, theme.BODY_Y, w, theme.BODY_H - 0.2, C.panel, radius=0.03)
            P.rect(s, x, theme.BODY_Y, w, 0.85, head, radius=0.08)
            P.rect(s, x, theme.BODY_Y + 0.5, w, 0.35, head)
            P.text(s, x + 0.3, theme.BODY_Y, w - 0.6, 0.85, col["title"], size=17, colour=C.white,
                   weight="semibold", anchor="middle")
            pts = [p for p in col.get("points", []) if p][:6]
            size = fit.fit_many(pts, w - 0.85, theme.BODY_H - 1.5, 15, 11, 0.16) or 11
            y = theme.BODY_Y + 1.15
            for p in pts:
                h = fit.text_height_in(p, w - 0.85, size)
                P.rect(s, x + 0.32, y + 0.1, 0.09, 0.09, head)
                P.text(s, x + 0.55, y, w - 0.85, h + 0.05, p, size=size, colour=C.ink)
                y += h + 0.16


def _actions(prs, ctx, sec_title, sd):
    items = [i for i in sd.get("items", []) if isinstance(i, dict) and i.get("action")]
    if not items:
        return
    pages = _chunks(items, _limit(sd, MAX_ACTIONS))
    has_owner = any(i.get("owner") for i in items)
    has_due = any(i.get("due") for i in items)
    for pi, page in enumerate(pages):
        s = _content_slide(prs, ctx, sec_title, sd, _cont(pi, len(pages)))
        owner_w = 2.2 if has_owner else 0
        due_w = 2.4 if has_due else 0
        action_w = theme.CONTENT_W - 0.9 - owner_w - due_w - 0.2
        heads = [("#", 0.9), ("Action", action_w + 0.2)] + ([("Owner", owner_w)] if has_owner else []) \
            + ([("When / trigger", due_w)] if has_due else [])
        top = _centre_y(min(0.78, (theme.BODY_H - 0.5) / max(len(page), 1)) * len(page) + 0.46)
        hx = theme.MARGIN_X
        for label, w in heads:
            P.text(s, hx, top, w, 0.3, label, size=10, colour=C.muted, weight="semibold", caps=True,
                   tracking=1.1)
            hx += w
        P.hline(s, theme.MARGIN_X, top + 0.36, theme.PAGE_W - theme.MARGIN_X, C.navy, 1.25)
        row_h = min(0.78, (theme.BODY_H - 0.5) / len(page))
        top = _centre_y(row_h * len(page) + 0.46) 
        for i, it in enumerate(page):
            y = top + 0.46 + i * row_h
            n = pi * MAX_ACTIONS + i + 1
            status = theme.status_colours(it.get("priority"))
            P.rect(s, theme.MARGIN_X, y + (row_h - 0.42) / 2, 0.42, 0.42, status[0] if status else C.teal, radius=0.2)
            P.text(s, theme.MARGIN_X, y + (row_h - 0.42) / 2, 0.42, 0.42, str(n), size=13, colour=C.white,
                   weight="semibold", align="center", anchor="middle")
            asz = fit.fit_size(it["action"], action_w, row_h - 0.08, 15, 11, "regular", 1.15) or 11
            P.text(s, theme.MARGIN_X + 0.9, y, action_w, row_h, it["action"], size=asz, colour=C.ink,
                   anchor="middle", line_spacing=1.15)
            cx = theme.MARGIN_X + 0.9 + action_w + 0.2
            if has_owner:
                P.text(s, cx, y, owner_w - 0.15, row_h, it.get("owner") or "—", size=12, colour=C.ink_2,
                       weight="semibold", anchor="middle")
                cx += owner_w
            if has_due:
                P.text(s, cx, y, due_w, row_h, it.get("due") or "—", size=12, colour=C.ink_2, anchor="middle")
            P.hline(s, theme.MARGIN_X, y + row_h, theme.PAGE_W - theme.MARGIN_X, C.rule, 0.5)


def _exhibit(prs, ctx, sec_title, sd):
    """A real image from the corpus -- a P&ID, a scanned form, a chart.

    THE IMAGE IS ALWAYS A FILE THAT EXISTS. Nothing here draws or
    generates a picture of plant equipment: a plausible invented diagram
    on an approval-bound deck is a fabricated record. The caption names
    the document it came from.
    """
    image = sd.get("image_path")
    if not image or not Path(image).exists():
        return
    s = _content_slide(prs, ctx, sec_title, sd)
    obs = [o for o in sd.get("observations", []) if o][:4]
    frame_w = theme.CONTENT_W - (3.9 if obs else 0)
    frame_h = theme.BODY_H - (0.4 if sd.get("caption") else 0)
    from PIL import Image as _Image

    try:
        with _Image.open(image) as im:
            ratio = im.height / max(im.width, 1)
    except Exception:  # noqa: BLE001 - an unreadable image is not a crash
        return
    w = min(frame_w, frame_h / ratio) if ratio else frame_w
    h = w * ratio
    x = theme.MARGIN_X + (frame_w - w) / 2
    y = _centre_y(h + (0.4 if sd.get("caption") else 0))
    P.rect(s, x - 0.06, y - 0.06, w + 0.12, h + 0.12, C.panel, line=C.rule)
    s.shapes.add_picture(str(image), Inches(x), Inches(y), Inches(w), Inches(h))
    if sd.get("caption"):
        P.text(s, x, y + h + 0.16, w, 0.3, sd["caption"], size=11, colour=C.muted)
    if obs:
        px = theme.PAGE_W - theme.MARGIN_X - 3.7
        P.rect(s, px, theme.BODY_Y, 3.7, theme.BODY_H - 0.25, C.panel, radius=0.03)
        P.text(s, px + 0.35, theme.BODY_Y + 0.3, 3.0, 0.3, "Read from the drawing", size=11, colour=C.teal,
               weight="semibold", caps=True, tracking=1.2)
        size = fit.fit_many(obs, 2.75, theme.BODY_H - 1.2, 15, 11, 0.2) or 11
        oy = theme.BODY_Y + 0.8
        for o in obs:
            oh = fit.text_height_in(o, 2.75, size)
            P.rect(s, px + 0.35, oy + 0.09, 0.1, 0.1, C.amber)
            P.text(s, px + 0.6, oy, 2.75, oh + 0.05, o, size=size, colour=C.ink)
            oy += oh + 0.2


def _quote(prs, ctx, sec_title, sd):
    """One sentence from the sources, set large, with the document it came from.

    For a directive or finding that carries a section on its own -- an SOP
    instruction, a limit, a conclusion. The text is the source's own words;
    the attribution is the document, so a strong line on a slide can still
    be traced.
    """
    s = _content_slide(prs, ctx, sec_title, sd)
    text = str(sd.get("text", "")).strip()
    attribution = str(sd.get("attribution", "")).strip()
    box_w = theme.CONTENT_W - 1.6
    size = fit.fit_size(text, box_w, theme.BODY_H - 1.6, 34, 18, "light", 1.28, max_lines=6) or 18
    height = fit.text_height_in(text, box_w, size, "light", 1.28)
    top = _centre_y(height + (0.9 if attribution else 0.2))

    P.rect(s, theme.MARGIN_X, top - 0.1, 0.1, height + 0.2, C.amber)
    P.text(s, theme.MARGIN_X + 0.55, top, box_w, height + 0.1, text, size=size, colour=C.navy,
           weight="light", line_spacing=1.28)
    if attribution:
        P.text(s, theme.MARGIN_X + 0.55, top + height + 0.35, box_w, 0.35, attribution,
               size=12, colour=C.teal, weight="semibold", caps=True, tracking=1.2)


def _matrix(prs, ctx, sec_title, sd):
    """A 2x2 of labelled quadrants -- likelihood against consequence, effort
    against impact. Four cells, each with a heading and its items."""
    s = _content_slide(prs, ctx, sec_title, sd)
    cells = [c for c in (sd.get("cells") or []) if isinstance(c, dict)][:4]
    while len(cells) < 4:
        cells.append({})
    gap = 0.3
    cw = (theme.CONTENT_W - gap) / 2
    ch = (theme.BODY_H - 0.9 - gap) / 2
    top = theme.BODY_Y + 0.55
    axes = sd.get("axes") or {}
    if axes.get("x"):
        P.text(s, theme.MARGIN_X, theme.BODY_Y, theme.CONTENT_W, 0.3, str(axes["x"]), size=11,
               colour=C.ink_2, caps=True, tracking=1.2)
    for i, cell in enumerate(cells):
        x = theme.MARGIN_X + (i % 2) * (cw + gap)
        y = top + (i // 2) * (ch + gap)
        status = theme.status_colours(cell.get("status"))
        accent = status[0] if status else (C.teal if i % 3 == 0 else C.navy)
        P.rect(s, x, y, cw, ch, C.panel, radius=0.02)
        P.rect(s, x, y, cw, 0.07, accent)
        P.text(s, x + 0.35, y + 0.35, cw - 0.7, 0.4, str(cell.get("title", "")), size=14,
               colour=C.navy, weight="semibold")
        items = [str(t) for t in (cell.get("items") or []) if str(t).strip()][:4]
        if items:
            # Fitted to the box that is actually drawn, with the gap the
            # paragraphs are actually given (6 pt): fitting to a taller box
            # or a wider gap puts the last line past the panel edge, which
            # PowerPoint reports as overflow.
            box_h = ch - 1.25
            # 11 pt floor, not 10: qa.py measures anything under 10.5 pt as
            # too small to read, so a cell that shrank to fit was a defect.
            size = fit.fit_many(items, cw - 0.7, box_h, 13, 11, 6 / 72) or 11
            P.paragraphs(s, x + 0.35, y + 0.95, cw - 0.7, box_h, items, size=size,
                         colour=C.ink, gap_pt=6, line_spacing=1.22)


LAYOUTS = {
    "quote": _quote,
    "matrix": _matrix,
    "exhibit": _exhibit,
    "points": _points,
    "big_stat": _big_stat,
    "kpis": _kpis,
    "chart": _chart,
    "table": _table,
    "process": _process,
    "timeline": _timeline,
    "alert": _alert,
    "comparison": _comparison,
    "actions": _actions,
}


def render_deck(spec: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    """Render a DeckSpec to a .pptx. Returns {path, slide_count}."""
    prs = Presentation()
    prs.slide_width = Inches(theme.PAGE_W)
    prs.slide_height = Inches(theme.PAGE_H)
    ctx = _Ctx(spec)

    sections = [sec for sec in spec.get("sections", []) if sec.get("slides")]
    # Indices into spec["sections"], so the page map points at the spec the
    # caller holds, not at this filtered list.
    sections_index = {id(sec): i for i, sec in enumerate(spec.get("sections", []))}
    _cover(prs, ctx)
    if len(sections) > 1:
        _agenda(prs, ctx, sections)
    # Dividers only when sections have enough in them to need separating.
    # Four one-slide sections produced four dividers around five content
    # slides -- MEASURED, nearly half the deck was chapter breaks.
    content_slides = sum(len(sec["slides"]) for sec in sections)
    use_dividers = len(sections) > 2 and content_slides >= 2 * len(sections)
    for si, sec in enumerate(sections, 1):
        if use_dividers:
            _divider(prs, ctx, si, sec)
        for sd in sec["slides"]:
            layout = LAYOUTS.get(sd.get("type"))
            if layout is not None:
                ctx.current = (sections_index[id(sec)], sec["slides"].index(sd))
                layout(prs, ctx, sec.get("title", ""), sd)
                ctx.current = None
    _sources_appendix(prs, ctx)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return {"path": str(out), "slide_count": len(prs.slides), "page_map": ctx.page_map}
