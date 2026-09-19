"""Content engine for presentations: corpus -> validated DeckSpec.

WHAT THIS REPLACED, AND WHY IT HAD TO GO. The previous pipeline asked
the model for a section outline, then filled each section with its own
retrieval and its own model call. Measured on five real prompts:

  * The outline call never succeeded. Ollama's format=json returns an
    OBJECT; the prompt asked for an ARRAY, so the code rejected every
    reply and used a hardcoded five-section fallback. Every deck had the
    same generic structure ("SENSOR TELEMETRY & SPECIFICATIONS" on an
    SOP deck).
  * Each section searched the corpus with its own generic title, so a
    deck about a pipeline incident acquired a KPI slide about sandbox
    RAM limits from an unrelated document. Topic drift, by design.
  * Slides were written independently, so nothing built on anything: no
    storyline, just five disconnected fills.

The shape here instead:

  1. ANCHOR DOCUMENTS. Find which documents the request is actually
     about, once, and read them in FULL. Every later step sees only
     those, so nothing can drift into an unrelated document.
  2. ONE OUTLINE over those documents: sections, and for each slide a
     type, a working title and the facts it should carry. Length follows
     the material -- a thin source gets a short deck, a rich one gets a
     long one, and no cap either way.
  3. ONE FILL PER SECTION, so slides in a section are written together
     and read as an argument rather than a list.
  4. VALIDATION per slide: required fields present, numbers present in
     the source text, sources resolvable. One repair attempt, then the
     slide is dropped rather than shipped broken.

Everything about how it LOOKS belongs to tools/generation/deck.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.models.ollama_client import generate as ollama_generate
from backend.models.registry import resolve_model_name

logger = logging.getLogger("pptx.deck_agent")

# Slide types the model may choose, with the fields each one needs. The
# renderer has more (cover, agenda, dividers, appendix, exhibit); those
# are placed by code, not chosen by a model.
SLIDE_TYPES: dict[str, dict[str, Any]] = {
    "points": {
        "required": ["bullets"],
        "spec": '"bullets": [str] (2-5, each a full sentence under 160 chars), '
                'optional "callout": {"value": str, "unit": str, "label": str}',
        "use": "an argument or a set of findings that belong together",
    },
    "big_stat": {
        "required": ["value", "label", "context"],
        "spec": '"value": str (the number alone), "unit": str, "label": str (what it measures), '
                '"context": str (2-3 sentences), "status": one of exceeded|below|watch|normal, '
                'optional "compare": {"value": str, "label": str}',
        "use": "one number that carries the whole message",
    },
    "kpis": {
        "required": ["items"],
        "spec": '"items": [{"value": str, "unit": str, "label": str, "note": str, '
                '"status": exceeded|below|watch|normal}] (2-4); exceeded = above its limit, '
                'below = under its range',
        "use": "several parameters read side by side",
    },
    "chart": {
        "required": ["categories", "series"],
        "spec": '"chart_type": column|line, "categories": [str], '
                '"series": [{"name": str, "values": [number]}] (values must align with categories), '
                '"unit": str, "highlight": one category to accent, "takeaways": [str] (2-3)',
        "use": "a trend or comparison across labelled periods -- only when the source gives a value per period",
    },
    "table": {
        "required": ["columns", "rows"],
        "spec": '"columns": [str] (2-4), "rows": [[str]] (each row the same length as columns), "caption": str',
        "use": "parameters against limits, or any small grid of values",
    },
    "process": {
        "required": ["steps"],
        "spec": '"steps": [{"title": str (under 40 chars), "detail": str}] (3-5)',
        "use": "a sequence of operations or an escalation path",
    },
    "timeline": {
        "required": ["events"],
        "spec": '"events": [{"date": str, "title": str, "detail": str}] (2-5)',
        "use": "dated events in order",
    },
    "alert": {
        "required": ["headline", "what"],
        "spec": '"severity": high|medium|low, "headline": str, "what": str, "impact": str, "action": str',
        "use": "ONLY for an incident, hazard, limit breach or interlock",
    },
    "comparison": {
        "required": ["columns"],
        "spec": '"columns": [{"title": str, "points": [str], "status": exceeded|below|watch|normal}] (2-3)',
        "use": "two or three options, units or periods set against each other",
    },
    "actions": {
        "required": ["items"],
        "spec": '"items": [{"action": str, "owner": str, "due": str, "priority": high|medium|low}] (2-6)',
        "use": "what must happen next -- always the closing section when the source recommends anything",
    },
}

# Words that describe the DELIVERABLE, not the subject. Retrieving on the
# request verbatim searched for documents about presentations: MEASURED,
# "Make a presentation on the CCR-1 regeneration cycle" pulled in
# PPTX_SANDBOX_MODULE_GUIDE.md as a source, and the model then took its
# slide-type names from that document's text.
_DELIVERABLE_PHRASE = re.compile(
    r"^\s*(please\s+)?(can\s+you\s+)?(make|create|prepare|build|generate|draft|put\s+together|give\s+me)\s+"
    r"(me\s+)?(a|an|the)?\s*(nice|short|quick|brief|detailed|executive|board|technical)?\s*"
    r"(power\s*point|pptx|ppt|presentation|slide\s*deck|deck|slides?|briefing)\s*"
    r"(presentation|deck)?\s*(on|about|for|covering|regarding|re)?\s*",
    re.I,
)

# A document scoring far below the best match is not what the request is
# about. Relative, not absolute: fused scores are not comparable across
# queries.
MIN_RELATIVE_SCORE = 0.55

MAX_DOCS = 3
MAX_CHARS_PER_DOC = 7000
MAX_CHARS_TOTAL = 16000
NUM_CTX = 12288
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# A value that can stand as a headline figure: optional comparator, a
# number, optional unit or percent. "34", "84%", "> 410 °C", "1,450 m3/h".
_MEASUREMENT = re.compile(r"^[<>≤≥~≈±]?\s*-?\d[\d.,]*\s*(%|[a-zA-Z°µ/²³\-\s]{0,14})$")


# Names a model reaches for that mean one of ours. Some come from the
# previous template's vocabulary, which still exists in project docs a
# model may have read; the rest are the obvious English alternatives.
TYPE_SYNONYMS = {
    "title_bullets": "points", "bullets": "points", "bullet_points": "points",
    "executive_summary": "points", "key_points": "points", "summary": "points",
    "quote_highlight": "points", "generic_grid": "points", "flexible_highlight": "points",
    "stat_callout": "big_stat", "big_number": "big_stat", "hero_stat": "big_stat",
    "multi_stat_row": "kpis", "kpi_row": "kpis", "stats": "kpis", "metrics": "kpis",
    "chart_commentary": "chart", "graph": "chart", "trend": "chart", "line_chart": "chart",
    "bar_chart": "chart", "column_chart": "chart",
    "table_data": "table", "data_table": "table", "spec_table": "table", "risk_matrix": "table",
    "process_flow": "process", "steps": "process", "workflow": "process",
    "safety_alert": "alert", "incident": "alert", "warning": "alert",
    "two_column": "comparison", "comparison_cards": "comparison", "compare": "comparison",
    "action_plan": "actions", "next_steps": "actions", "recommendations": "actions",
    "image_caption": "exhibit", "diagram": "exhibit",
}

# Field names a model uses for the same thing.
FIELD_ALIASES = {
    "val": "value", "number": "value", "figure": "value",
    "name": "label", "caption_text": "label",
    "detail": "note", "sub_label": "note",
}


def canonical_type(name):
    key = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key in SLIDE_TYPES:
        return key
    return TYPE_SYNONYMS.get(key)


class NotInCorpus(ValueError):
    """No document in the corpus covers the request."""


# ── anchoring ───────────────────────────────────────────────────────────────


def topic_of(request: str) -> str:
    """The subject of a deck request, without the deliverable words."""
    topic = _DELIVERABLE_PHRASE.sub("", request or "").strip()
    return topic or (request or "").strip()


def anchor_documents(store, chunks: list, request: str) -> list[dict]:
    """The documents this request is about, each with its full text.

    THE ONE RETRIEVAL THAT MATTERS. Section-level searches were what let
    an unrelated document into a deck; here retrieval happens once,
    against the user's own words, and everything downstream reads only
    what comes back.
    """
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    result = retrieve_with_grounding_check(store, topic_of(request), top_k=10)
    if not result.found or not result.chunks:
        raise NotInCorpus(
            "No document in the corpus covers this request "
            f"({result.reason or 'below the grounding threshold'})."
        )

    best: dict[str, float] = {}
    pages: dict[str, set] = {}
    for c in result.chunks:
        best[c.source_document] = max(best.get(c.source_document, 0.0), c.score)
        if c.page_number:
            pages.setdefault(c.source_document, set()).add(c.page_number)
    ranked = sorted(best, key=lambda d: best[d], reverse=True)
    top_score = best[ranked[0]]
    ranked = [d for d in ranked if best[d] >= top_score * MIN_RELATIVE_SCORE][:MAX_DOCS]

    by_doc: dict[str, list] = {}
    for ch in chunks or []:
        if ch.metadata.source_document in ranked:
            by_doc.setdefault(ch.metadata.source_document, []).append(ch)

    docs = []
    budget = MAX_CHARS_TOTAL
    for i, name in enumerate(ranked, 1):
        ordered = sorted(by_doc.get(name, []), key=lambda c: (c.metadata.chunk_index or 0))
        text = "\n".join(c.text for c in ordered).strip()
        if not text:
            text = "\n".join(c.text for c in result.chunks if c.source_document == name)
        allowance = min(MAX_CHARS_PER_DOC, budget)
        # AT MOST FOUR PAGES. A 15-page document matched on every page
        # printed "p.1, 2, 3, ... 15" under every slide, which is noise
        # rather than a citation.
        doc_pages = sorted(pages.get(name, []))[:4]
        docs.append({
            "id": f"S{i}",
            "document": name,
            "pages": doc_pages,
            "text": text[:allowance],
            "truncated": len(text) > allowance,
        })
        budget -= min(len(text), allowance)
        if budget <= 0:
            break
    return docs


# Stop words for the coverage check below. Deliberately small: the point
# is to find the REQUEST'S OWN nouns in the documents, not to parse
# English.
_STOP = {
    "a", "an", "the", "and", "or", "of", "for", "on", "in", "to", "our", "we", "us", "my",
    "this", "that", "these", "those", "with", "from", "at", "by", "as", "is", "are", "was",
    "were", "be", "about", "into", "over", "per", "its", "it", "their", "there", "here",
    "what", "which", "who", "how", "why", "when", "where", "all", "any", "some", "more",
    "make", "create", "prepare", "build", "generate", "draft", "give", "show", "tell",
    "presentation", "deck", "slides", "slide", "powerpoint", "pptx", "ppt", "briefing",
    "report", "summary", "overview", "please", "can", "you",
}


def topic_coverage(request: str, docs: list[dict]) -> tuple[float, list[str]]:
    """What fraction of the request's own words appear in the sources.

    A CHEAP CHECK THE COSINE GATE DOES NOT MAKE. The gate scores semantic
    similarity, and on a small corpus an unrelated document can clear it:
    MEASURED, "our retail fuel station marketing strategy for Diwali"
    retrieved a PDF about the Pradhan Mantri Jan Dhan Yojana above
    threshold, and the deck that followed was titled for Diwali and
    written about financial inclusion.

    Embeddings encode topic, not identity. Whether the words the person
    actually used appear anywhere in the documents is a different
    question, and it is the one that catches this.
    """
    words = {w for w in re.findall(r"[a-z0-9][a-z0-9/-]{2,}", topic_of(request).lower())
             if w not in _STOP}
    if not words:
        return 1.0, []
    haystack = " ".join(d["text"] for d in docs).lower()
    missing = sorted(w for w in words if w not in haystack)
    return (len(words) - len(missing)) / len(words), missing


MIN_TOPIC_COVERAGE = 0.4


def sources_can_answer(request: str, docs: list[dict]) -> tuple[bool, str]:
    """Ask the model whether these documents can answer the request.

    One call, before any planning. The alternative is what happened
    without it: a full deck, correctly formatted and properly cited, on a
    subject the sources do not discuss.
    """
    prompt = f"""Below are the only documents available. Decide whether they contain the
information needed to make a presentation answering this request.

REQUEST: "{request}"

DOCUMENTS:
{_sources_block(docs)}

Answer honestly. If the documents are about a different subject, say no, even if they are
interesting. Partial coverage of the REQUESTED subject counts as yes.

Reply with ONLY: {{"can_answer": true or false, "reason": "one short sentence"}}"""
    data = _ask_json(prompt, timeout=180)
    if not isinstance(data, dict) or "can_answer" not in data:
        return True, ""  # an unusable verdict must not block a good request
    return bool(data.get("can_answer")), str(data.get("reason") or "")


def _sources_block(docs: list[dict]) -> str:
    return "\n\n".join(
        f"[{d['id']}] {d['document']}\n{d['text']}" + ("\n…(truncated)" if d["truncated"] else "")
        for d in docs
    )


# ── model calls ─────────────────────────────────────────────────────────────


def _ask_json(prompt: str, *, model_id: str = "reasoning-model", timeout: int = 300) -> Any:
    """One JSON call. Returns parsed JSON, or None.

    format=json makes Ollama return a JSON OBJECT, never a bare array --
    the previous planner asked for an array and so failed every time.
    Every prompt here therefore asks for an object.
    """
    raw = ollama_generate(
        resolve_model_name(model_id),
        prompt,
        timeout=timeout,
        format="json",
        options={"num_ctx": NUM_CTX},
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw or "", re.S)
        if not match:
            logger.warning("Model reply was not JSON: %r", (raw or "")[:200])
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


_TYPE_MENU = "\n".join(f"- {name}: {meta['use']}" for name, meta in SLIDE_TYPES.items())


def plan_storyline(request: str, docs: list[dict]) -> dict | None:
    """Sections and, per slide, a type and the facts it should carry."""
    prompt = f"""You are preparing an operations briefing for Mangalore Refinery and Petrochemicals Limited (MRPL).

Plan a slide deck that answers this request using ONLY the source documents below.

REQUEST: "{request}"

SOURCE DOCUMENTS:
{_sources_block(docs)}

SLIDE TYPES available, and when each is right:
{_TYPE_MENU}

Plan the deck as a narrative an operations manager can follow. Rules:
1. Let the material decide the length. One slide per distinct finding, measurement set,
   cause, comparison or action group that the sources actually support. Do not pad, do not
   compress two findings into one slide, and do not aim for any particular number of slides.
2. Sections are the storyline: typically what the situation is, what the evidence shows,
   why it happened, what must happen next. Name them in the language of the documents.
3. Every slide names the facts it will use, quoting figures exactly as they appear.
4. Use "chart" only where a source gives a value for each of several labelled periods.
4a. A "process" slide holds the WHOLE sequence (3-5 steps), a "timeline" the whole run of
   events, an "actions" slide every action. NEVER one step, event or action per slide.
4b. Choose the most VISUAL type the facts support: one decisive number -> "big_stat";
   several readings -> "kpis"; readings against limits -> "table"; an ordered procedure ->
   "process"; dated events -> "timeline"; an incident or breach -> "alert". Use "points" only
   when nothing more specific fits, and never three "points" slides in a row.
5. Use "alert" only for an incident, hazard, limit breach or interlock.
6. If the sources recommend or require anything, the last section is an "actions" slide.
7. Never plan a slide the sources cannot fill.

Reply with ONLY this JSON object:
{{
  "deck_title": "a specific title naming the unit and the finding",
  "subtitle": "one line on what the deck covers",
  "sections": [
    {{
      "title": "short section name",
      "summary": "one short line",
      "slides": [
        {{"type": "one of the types above",
          "title": "the takeaway as a full sentence, under 90 characters",
          "facts": "the exact figures and statements this slide will carry",
          "source_ids": ["S1"]}}
      ]
    }}
  ]
}}"""
    data = _ask_json(prompt)
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return None
    # A model that names a type in its own words (or copies one out of a
    # source document) still gets the slide it meant.
    for section in data["sections"]:
        if not isinstance(section, dict):
            continue
        for slide in section.get("slides") or []:
            if isinstance(slide, dict):
                slide["type"] = canonical_type(slide.get("type")) or "points"
    return data


def fill_section(request: str, section: dict, docs: list[dict], feedback: str = "") -> list[dict] | None:
    """Write every slide in one section together, so they read as one argument."""
    planned = [s for s in section.get("slides", []) if isinstance(s, dict)
               and canonical_type(s.get("type")) in SLIDE_TYPES]
    for one in planned:
        one["type"] = canonical_type(one["type"])
    if not planned:
        return []
    specs = "\n".join(
        f'Slide {i + 1} — type "{p["type"]}", working title: {p.get("title", "")}\n'
        f'  facts to carry: {p.get("facts", "")}\n'
        f'  fields: {SLIDE_TYPES[p["type"]]["spec"]}'
        for i, p in enumerate(planned)
    )
    correction = f"\nA previous attempt was rejected: {feedback}\nFix exactly that.\n" if feedback else ""
    prompt = f"""You are writing slides for an MRPL operations briefing, from the source documents below.

REQUEST: "{request}"
SECTION: {section.get('title', '')} — {section.get('summary', '')}

SOURCE DOCUMENTS:
{_sources_block(docs)}

Write these slides:
{specs}
{correction}
Rules, and they are strict:
1. EVERY figure must appear in the source documents, copied exactly (including units). If a
   number is not in the sources, leave it out. Never estimate, round or invent one.
2. "title" is the slide's takeaway as a full sentence, specific, under 90 characters. Never a
   generic label like "Key Metrics" or "Overview".
3. Write for an operations manager: plain, direct, no filler and no marketing language.
4. Fill every field the type requires. Omit an optional field rather than filling it with
   something vague.
5. "sources" lists the source ids this slide's facts came from, e.g. ["S1"].
6. No markdown, no asterisks, no bullet characters in the text itself.

Reply with ONLY this JSON object:
{{"slides": [{{"type": ..., "title": ..., "sources": ["S1"], ...type fields...}}]}}"""
    data = _ask_json(prompt)
    if not isinstance(data, dict):
        return None
    slides = data.get("slides")
    if isinstance(slides, dict):
        slides = [slides]
    return slides if isinstance(slides, list) else None


# ── validation ──────────────────────────────────────────────────────────────


def _numbers(value: Any) -> set[float]:
    """Every number in `value`, as floats.

    NUMERIC, not textual. Comparing the strings rejected "84.0" against a
    source that says "84%" -- the same measurement written differently --
    while a genuinely invented figure (91, the midpoint the model guessed
    for a "90-96%" range) has to stay caught.
    """
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    out: set[float] = set()
    for token in _NUMBER.findall(text):
        try:
            out.add(float(token.replace(",", "")))
        except ValueError:
            continue
    return out


def _dedupe_unit(item: dict) -> dict:
    """Drop a unit the model already put inside the value.

    It returned {"value": "478°C", "unit": "°C"}, which rendered as
    "478°C °C", and {"value": "0.5%", "unit": "O2%"}.
    """
    value, unit = str(item.get("value") or "").strip(), str(item.get("unit") or "").strip()
    if not value or not unit:
        return item
    compact = unit.replace(" ", "").lower()
    if compact and compact in value.replace(" ", "").lower():
        return {**item, "value": value, "unit": ""}
    return item


# Per list type: the list, and the field in each item the layout renders.
ITEM_TEXT_FIELD = {
    "timeline": ("events", "title"), "process": ("steps", "title"), "actions": ("items", "action"),
    "kpis": ("items", "label"), "comparison": ("columns", "title"),
}


def validate_slide(slide: Any, docs: list[dict]) -> tuple[dict | None, str]:
    """A slide fit to render, or (None, why not).

    The number check is the load-bearing one: a figure on a refinery
    slide that no source contains is a fabricated measurement with a
    citation attached. Single digits are exempt -- they are counts and
    step numbers, not measurements.
    """
    if not isinstance(slide, dict):
        return None, "not an object"
    stype = canonical_type(slide.get("type"))
    meta = SLIDE_TYPES.get(stype)
    if not meta:
        return None, f"unknown slide type {slide.get('type')!r}"

    out = {k: v for k, v in slide.items() if k not in ("facts", "source_ids")}
    out["type"] = stype
    if "sources" not in out and isinstance(slide.get("source_ids"), list):
        out["sources"] = slide["source_ids"]
    if isinstance(out.get("stats"), list) and not out.get("items"):
        out["items"] = out.pop("stats")
    if isinstance(out.get("items"), list):
        out["items"] = [
            _dedupe_unit({FIELD_ALIASES.get(k, k): v for k, v in it.items()}) if isinstance(it, dict) else it
            for it in out["items"]
        ]
    if stype == "big_stat":
        out = {**out, **_dedupe_unit({"value": out.get("value"), "unit": out.get("unit")})}
    # The list a type needs, under the other names a model files it: seven
    # "process" slides were dropped for an empty "steps" while the model
    # had put the sequence under another key.
    list_aliases = {
        "process": ("steps", ("sequence", "stages", "phases", "items", "procedure")),
        "timeline": ("events", ("milestones", "phases", "items", "dates")),
        "actions": ("items", ("actions", "recommendations", "next_steps", "tasks")),
    }
    if stype in list_aliases:
        target, aliases = list_aliases[stype]
        if not out.get(target):
            for alias in aliases:
                if isinstance(slide.get(alias), list) and slide[alias]:
                    out[target] = slide[alias]
                    break
        if stype == "process" and isinstance(out.get("steps"), list):
            out["steps"] = [{"title": st} if isinstance(st, str) else st for st in out["steps"]]
        if stype == "actions" and isinstance(out.get("items"), list):
            out["items"] = [{"action": it} if isinstance(it, str) else it for it in out["items"]]
    if stype == "points" and not out.get("bullets"):
        for alias in ("points", "text", "lines"):
            if isinstance(slide.get(alias), list):
                out["bullets"] = [str(b) for b in slide[alias]]
                break
    title = str(out.get("title") or "").strip()
    if len(title) < 8:
        return None, "title missing or too short"
    out["title"] = title

    for field in meta["required"]:
        value = out.get(field)
        if value in (None, "", [], {}):
            return None, f"required field {field!r} is empty"

    # EVERY ITEM MUST CARRY WHAT ITS LAYOUT DRAWS. Measured: a timeline's
    # events came back with KPI field names (value/label/note), passed the
    # "events is non-empty" check, and rendered as a bare axis on an
    # otherwise blank page. Caught by the page reviewer, not by layout
    # measurement -- an empty page has nothing to overflow.
    if stype in ITEM_TEXT_FIELD:
        list_field, text_field = ITEM_TEXT_FIELD[stype]
        items = out.get(list_field) or []
        bad = [i for i, it in enumerate(items, 1)
               if not isinstance(it, dict) or not str(it.get(text_field) or "").strip()]
        if bad:
            return None, (f"{stype} {list_field} {bad[:4]} have no {text_field!r}; each needs: "
                          f"{meta['spec']}")

    if stype == "table":
        cols = out.get("columns") or []
        rows = []
        for row in out.get("rows") or []:
            if isinstance(row, dict):
                row = [row.get(c, "") for c in cols]
            if not isinstance(row, (list, tuple)):
                return None, "table rows must be lists"
            rows.append([str(c) for c in row][: len(cols)])
        if not rows:
            return None, "table has no rows"
        out["columns"] = [str(c) for c in cols]
        out["rows"] = rows

    if stype == "chart":
        cats = [str(c) for c in out.get("categories") or []]
        series = []
        for ser in out.get("series") or []:
            if not isinstance(ser, dict):
                continue
            values = ser.get("values")
            if not isinstance(values, list):
                continue
            try:
                nums = [float(str(v).replace(",", "")) for v in values[: len(cats)]]
            except (TypeError, ValueError):
                return None, "chart values must be numbers"
            if len(nums) != len(cats):
                return None, "chart needs one value per category"
            series.append({"name": str(ser.get("name") or ""), "values": nums})
        if len(cats) < 2 or not series:
            return None, "chart needs at least two categories and one series"
        out["categories"], out["series"] = cats, series

    # A MEASUREMENT IS A NUMBER. The model put "Replace P-HS-02 discharge
    # flange gasket" in a KPI card's value, and "Hassan Pumping Station" in
    # a callout; both rendered as headline figures.
    if stype == "kpis":
        for it in out.get("items") or []:
            if not isinstance(it, dict) or not _MEASUREMENT.match(str(it.get("value", "")).strip()):
                return None, ("kpis values must be measurements (a number with an optional unit); "
                              "use an actions or points slide for statements")
    if stype == "big_stat" and not _MEASUREMENT.match(str(out.get("value", "")).strip()):
        return None, "big_stat value must be a number"
    status_bearers = [out] if stype == "big_stat" else (out.get("items") or []) if stype == "kpis" else []
    for item in status_bearers:
        clash = _status_contradiction(item)
        if clash:
            return None, clash
    if stype == "points" and isinstance(out.get("callout"), dict):
        if not _MEASUREMENT.match(str(out["callout"].get("value", "")).strip()):
            out.pop("callout")

    known = {d["id"] for d in docs}
    out["sources"] = [s for s in (out.get("sources") or []) if s in known] or [docs[0]["id"]]

    sourced = _numbers(" ".join(d["text"] for d in docs))
    content = {k: v for k, v in out.items() if k not in ("sources", "type", "notes")}
    # Single digits are exempt: they are counts, step numbers and list
    # positions, not measurements.
    unsourced = {n for n in _numbers(content) if n >= 10 and n not in sourced}
    if unsourced:
        pretty = ", ".join(f"{n:g}" for n in sorted(unsourced)[:6])
        return None, f"these figures are in no source document: {pretty}"
    return out, ""


_SAYS_BELOW = re.compile(r"\b(below|under|lower than|short of|less than)\b", re.I)
_SAYS_ABOVE = re.compile(r"\b(above|exceed\w*|over|higher than|more than|breach\w*)\b", re.I)


def _status_contradiction(item: dict) -> str:
    """The status pill must agree with the words beside it.

    Measured: CCR-1's chlorination efficiency (84% against 90-96) shipped
    with the note "Below normal range" and a red EXCEEDED pill, because
    the schema offered no status for a value under its range. Rejected so
    the repair pass picks the status that matches, never silently changed.
    """
    status = str(item.get("status") or "").strip().lower()
    words = " ".join(str(item.get(k) or "") for k in ("note", "context", "label"))
    below, above = bool(_SAYS_BELOW.search(words)), bool(_SAYS_ABOVE.search(words))
    if status == "exceeded" and below and not above:
        return (f"status 'exceeded' contradicts {words.strip()[:80]!r}; use status 'below' "
                "for a value under its range")
    if status == "below" and above and not below:
        return (f"status 'below' contradicts {words.strip()[:80]!r}; use status 'exceeded' "
                "for a value over its limit")
    return ""


# ── assembly ────────────────────────────────────────────────────────────────


# Types whose content is a list, and the field that holds it. Consecutive
# slides of the same type each holding a single item are fragments of one
# slide: the model returned eight "process" slides of one step each for a
# changeout sequence, which rendered as eight slides with a lone numbered
# circle. Merged here rather than re-prompted, because the content is
# right and only its packaging is wrong -- and the renderer paginates
# whatever the merge produces.
_LIST_FIELD = {"process": "steps", "timeline": "events", "actions": "items", "points": "bullets"}


def _merge_fragments(slides: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for slide in slides:
        field = _LIST_FIELD.get(slide.get("type"))
        previous = merged[-1] if merged else None
        if (
            field
            and previous is not None
            and previous.get("type") == slide.get("type")
            and len(slide.get(field) or []) <= 2
            and len(previous.get(field) or []) <= 8
        ):
            previous[field] = list(previous.get(field) or []) + list(slide.get(field) or [])
            previous["sources"] = sorted(set(previous.get("sources", []) + slide.get("sources", [])))
            continue
        merged.append(dict(slide))
    return merged


# "Homopolymer H030SG: 22 batches produced." -- a label, one figure, a unit.
_LABELLED_FIGURE = re.compile(
    r"^\s*(?P<label>[^:]{2,60}?)\s*[:–—-]\s*(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>%|[A-Za-z/°][\w/°.]*)?(?:\s+[a-z][\w ]*)?\.?\s*$"
)


def _chart_from_list(slide: dict) -> dict:
    """A points slide listing one figure per label, in one unit, becomes a column chart.

    The model wrote August's production mix as four bullets ("H030SG: 22
    batches produced", ...); the page reviewer rated it plain, and it is a
    comparison a reader should see, not read. Nothing new is introduced:
    labels and values are the bullets' own, already checked against the
    sources, and only the largest is accented.
    """
    bullets = slide.get("bullets") or []
    if slide.get("type") != "points" or not 3 <= len(bullets) <= 8:
        return slide
    parsed = [_LABELLED_FIGURE.match(str(b)) for b in bullets]
    if not all(parsed):
        return slide
    units = {(m.group("unit") or "").lower() for m in parsed}
    if len(units) != 1:
        return slide
    cats = [m.group("label").strip() for m in parsed]
    values = [float(m.group("value").replace(",", "")) for m in parsed]
    if len(set(cats)) != len(cats):
        return slide
    chart = {
        "type": "chart", "title": slide.get("title", ""), "chart_type": "column",
        "categories": cats, "series": [{"name": slide.get("title", ""), "values": values}],
        "unit": parsed[0].group("unit") or "", "sources": slide.get("sources", []),
    }
    if values.count(max(values)) == 1:
        chart["highlight"] = cats[values.index(max(values))]
    if slide.get("notes"):
        chart["notes"] = slide["notes"]
    return chart


def build_deck_spec(request: str, store, chunks: list, *, max_repairs: int = 1) -> dict:
    """The whole content pipeline: corpus in, validated DeckSpec out."""
    import datetime as dt

    docs = anchor_documents(store, chunks, request)

    coverage, missing = topic_coverage(request, docs)
    if coverage < MIN_TOPIC_COVERAGE:
        raise NotInCorpus(
            "The documents in the corpus do not cover this request: none of them mention "
            f"{', '.join(missing[:6])}. Nothing was generated."
        )
    answerable, why = sources_can_answer(request, docs)
    if not answerable:
        raise NotInCorpus(
            f"The corpus does not contain what this request needs{': ' + why if why else ''}. "
            "Nothing was generated."
        )

    plan = plan_storyline(request, docs)
    if not plan:
        raise NotInCorpus(
            "The planner could not produce a usable outline for this request from the "
            "documents in the corpus."
        )

    sections_out: list[dict] = []
    dropped: list[str] = []
    for section in plan.get("sections", []):
        if not isinstance(section, dict):
            continue
        slides = fill_section(request, section, docs)
        if not slides:
            dropped.append(f"{section.get('title', '?')}: the model returned no usable slide")
            slides = []
        good: list[dict] = []
        for i, raw in enumerate(slides):
            slide, why = validate_slide(raw, docs)
            attempts = 0
            while slide is None and attempts < max_repairs:
                attempts += 1
                logger.info("Slide rejected (%s); asking for a repair.", why)
                planned_one = {"title": section.get("title"), "summary": section.get("summary"),
                               "slides": [section.get("slides", [])[i]] if i < len(section.get("slides", [])) else []}
                repaired = fill_section(request, planned_one, docs, feedback=why) or []
                slide, why = validate_slide(repaired[0], docs) if repaired else (None, why)
            if slide is None:
                dropped.append(f"{section.get('title', '?')}: {why}")
                continue
            good.append(_chart_from_list(slide))
        if good:
            sections_out.append({
                "title": str(section.get("title") or "").strip() or "Findings",
                "summary": str(section.get("summary") or "").strip(),
                "slides": good,
            })

    sections_out = [
        {**sec, "slides": _merge_fragments(sec["slides"])} for sec in sections_out
    ]

    if not sections_out:
        raise NotInCorpus(
            "Nothing in the corpus could fill a slide for this request." +
            (f" Rejected: {'; '.join(dropped[:3])}" if dropped else "")
        )

    used = {sid for sec in sections_out for sl in sec["slides"] for sid in sl["sources"]}
    spec = {
        "title": str(plan.get("deck_title") or request).strip(),
        "subtitle": str(plan.get("subtitle") or "").strip(),
        "date": dt.date.today().strftime("%d %B %Y"),
        "sources": [
            {"id": d["id"], "document": d["document"], "pages": d["pages"],
             "used_for": "Figures and statements cited on the slides that reference it"}
            for d in docs if d["id"] in used
        ],
        "sections": sections_out,
    }
    return {
        "deck_spec": spec,
        "slide_titles": [sl["title"] for sec in sections_out for sl in sec["slides"]],
        "documents": [d["document"] for d in docs if d["id"] in used],
        "dropped_slides": dropped,
    }
