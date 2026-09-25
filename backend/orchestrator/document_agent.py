"""Content engine for documents and spreadsheets: corpus -> validated spec.

WHAT THIS REPLACED, AND WHY. Presentations got a content engine (anchored
documents, a written storyline, every figure checked against the sources)
while Word/PDF/Excel kept the first thing that worked: retrieve loosely
relevant chunks, paste each one in as a section, generate a heading.
MEASURED on "Draft a PDF report on the CCR-1 regeneration cycle 18
findings": twelve sections drawn from NINE documents, among them
VIBECODING_SPEC.md, OWNERSHIP.md, TOOLS.md and Sahil.md -- this project's
own paperwork, in a refinery report, under a heading that made it look
like plant evidence.

So documents are built the way decks are, from the same functions:

  1. ANCHOR the request to the documents it is actually about
     (deck_agent.anchor_documents), read in full.
  2. REFUSE when the corpus does not cover the request, rather than
     writing a plausible document out of whatever came back.
  3. PLAN sections, then WRITE each one from the anchored text, with the
     source ids it rests on.
  4. VALIDATE: every figure of 10 or more must appear in the sources,
     numerically; a section with no resolvable source is dropped rather
     than shipped looking like the sourced ones.

LONG SOURCES (a whole book) WORK DIFFERENTLY, BECAUSE THEY HAVE TO. The
anchored text is capped at 16,000 characters -- about four pages of a
500-page book -- so a request to summarise one saw its opening and nothing
else, and every section was written from the same prompt. For a source
past LONG_SOURCE_CHARS:

  * the OUTLINE is planned from passages spread evenly across the whole
    document, so the plan covers the end as well as the beginning;
  * each section is then written from only the passages that match ITS
    heading, selected by word overlap inside the anchored documents (no
    model call, no chance of drifting into another document);
  * sections are written CONCURRENTLY, because each one is now a small,
    independent prompt.

A 10-20 section report from a book therefore costs about as much as one
long call, not twenty of them.

A spreadsheet is the same pipeline with a different shape at the end:
sheets of headers and rows, each row carrying its source, and any cell
the sources do not give left EMPTY and marked unsourced -- never filled
with a plausible number.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.orchestrator.deck_agent import (
    MIN_TOPIC_COVERAGE,
    figure_label_mismatches,
    NotInCorpus,
    _ask_json,
    _numbers,
    _sources_block,
    anchor_documents,
    choose_writer,
    source_chars,
    sources_can_answer,
    topic_coverage,
    topic_of,
    writer_timeout,
)

logger = logging.getLogger("documents.agent")

MAX_SECTIONS = 8
MIN_BODY_CHARS = 120
# A section of a long-source report carries more: twenty sections of two
# sentences is a three-page summary of a five-hundred-page book, and the
# ask is ten to twenty pages.
MIN_BODY_CHARS_LONG = 600

# Past this much anchored text, the whole document cannot be shown to the
# model at once and the long-source path is used instead.
LONG_SOURCE_CHARS = 20000
# A long source earns more sections: this is what makes a 10-20 page PDF.
MAX_SECTIONS_LONG = 20
# ...and a FLOOR. Given a range of "3 to 20" for a 593-page book the model
# planned four sections and produced a one-page summary. A long source is
# the case where the reader wants the whole of it covered.
MIN_SECTIONS_LONG = 14
# A long source is planned in consecutive groups, so every stretch of it is
# covered rather than whichever part the model found interesting.
OUTLINE_GROUPS = 5
OUTLINE_SAMPLES_PER_GROUP = 6
SECTIONS_PER_GROUP = 4
# Passages sampled across the document to plan from, and their size.
OUTLINE_SAMPLES = 16
OUTLINE_SAMPLE_CHARS = 700
# Characters of matched passage given to one section's writer.
SECTION_CONTEXT_CHARS = 3000
# Sections written at once. MEASURED against this Ollama: four concurrent
# calls finished in 18 s of wall clock against 48 s of call time, a 2.7x
# speedup, so the server does serve them in parallel from one resident
# model. Five keeps the KV cache modest on an 8 GB card.
SECTION_WORKERS = 5
# How much anchored source text a report may read. Far above the deck's
# budget because sections read PASSAGES of it rather than the whole thing:
# a 593-page book is about 1.2 million characters.
DOC_SOURCE_BUDGET = 2_000_000


def plan_long_document(request: str, docs: list[dict], *, writer: str) -> dict | None:
    """Plan a long source in GROUPS, each covering one stretch of it.

    Asked for "between 14 and 20 sections" over a 593-page book in one call,
    the model planned six and the report came to two pages. The document is
    split into consecutive groups of passages and each group is planned on
    its own, concurrently: every part of the source gets its own sections,
    and the count follows the material instead of the model's appetite.
    """
    from concurrent.futures import ThreadPoolExecutor

    pieces = _passages(docs, OUTLINE_SAMPLE_CHARS)
    if not pieces:
        return None
    groups: list[list[tuple[str, str]]] = []
    stride = max(1, len(pieces) // OUTLINE_GROUPS)
    for start in range(0, len(pieces), stride):
        chunk = pieces[start:start + stride]
        if chunk:
            groups.append(chunk)
    groups = groups[:OUTLINE_GROUPS]

    def plan_group(index_and_group):
        index, group = index_and_group
        step = max(1, len(group) // OUTLINE_SAMPLES_PER_GROUP)
        view = "\n\n".join(f"[{sid}] …{text}…" for sid, text in group[::step][:OUTLINE_SAMPLES_PER_GROUP])
        prompt = f"""You are planning part {index + 1} of {len(groups)} of a report, from the passages
below. They are consecutive extracts from one long source; part {index + 1} covers this stretch of it.

REQUEST: {request}

PASSAGES:
{view}

Plan EXACTLY {SECTIONS_PER_GROUP} sections covering what THIS stretch contains, in its own
vocabulary. Four sections, not fewer: this stretch is a fifth of a long document.
Headings say what the material says, never "Introduction" or "Overview". For each section list
the facts it must carry, copied from the passages above.

Reply with ONLY this JSON object:
{{"sections": [{{"heading": "...", "must_cover": ["fact", "fact"], "source_ids": ["S1"]}}]}}"""
        def ask() -> list[dict]:
            data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer),
                             num_ctx=_context_bucket((len(prompt) // 3) + 1024))
            if not isinstance(data, dict):
                return []
            return [s for s in (data.get("sections") or []) if isinstance(s, dict) and s.get("heading")]

        # Asked for four sections a group returned one or two, and five groups
        # planned eight sections for a 593-page book. A thin group is asked
        # once more before its stretch of the source goes uncovered.
        planned = ask()
        # Only a group that came back nearly empty is worth a second call:
        # asking again for a group that gave three costs a planning round
        # for one extra section.
        if len(planned) < 2:
            planned = max(planned, ask(), key=len)
        return planned

    with ThreadPoolExecutor(max_workers=SECTION_WORKERS) as pool:
        planned = list(pool.map(plan_group, enumerate(groups)))
    sections = [s for group in planned for s in group][:MAX_SECTIONS_LONG]
    if not sections:
        return None
    topic = topic_of(request)
    return {"title": (topic[:1].upper() + topic[1:]) if topic else request.strip(),
            "subtitle": f"From {docs[0]['document']}", "sections": sections}


def plan_document(request: str, docs: list[dict], *, writer: str) -> dict | None:
    """Section headings and what each must cover, from these documents only."""
    long_source = source_chars(docs) >= LONG_SOURCE_CHARS
    if long_source:
        return plan_long_document(request, docs, writer=writer)
    max_sections = MAX_SECTIONS_LONG if long_source else MAX_SECTIONS
    section_count = (f"Between {MIN_SECTIONS_LONG} and {max_sections}" if long_source
                     else f"Between 3 and {max_sections}")
    sources_view = outline_view(docs) if long_source else _sources_block(docs)
    prompt = f"""You are planning a report from the source documents below, using ONLY them.
Write about what THESE documents are about: they may be plant procedures, a legal text, a
textbook or anything else, and the report follows their subject, not a house style.

REQUEST: {request}

SOURCES:
{sources_view}

Plan the report. Rules:
1. {section_count} sections, in the order a reader needs them: what happened,
   what was measured, what it means, what must happen next.
2. Every section must be answerable from the sources above. Do not plan a section the
   sources cannot fill.
2a. Each section covers DIFFERENT material. Two sections retelling the same incident
   under different headings read as two findings; plan one.
3. Headings say the finding, not the category: "Bed inlet ran six hours long" or
   "Section 66A was struck down", never "Introduction" or "Overview".
4. List the facts each section must carry, copied from the sources.
5. For a long source, the sections must cover it END TO END, not only its opening:
   the passages above are taken from across the whole document.

Reply with ONLY this JSON object:
{{"title": "the report title", "subtitle": "one line of context",
  "sections": [{{"heading": "...", "must_cover": ["fact", "fact"], "source_ids": ["S1"]}}]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer))
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return None
    sections = [s for s in data["sections"] if isinstance(s, dict) and s.get("heading")][:max_sections]
    if not sections:
        return None
    return {"title": str(data.get("title") or request).strip(),
            "subtitle": str(data.get("subtitle") or "").strip(),
            "sections": sections}


def write_section(request: str, section: dict, docs: list[dict], *, writer: str,
                  long_source: bool = False) -> dict | None:
    """One section's prose, grounded in the anchored documents."""
    # MEASURED: asked for "8 to 12 sentences, at least 700 characters" in a
    # single `body`, this model returns about 334 -- it writes one field
    # short however the length is worded. Asked for three or four PARAGRAPHS
    # it writes each of them, which is how a section reaches the length a
    # ten-page report needs without three times the calls.
    length = ("2 to 4 full sentences" if long_source else "2 to 5 full sentences")
    reply_shape = ('{"heading": "...", "paragraphs": ["...", "...", "..."], "sources": ["S1"], '
                   '"contains_estimate": false}' if long_source else
                   '{"heading": "...", "body": "...", "sources": ["S1"], "contains_estimate": false}')
    paragraph_rule = ("6. Write THREE OR FOUR paragraphs, each on a different part of the material "
                      "above. Each paragraph is {length} long.\n" if long_source else "")
    prompt = f"""You are writing one section of a report, using ONLY the source documents
below. Write about what THEY are about, in their own vocabulary.

REPORT REQUEST: {request}
SECTION HEADING: {section.get('heading')}
THIS SECTION MUST COVER: {'; '.join(str(f) for f in (section.get('must_cover') or []))}

SOURCES:
{_sources_block(docs)}

Rules:
1. Write plain, precise English in the subject's own terms. No bullet points, no headings.
2. EVERY figure must appear in the sources above, copied exactly, with its unit.
3. Never write a number the sources do not contain. If a fact is missing, write the
   section without it rather than estimating.
4. "sources" lists the source ids ([S1], [S2]) this section's claims come from.
{paragraph_rule}

Reply with ONLY this JSON object:
{reply_shape}"""
    # The window this call needs, ROUNDED TO A BUCKET. Sizing it exactly to
    # each prompt gave every call a different num_ctx, and Ollama reloads the
    # model when the context size changes: twenty "concurrent" sections ran
    # one after another, 348 s for 20 calls that take 17 s each. Sharing one
    # bucket lets the server keep a single instance with parallel slots.
    window = _context_bucket((len(prompt) // 3) + 1024)
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer), num_ctx=window)
    if not isinstance(data, dict):
        return None
    paragraphs = [str(par).strip() for par in (data.get("paragraphs") or []) if str(par).strip()]
    if paragraphs:
        data["body"] = "\n\n".join(paragraphs)
    return data


def _passages(docs: list[dict], size: int = 1200) -> list[tuple[str, str]]:
    """The anchored text as (source id, passage) pairs of roughly `size`."""
    out: list[tuple[str, str]] = []
    for doc in docs:
        text = doc["text"]
        for start in range(0, len(text), size):
            piece = text[start:start + size].strip()
            if len(piece) > 200:
                out.append((doc["id"], piece))
    return out


def outline_view(docs: list[dict]) -> str:
    """Passages spread across the WHOLE source, for planning a long document.

    Reading the first 16,000 characters of a 500-page book and calling it
    the source is how a "summary" ends up covering only chapter one.
    """
    pieces = _passages(docs, OUTLINE_SAMPLE_CHARS)
    if len(pieces) <= OUTLINE_SAMPLES:
        chosen = pieces
    else:
        step = len(pieces) / OUTLINE_SAMPLES
        chosen = [pieces[int(i * step)] for i in range(OUTLINE_SAMPLES)]
    return "\n\n".join(f"[{sid}] …{text}…" for sid, text in chosen)


def _words(text: str) -> set[str]:
    """Words and figures worth matching on.

    Numbers count: "Procedure 47", "Section 12.3" and "IT Act 2000" are
    identified by their figures, and a matcher that drops them selected the
    opening of the document for every section.
    """
    import re as _re

    return {w for w in _re.findall(r"[a-z][a-z0-9.-]{2,}|\d[\d.]*", text.lower())}


def context_for(section: dict, docs: list[dict]) -> list[dict]:
    """The passages of the anchored documents that match this heading.

    Word overlap, not a model call and not a fresh corpus search: the
    material is already the right document, and the only question is which
    part of it this section is about.
    """
    wanted = _words(str(section.get("heading", "")) + " " +
                    " ".join(str(f) for f in (section.get("must_cover") or [])))
    if not wanted:
        return docs
    scored = []
    for sid, piece in _passages(docs):
        overlap = len(wanted & _words(piece))
        if overlap:
            scored.append((overlap, sid, piece))
    scored.sort(key=lambda t: t[0], reverse=True)

    by_id = {d["id"]: d for d in docs}
    kept: dict[str, list[str]] = {}
    budget = SECTION_CONTEXT_CHARS
    for _score, sid, piece in scored:
        if budget <= 0:
            break
        kept.setdefault(sid, []).append(piece[:budget])
        budget -= len(piece)
    if not kept:
        return [{**docs[0], "text": docs[0]["text"][:SECTION_CONTEXT_CHARS]}]
    return [{**by_id[sid], "text": "\n…\n".join(pieces)} for sid, pieces in kept.items()]


# TWO SECTIONS ARE THE SAME SECTION when they share most of their words AND
# their figures. MEASURED on a live PDF: "Batch H110F-0847 Exceeded MFI Spec
# Limit" and "Grade Changeover Checklist Updated" both told the whole story
# of the same batch -- same MFI, same excursion, same 20-minute hold point --
# under two headings, which reads as two findings.
#
# Word overlap ALONE is not enough to say so: sections of a manual describing
# different procedures share their vocabulary ("procedure", "purge", "the
# check the manual requires") while being about different things. Their
# FIGURES differ, and the retelling's do not.
DUPLICATE_OVERLAP = 0.75


def _overlap(a: str, b: str) -> float:
    """Fraction of the shorter section's words that the longer one repeats."""
    wa = {w for w in a.lower().split() if len(w) > 3}
    wb = {w for w in b.lower().split() if len(w) > 3}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _same_figures(a: str, b: str) -> bool:
    fa, fb = _numbers(a), _numbers(b)
    if not fa and not fb:
        return True
    if not fa or not fb:
        return False
    return len(fa & fb) / min(len(fa), len(fb)) >= 0.8


def is_retelling(body: str, earlier: str) -> bool:
    return _overlap(body, earlier) >= DUPLICATE_OVERLAP and _same_figures(body, earlier)


def validate_section(section: Any, docs: list[dict], *, min_body: int = MIN_BODY_CHARS
                     ) -> tuple[dict | None, str]:
    """A section fit to publish, or (None, why not).

    The figure check is the load-bearing one, exactly as it is for slides:
    a number in a refinery report that no source contains is a fabricated
    measurement with a citation next to it.
    """
    if not isinstance(section, dict):
        return None, "not an object"
    heading = str(section.get("heading") or "").strip()
    body = " ".join(str(section.get("body") or "").split())
    # 4, not 6: "Risk" and "Costs" are legitimate headings.
    if len(heading) < 4:
        return None, "heading missing or too short"
    if len(body) < min_body:
        return None, f"body is {len(body)} characters; a section needs at least {min_body}"

    known = {d["id"] for d in docs}
    sources = [s for s in (section.get("sources") or []) if s in known]
    if not sources:
        return None, "no source id this section rests on"

    sourced = _numbers(" ".join(d["text"] for d in docs))
    unsourced = {n for n in _numbers(body) if n >= 10 and n not in sourced}
    if unsourced:
        pretty = ", ".join(f"{n:g}" for n in sorted(unsourced)[:6])
        return None, f"these figures are in no source document: {pretty}"

    return {"heading": heading, "body": body, "sources": sources,
            "contains_estimate": bool(section.get("contains_estimate"))}, ""


# Context sizes we ask Ollama for. Anything else forces a reload.
CONTEXT_BUCKETS = (4096, 8192, 12288)


def _context_bucket(tokens: int) -> int:
    for bucket in CONTEXT_BUCKETS:
        if tokens <= bucket:
            return bucket
    return CONTEXT_BUCKETS[-1]


def _bounded(docs: list[dict]) -> list[dict]:
    """The same documents, cut to what a model call can actually read."""
    if source_chars(docs) < LONG_SOURCE_CHARS:
        return docs
    return [{**d, "text": outline_view([d]), "truncated": True} for d in docs]


def build_document_spec(request: str, store, chunks: list, *, max_repairs: int = 1) -> dict:
    """Corpus in, validated document spec out. Raises NotInCorpus when it cannot."""
    docs = anchor_documents(store, chunks, request,
                            max_chars_per_doc=DOC_SOURCE_BUDGET, max_chars_total=DOC_SOURCE_BUDGET)

    coverage, missing = topic_coverage(request, docs)
    if coverage < MIN_TOPIC_COVERAGE:
        raise NotInCorpus(
            "The documents in the corpus do not cover this request: none of them mention "
            f"{', '.join(missing[:6])}. Nothing was written.")
    # The relevance check is a MODEL call, so it must be shown a bounded view:
    # handing it a 1.4-million-character book overflowed the window and it
    # answered that the documents were unrelated to their own subject.
    answerable, why = sources_can_answer(request, _bounded(docs))
    if not answerable:
        raise NotInCorpus(
            f"The corpus does not contain what this request needs{': ' + why if why else ''}. "
            "Nothing was written.")

    writer = choose_writer(docs)
    import time as _time

    _t0 = _time.time()
    plan = plan_document(request, docs, writer=writer)
    plan_seconds = _time.time() - _t0
    if not plan:
        raise NotInCorpus("The planner could not produce a usable report outline from these documents.")

    long_source = source_chars(docs) >= LONG_SOURCE_CHARS
    # Where the wall clock goes, reported with the result: planning, writing,
    # and how many sections had to be written twice.
    timings = {"plan_seconds": round(plan_seconds, 1), "rewrites": 0, "calls": 0}

    def write_one(planned: dict) -> tuple[dict, dict | None, str]:
        """One section, from only the passages that match it."""
        # A long source is not shown whole to any section: its own passages
        # are, which keeps the prompt small enough to be quick and specific.
        context = context_for(planned, docs) if long_source else docs
        min_body = MIN_BODY_CHARS_LONG if long_source else MIN_BODY_CHARS
        timings["calls"] += 1
        written = write_section(request, planned, context, writer=writer, long_source=long_source)
        # WRITTEN from its own passages, VALIDATED against the whole anchored
        # source: a figure that appears in another chapter of the same book is
        # sourced, and checking it against this section's passages alone
        # rejected eight of nine sections of a book summary.
        section, why = validate_section(written, docs, min_body=min_body)
        attempts = 0
        while section is None and attempts < max_repairs:
            attempts += 1
            timings["rewrites"] += 1
            timings["calls"] += 1
            logger.info("Section rejected (%s); rewriting.", why)
            retry = dict(planned)
            retry["must_cover"] = list(planned.get("must_cover") or []) + [f"Fix: {why}"]
            written = write_section(request, retry, context, writer=writer, long_source=long_source)
            section, why = validate_section(written, docs, min_body=min_body)
        return planned, section, why

    _t1 = _time.time()
    if long_source and SECTION_WORKERS > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=SECTION_WORKERS) as pool:
            written_sections = list(pool.map(write_one, plan["sections"]))
    else:
        written_sections = [write_one(planned) for planned in plan["sections"]]
    timings["write_seconds"] = round(_time.time() - _t1, 1)

    sections: list[dict] = []
    dropped: list[str] = []
    for planned, section, why in written_sections:
        if section is None:
            dropped.append(f"{planned.get('heading', '?')}: {why}")
            continue
        twin = next((s for s in sections if is_retelling(section["body"], s["body"])), None)
        if twin is not None:
            dropped.append(f"{section['heading']}: says the same as {twin['heading']!r}")
            continue
        sections.append(section)

    if not sections:
        raise NotInCorpus(
            "Nothing in the corpus could fill a section of this report." +
            (f" Rejected: {'; '.join(dropped[:3])}" if dropped else ""))

    by_id = {d["id"]: d for d in docs}
    used = {sid for sec in sections for sid in sec["sources"]}
    # Sourced figures whose LABEL differs from the source's wording. Not a
    # rejection: paraphrase is legitimate and a wrong label is for a person
    # to judge, so they go on the approval card.
    relabelled = sorted({fig for sec in sections
                         for fig in figure_label_mismatches(sec["body"], docs)})
    return {
        "title": plan["title"],
        "subtitle": plan["subtitle"],
        "sections": sections,
        "documents": [by_id[s]["document"] for s in sorted(used) if s in by_id],
        "dropped_sections": dropped,
        "relabelled_figures": relabelled,
        "timings": timings,
        "writer": writer,
        "topic": topic_of(request),
    }


# ── spreadsheets ────────────────────────────────────────────────────────────


def plan_sheets(request: str, docs: list[dict], *, writer: str) -> list[dict] | None:
    """Sheets of headers and rows, every value copied from the sources."""
    prompt = f"""You are building a spreadsheet from the source documents below, using ONLY
them, whatever their subject is.

REQUEST: {request}

SOURCES:
{_sources_block(docs)}

Rules:
1. One to three sheets. Each has a short name, 2 to 6 column headers, and its data rows.
1a. EVERY row the sources give for this subject, not a sample. If the sources list four
   grades, batches or dates, the sheet has four rows.
2. EVERY value must be copied from the sources above, exactly, including units.
3. If the sources do not give a value for a cell, put an empty string "" there. NEVER
   estimate, infer or invent a figure -- an empty cell reads as unknown, a plausible one
   reads as measured.
4. Every row lists the source ids its values come from.

Reply with ONLY this JSON object:
{{"sheets": [{{"sheet_name": "...", "headers": ["..."],
   "rows": [{{"cells": ["...", "..."], "sources": ["S1"]}}]}}]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer))
    if not isinstance(data, dict) or not isinstance(data.get("sheets"), list):
        return None
    return [s for s in data["sheets"] if isinstance(s, dict)] or None


def validate_sheet(sheet: Any, docs: list[dict]) -> tuple[dict | None, str]:
    """A sheet fit to write, with unsourced cells emptied rather than guessed."""
    if not isinstance(sheet, dict):
        return None, "not an object"
    headers = [str(h).strip() for h in (sheet.get("headers") or []) if str(h).strip()]
    if not 2 <= len(headers) <= 6:
        return None, f"a sheet needs 2 to 6 headers, got {len(headers)}"

    known = {d["id"] for d in docs}
    sourced = _numbers(" ".join(d["text"] for d in docs))
    rows, emptied = [], 0
    for raw in sheet.get("rows") or []:
        cells = raw.get("cells") if isinstance(raw, dict) else raw
        if not isinstance(cells, (list, tuple)) or not any(str(c).strip() for c in cells):
            continue
        row_sources = [s for s in ((raw.get("sources") if isinstance(raw, dict) else []) or []) if s in known]
        clean = []
        for cell in list(cells)[:len(headers)]:
            text = str(cell).strip()
            # A figure the sources do not contain is emptied, not printed:
            # a spreadsheet cell reads as measured.
            if {n for n in _numbers(text) if n >= 10 and n not in sourced}:
                emptied += 1
                text = ""
            clean.append(text)
        clean += [""] * (len(headers) - len(clean))
        rows.append({"cells": clean, "sources": row_sources,
                     "is_unsourced": not row_sources or not any(clean)})
    if not rows:
        return None, "no rows the sources support"
    return {"sheet_name": str(sheet.get("sheet_name") or "Sheet1").strip()[:31],
            "headers": headers, "rows": rows, "emptied_cells": emptied}, ""


def build_spreadsheet_spec(request: str, store, chunks: list) -> dict:
    """Corpus in, validated sheets out. Raises NotInCorpus when it cannot."""
    docs = anchor_documents(store, chunks, request)
    coverage, missing = topic_coverage(request, docs)
    if coverage < MIN_TOPIC_COVERAGE:
        raise NotInCorpus(
            "The documents in the corpus do not cover this request: none of them mention "
            f"{', '.join(missing[:6])}. Nothing was written.")

    writer = choose_writer(docs)
    planned = plan_sheets(request, _bounded(docs), writer=writer)
    if not planned:
        raise NotInCorpus("The model could not build a table from these documents.")

    sheets, dropped = [], []
    for raw in planned:
        sheet, why = validate_sheet(raw, docs)
        if sheet is None:
            dropped.append(f"{(raw or {}).get('sheet_name', '?')}: {why}")
            continue
        sheets.append(sheet)
    if not sheets:
        raise NotInCorpus("No sheet could be filled from the corpus." +
                          (f" Rejected: {'; '.join(dropped[:3])}" if dropped else ""))

    by_id = {d["id"]: d for d in docs}
    used = {s for sh in sheets for row in sh["rows"] for s in row["sources"]}
    topic = topic_of(request)
    return {
        # The subject, capitalised once -- not Title Case, which turned
        # "QA" into "Qa" and read like a headline generator.
        "title": (topic[:1].upper() + topic[1:]) if topic else request.strip(),
        "sheets": sheets,
        "documents": [by_id[s]["document"] for s in sorted(used) if s in by_id],
        "dropped_sheets": dropped,
        "writer": writer,
        "emptied_cells": sum(s["emptied_cells"] for s in sheets),
    }
