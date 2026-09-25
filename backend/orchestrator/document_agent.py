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
    NotInCorpus,
    _ask_json,
    _numbers,
    _sources_block,
    anchor_documents,
    choose_writer,
    sources_can_answer,
    topic_coverage,
    topic_of,
    writer_timeout,
)

logger = logging.getLogger("documents.agent")

MAX_SECTIONS = 8
MIN_BODY_CHARS = 120


def plan_document(request: str, docs: list[dict], *, writer: str) -> dict | None:
    """Section headings and what each must cover, from these documents only."""
    prompt = f"""You are writing a report for MRPL refinery operations, using ONLY the source
documents below.

REQUEST: {request}

SOURCES:
{_sources_block(docs)}

Plan the report. Rules:
1. Between 3 and {MAX_SECTIONS} sections, in the order a reader needs them: what happened,
   what was measured, what it means, what must happen next.
2. Every section must be answerable from the sources above. Do not plan a section the
   sources cannot fill.
3. Headings say the finding, not the category: "Cycle 18 ran six hours long", not
   "Introduction".
4. List the facts each section must carry, copied from the sources.

Reply with ONLY this JSON object:
{{"title": "the report title", "subtitle": "one line of context",
  "sections": [{{"heading": "...", "must_cover": ["fact", "fact"], "source_ids": ["S1"]}}]}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer))
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return None
    sections = [s for s in data["sections"] if isinstance(s, dict) and s.get("heading")][:MAX_SECTIONS]
    if not sections:
        return None
    return {"title": str(data.get("title") or request).strip(),
            "subtitle": str(data.get("subtitle") or "").strip(),
            "sections": sections}


def write_section(request: str, section: dict, docs: list[dict], *, writer: str) -> dict | None:
    """One section's prose, grounded in the anchored documents."""
    prompt = f"""You are writing one section of an MRPL operations report, using ONLY the
source documents below.

REPORT REQUEST: {request}
SECTION HEADING: {section.get('heading')}
THIS SECTION MUST COVER: {'; '.join(str(f) for f in (section.get('must_cover') or []))}

SOURCES:
{_sources_block(docs)}

Rules:
1. Write 2 to 5 full sentences of plain operational English. No bullet points, no headings.
2. EVERY figure must appear in the sources above, copied exactly, with its unit.
3. Never write a number the sources do not contain. If a fact is missing, write the
   section without it rather than estimating.
4. "sources" lists the source ids ([S1], [S2]) this section's claims come from.

Reply with ONLY this JSON object:
{{"heading": "...", "body": "...", "sources": ["S1"], "contains_estimate": false}}"""
    data = _ask_json(prompt, model_id=writer, timeout=writer_timeout(writer))
    if not isinstance(data, dict):
        return None
    return data


def validate_section(section: Any, docs: list[dict]) -> tuple[dict | None, str]:
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
    if len(body) < MIN_BODY_CHARS:
        return None, f"body is {len(body)} characters; a section needs at least {MIN_BODY_CHARS}"

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


def build_document_spec(request: str, store, chunks: list, *, max_repairs: int = 1) -> dict:
    """Corpus in, validated document spec out. Raises NotInCorpus when it cannot."""
    docs = anchor_documents(store, chunks, request)

    coverage, missing = topic_coverage(request, docs)
    if coverage < MIN_TOPIC_COVERAGE:
        raise NotInCorpus(
            "The documents in the corpus do not cover this request: none of them mention "
            f"{', '.join(missing[:6])}. Nothing was written.")
    answerable, why = sources_can_answer(request, docs)
    if not answerable:
        raise NotInCorpus(
            f"The corpus does not contain what this request needs{': ' + why if why else ''}. "
            "Nothing was written.")

    writer = choose_writer(docs)
    plan = plan_document(request, docs, writer=writer)
    if not plan:
        raise NotInCorpus("The planner could not produce a usable report outline from these documents.")

    sections: list[dict] = []
    dropped: list[str] = []
    for planned in plan["sections"]:
        written = write_section(request, planned, docs, writer=writer)
        section, why = validate_section(written, docs)
        attempts = 0
        while section is None and attempts < max_repairs:
            attempts += 1
            logger.info("Section rejected (%s); rewriting.", why)
            retry = dict(planned)
            retry["must_cover"] = list(planned.get("must_cover") or []) + [f"Fix: {why}"]
            written = write_section(request, retry, docs, writer=writer)
            section, why = validate_section(written, docs)
        if section is None:
            dropped.append(f"{planned.get('heading', '?')}: {why}")
            continue
        sections.append(section)

    if not sections:
        raise NotInCorpus(
            "Nothing in the corpus could fill a section of this report." +
            (f" Rejected: {'; '.join(dropped[:3])}" if dropped else ""))

    by_id = {d["id"]: d for d in docs}
    used = {sid for sec in sections for sid in sec["sources"]}
    return {
        "title": plan["title"],
        "subtitle": plan["subtitle"],
        "sections": sections,
        "documents": [by_id[s]["document"] for s in sorted(used) if s in by_id],
        "dropped_sections": dropped,
        "writer": writer,
        "topic": topic_of(request),
    }


# ── spreadsheets ────────────────────────────────────────────────────────────


def plan_sheets(request: str, docs: list[dict], *, writer: str) -> list[dict] | None:
    """Sheets of headers and rows, every value copied from the sources."""
    prompt = f"""You are building a spreadsheet for MRPL refinery operations, using ONLY the
source documents below.

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
    planned = plan_sheets(request, docs, writer=writer)
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
