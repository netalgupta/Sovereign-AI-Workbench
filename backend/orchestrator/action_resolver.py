"""Turn an intercepted instruction into the tool call it actually means.

THE BUG THIS EXISTS TO FIX, WHICH IS THE DEMO ITSELF.

router_node intercepts write actions and registers an approval under the
tool name `operator_requested_action`. No such tool is registered. So
the flagship scenario in the problem statement --

    "reading a scanned inspection report, pulling out key findings and
     drafting an approval note as a Word file"

-- ran like this: the request was intercepted, the modal appeared, the
operator approved, and execute_approved() called

    call_tool("operator_requested_action", ...)
      -> KeyError: No tool named 'operator_requested_action'

The gate obtained consent to run something that was wired to nothing. It
is the worst possible shape for a safety control: the ceremony is
complete, the audit entry exists, and the effect the person authorised
cannot happen. A refusal would have been better, because a refusal is
visible.

WHAT THIS DOES INSTEAD.

An intercepted instruction is resolved to a CONCRETE, REGISTERED tool
call with real arguments BEFORE approval is requested. The operator then
approves the thing that will run -- the actual filename, the actual
section headings, the actual sources each section rests on -- and
approving it runs exactly that, because the gate hashes the arguments it
showed.

WHERE THERE IS NO TOOL, THERE IS NO PRETENDING.

Four of the five intercepted categories have no connector in this build:
setpoint changes, SAP/ERP writes, outbound sends and destructive
changes. They are resolved to `executable=False` with the reason stated,
and the UI offers acknowledgement rather than an Execute button that
would fail. A system that cannot do something should say so at the point
of asking, not after consent has been recorded.

GROUNDING APPLIES TO DRAFTED DOCUMENTS TOO.

The sections handed to draft_docx come from retrieval, and each carries
the source documents its claims came from. A section with no source is
marked UNSOURCED in the file itself by the tool. A drafted approval note
is a document that leaves the building and gets signed; an unsourced
paragraph inside one that looks exactly like a sourced one is the same
failure as an uncited number in chat, with a longer life.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Where drafted deliverables land. Under the repo rather than a system
# temp directory: the operator has to be able to find, open and send the
# file, and a path they cannot navigate to is a file that did not arrive.
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"

# Categories that can actually be carried out by this build.
_EXECUTABLE = {"file write"}


@dataclass
class ResolvedAction:
    """An intercepted instruction, resolved to something concrete."""

    category: str
    executable: bool
    tool_name: str | None = None
    arguments: dict = field(default_factory=dict)
    effect: str = ""
    # Plain-language description of what will be produced, shown in the
    # approval modal. Never a function signature: being shown
    # draft_docx({...}) is not informed consent.
    preview: list[str] = field(default_factory=list)
    reason: str = ""
    # Set when the action continues as a background job (presentations):
    # the job files the approval itself when its work is done.
    job_id: str | None = None


def resolve(request: str, category: str, *, session_id: str = "default") -> ResolvedAction:
    """What this instruction actually means, as a tool call or a refusal."""
    if category not in _EXECUTABLE:
        return ResolvedAction(
            category=category,
            executable=False,
            effect=(
                f"Operator-requested {category}, from the instruction: "
                f'"{request.strip()}". '
                f"The system has NOT resolved a target device, value or "
                f"endpoint for this, and has no connector that could carry "
                f"it out."
            ),
            reason=(
                f"No {category} connector is installed in this build. "
                f"Approving records your authorisation; it does not cause "
                f"the action, because nothing here can perform it."
            ),
        )

    return _resolve_output(request, session_id=session_id)


_DECK_RE = re.compile(r"\b(pptx|powerpoint|presentation|slide\s*deck|slides)\b", re.I)


# The same signal agent_loop._tools_for_request uses to narrow a drafting
# turn to search_documents + draft_xlsx. One spelling, both paths: the
# interceptor and the schema-narrowing decision must not drift.
# "comparison table" is a spreadsheet even without the word "Excel";
# the refinery lexicon ("memo", "report") is deliberately excluded
# because those are document words, handled by the docx path.
_XLSX_REQUEST_RE = re.compile(
    r"(?:\.xlsx|spreadsheet|excel|comparison table|comparison matrix|"
    r"(?:build|draft|create|make)\b.*(?:table|matrix)\b)",
    re.I,
)


def is_spreadsheet_request(request: str) -> bool:
    """Does this file-write request ask for a spreadsheet, not a document?

    Lives here (not in agent_loop) because it is the resolver's decision
    too: an intercepted Excel request must resolve to draft_xlsx, or the
    operator approves a .docx where they asked for a .xlsx.
    """
    return bool(_XLSX_REQUEST_RE.search(request or ""))


_PDF_REQUEST_RE = re.compile(
    r"(?:\.pdf|pdf report|pdf document|(?:build|draft|create|make|export|write)\b.*(?:pdf))",
    re.I,
)


def is_pdf_request(request: str) -> bool:
    """Does this file-write request ask for a PDF document?

    Lives here (alongside is_spreadsheet_request) so the interceptor and
    agent_loop tool-narrowing decision stay unified.
    """
    return bool(_PDF_REQUEST_RE.search(request or ""))


def is_deck_request(request: str) -> bool:
    """Does this file-write request ask for a presentation?

    Deliberately NOT bare "deck" or "slide": "tray deck" and "slide valve"
    are refinery equipment, and a request to write up a slide valve
    inspection is a document, not a presentation.
    """
    return bool(_DECK_RE.search(request or ""))


def output_kind_for(request: str) -> str:
    """Which deliverable this request asks for: deck, xlsx, pdf or docx.

    One place, so the interceptor, the job and agent_loop's tool narrowing
    cannot disagree about whether "build a comparison table" is a
    spreadsheet or a Word document.
    """
    if is_deck_request(request):
        return "deck"
    if is_spreadsheet_request(request):
        return "xlsx"
    if is_pdf_request(request):
        return "pdf"
    return "docx"


def _resolve_output(request: str, *, session_id: str) -> ResolvedAction:
    """Start the deliverable as a background job; approval comes when it is ready.

    Writing takes minutes on local models (and a deck is also illustrated
    and reviewed page by page), so the approval is filed by the job once
    the work is done -- the operator approves the real sections, sheets or
    slides AND sees what was checked. Nothing is written until then.
    """
    from backend.orchestrator import output_jobs

    kind = output_kind_for(request)
    label = output_jobs.KINDS[kind][0]
    job = output_jobs.start(request, session_id=session_id, kind=kind)
    return ResolvedAction(
        category="file write",
        executable=False,
        effect=f'Create a {label} for: "{request.strip()}"',
        reason="Building in the background; approval is requested when it is finished and checked.",
        job_id=job.job_id,
    )


def deck_job_reply(resolved: ResolvedAction) -> str:
    """What chat says when an output job starts. Shared by both chat paths."""
    from backend.orchestrator import output_jobs

    job = output_jobs.get(resolved.job_id or "")
    kind = job.kind if job else "deck"
    label = output_jobs.KINDS.get(kind, ("deliverable",))[0]
    stages = (
        "writing the slides from the source documents → local artwork → rendering every "
        "page, measuring its layout and reviewing its design, fixing weak pages → your approval"
        if kind == "deck" else
        "finding the documents this rests on → writing it section by section → checking every "
        "figure against those documents → your approval"
    )
    return "\n".join([
        f"**Building your {label} in the background.**",
        "",
        f"Stages: {stages}.",
        "",
        f"Job `{resolved.job_id}`. Nothing is written until you approve the finished file.",
    ])


def deck_preview(output_path: Path, titles: list[str], citations: list[str], omitted: list[str],
                 *, quality: dict | None = None, unit: str = "slide",
                 report: dict | None = None) -> list[str]:
    """The approval card's lines: file, what is in it, sources, what was checked."""
    # One title per line, and only the first few. Joined into a single
    # line, a 15-slide deck produced an unreadable wall of text on the
    # one screen where a person is meant to check what they are approving.
    shown = titles[:8]
    preview = [
        f"Creates the file {output_path.name}",
        f"{len(titles)} {unit}(s):",
        *[f"   {i}. {t}" for i, t in enumerate(shown, 1)],
    ]
    if len(titles) > len(shown):
        preview.append(f"   … and {len(titles) - len(shown)} more")
    preview.append("Sources: " + ("; ".join(citations) or "none"))
    if omitted:
        preview.append("Left out for lack of a source: " + "; ".join(omitted[:3]))
    if quality is not None:
        from backend.orchestrator.output_jobs import quality_line

        preview.append(quality_line(quality))
    if report:
        preview.append(_report_line(report))
    preview.append(f"Written to {output_path.parent}")
    return preview


def _report_line(report: dict) -> str:
    """What was checked on a document or spreadsheet, in one line."""
    parts = []
    if "sections" in report:
        parts.append(f"{report['sections']} section(s) written, every figure checked against the sources")
        if report.get("estimates"):
            parts.append(f"{report['estimates']} marked as containing an estimate")
    if "sheets" in report:
        parts.append(f"{report['sheets']} sheet(s), {report.get('rows', 0)} row(s)")
        if report.get("emptied_cells"):
            parts.append(f"{report['emptied_cells']} cell(s) left EMPTY: no source gives that value")
    if report.get("dropped"):
        parts.append(f"{len(report['dropped'])} dropped for lack of a source")
    return "Checked: " + "; ".join(parts) if parts else "Checked: nothing to report"


def _resolve_document_draft(request: str, *, session_id: str) -> ResolvedAction:
    """Build the actual draft_docx / draft_xlsx / generate_pdf call this request describes."""
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    is_xlsx = is_spreadsheet_request(request)
    is_pdf = is_pdf_request(request)
    title = _title_for(request)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kind_slug = "xlsx" if is_xlsx else ("pdf" if is_pdf else "docx")
    output_path = OUTPUT_DIR / f"{_slug(title)}-{stamp}.{kind_slug}"
    doc_kind = "spreadsheet" if is_xlsx else ("PDF document" if is_pdf else "Word document")

    sections: list[dict] = []
    documents: list[str] = []
    try:
        store, _ = get_state().ensure_corpus()
        chunks = _individually_relevant_chunks(store, request)
        for chunk in chunks:
            name = getattr(chunk, "source_document", None)
            if name and name not in documents:
                documents.append(name)
            sections.append({
                "heading": _heading_for(chunk, len(sections) + 1),
                "body": (getattr(chunk, "text", "") or "").strip(),
                "sources": [name] if name else [],
                "contains_estimate": False,
            })
    except Exception as exc:  # noqa: BLE001
        # Retrieval failing is reported, not papered over with an empty
        # document. A drafted file with invented contents is worse than
        # no file.
        return ResolvedAction(
            category="file write",
            executable=False,
            effect=f'Draft a {doc_kind} for: "{request.strip()}"',
            reason=(
                f"Could not read the corpus to ground this file "
                f"({type(exc).__name__}: {exc}). Nothing will be written: a "
                f"drafted file with invented contents is worse than no "
                f"file."
            ),
        )

    if not sections:
        return ResolvedAction(
            category="file write",
            executable=False,
            effect=f'Draft a {doc_kind} for: "{request.strip()}"',
            reason=(
                "Nothing in the loaded corpus clears the grounding threshold "
                "for this request, so every row would be UNSOURCED. "
                "Add the relevant document under Sources, or name the "
                "document you mean."
            ),
        )

    if is_xlsx:
        return _resolve_spreadsheet(title, sections, documents, output_path, request)
    if is_pdf:
        return _resolve_pdf(title, sections, documents, output_path, request)
    return _resolve_word(title, sections, documents, output_path, request)


def _resolve_pdf(
    title: str, sections: list[dict], documents: list[str],
    output_path: Path, request: str,
) -> ResolvedAction:
    """The generate_pdf call built from retrieved, individually relevant sections."""
    preview = [
        f"Creates the file {output_path.name}",
        f"{len(sections)} section(s), drawn from "
        f"{len(documents)} source document(s): {', '.join(documents)}",
        "Every section names the document its claims came from; a section "
        "without one is marked [UNSOURCED] in the file itself",
        f"Written to {OUTPUT_DIR}",
    ]

    return ResolvedAction(
        category="file write",
        executable=True,
        tool_name="generate_pdf",
        arguments={
            "title": title,
            "subtitle": f"Exported from the loaded corpus on "
                        f"{datetime.now().strftime('%d %b %Y')}",
            "sections": sections,
            "output_path": str(output_path),
        },
        effect=(
            f'Requested: "{request.strip()}"\n'
            f"Effect: write a PDF document to {output_path.name}, containing "
            f"{len(sections)} section(s) grounded in "
            f"{len(documents)} source document(s)."
        ),
        preview=preview,
    )


def _resolve_word(
    title: str, sections: list[dict], documents: list[str],
    output_path: Path, request: str,
) -> ResolvedAction:
    """The draft_docx call built from retrieved, individually relevant sections."""
    preview = [
        f"Creates the file {output_path.name}",
        f"{len(sections)} section(s), drawn from "
        f"{len(documents)} source document(s): {', '.join(documents)}",
        "Every section names the document its claims came from; a section "
        "without one is marked UNSOURCED in the file itself",
        f"Written to {OUTPUT_DIR}",
    ]

    return ResolvedAction(
        category="file write",
        executable=True,
        tool_name="draft_docx",
        arguments={
            "title": title,
            "subtitle": f"Drafted from the loaded corpus on "
                        f"{datetime.now().strftime('%d %b %Y')}",
            "sections": sections,
            "output_path": str(output_path),
        },
        effect=(
            # THE OPERATOR'S OWN WORDS STAY IN THE RECORD.
            #
            # Describing only the effect ("Write a Word document to
            # X.docx...") is precise and loses something that matters on
            # an approval screen: what the person actually asked for.
            # Consent is given to an instruction, and an audit entry that
            # records only the consequence cannot show the two matched.
            f'Requested: "{request.strip()}"\n'
            f"Effect: write a Word document to {output_path.name}, containing "
            f"{len(sections)} section(s) grounded in "
            f"{len(documents)} source document(s)."
        ),
        preview=preview,
    )


def _resolve_spreadsheet(
    title: str, sections: list[dict], documents: list[str],
    output_path: Path, request: str,
) -> ResolvedAction:
    """The draft_xlsx call built from the same retrieved sections.

    The approval shows the real row structure -- column headers, a row
    per retrieved finding, and the source each row rests on -- because
    approving that call is what actually runs. A row with no source is
    marked UNSOURCED in the file by the tool.
    """
    headers = ["Finding / Topic", "Details", "Sourced From"]
    rows = []
    for s in sections:
        srcs = list(s.get("sources") or [])
        rows.append({
            "cells": [
                s.get("heading", "") or "",
                (s.get("body", "") or "").strip(),
                "; ".join(srcs) if srcs else "UNSOURCED",
            ],
            "sources": srcs,
        })
    sheets = [{
        "sheet_name": (title or "Findings")[:31],
        "headers": headers,
        "rows": rows,
        "sources": documents,
    }]

    preview = [
        f"Creates the file {output_path.name}",
        f"1 sheet(s) with columns {', '.join(headers)}",
        f"{len(rows)} row(s) drawn from "
        f"{len(documents)} source document(s): {', '.join(documents)}",
        "Every row names the document its claims came from; a row "
        "without one is marked UNSOURCED in the file itself",
        f"Written to {OUTPUT_DIR}",
    ]

    return ResolvedAction(
        category="file write",
        executable=True,
        tool_name="draft_xlsx",
        arguments={
            "title": title,
            "subtitle": f"Drafted from the loaded corpus on "
                        f"{datetime.now().strftime('%d %b %Y')}",
            "sheets": sheets,
            "output_path": str(output_path),
        },
        effect=(
            f'Requested: "{request.strip()}"\n'
            f"Effect: write an Excel spreadsheet to {output_path.name}, "
            f"containing {len(rows)} row(s) grounded in "
            f"{len(documents)} source document(s)."
        ),
        preview=preview,
    )


def _individually_relevant_chunks(store, request: str) -> list:
    """Passages that each belong in this document on their own merit.

    A DIFFERENT CRITERION FROM CHAT, DELIBERATELY, and this is not the
    duplicated-retrieval mistake it resembles. An answer needs the top-k
    passages that are COLLECTIVELY sufficient to respond; the model then
    uses what is relevant and ignores the rest. A document has no such
    filter: every passage handed over becomes a section with a heading,
    and the reader assumes it is there because it belongs.

    Measured, before this existed. "Draft an approval note on the CCR1
    regeneration cycle inspection findings" produced a seven-section
    document whose first two sections were an Aromatic Complex benzene
    safety circular and a Kasargod depot tank-calibration thread --
    correctly attributed, entirely unrelated, and sitting under headings
    reading "Finding 1" and "Finding 2" in a document about CCR1. In
    chat that is a weak answer. In a Word file that gets signed and
    forwarded it is a manufactured finding.

    Each passage is therefore kept only if it clears the SAME dense
    similarity floor the grounding gate uses, on its own -- not because
    it placed in the top k of a small corpus. top_k against 21 chunks
    returns a quarter of the corpus for every query; rank means very
    little at that size.

    Sparse-only matches are dropped here rather than admitted without a
    score. For a document, silently omitting a marginal passage is
    recoverable; including an off-topic one is not.
    """
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.grounded_retrieval import confidence_threshold
    from backend.retrieval.hybrid_search import RetrievedChunk
    from backend.retrieval.query_builder import build_search_query

    search_query = build_search_query(request, store.all_chunk_texts())
    embedding = embed_texts([search_query])[0]
    threshold = confidence_threshold()

    kept: list = []
    for faiss_id, similarity in store.dense_search(embedding, top_k=12):
        if similarity < threshold:
            continue
        stored = store.get_by_faiss_id(faiss_id)
        if stored is None:
            continue
        kept.append(
            RetrievedChunk(
                text=stored.text,
                source_document=stored.source_document,
                page_number=stored.page_number,
                score=float(similarity),
            )
        )
    return kept


# Words that describe the ACT of drafting rather than the subject of the
# document, and would otherwise end up in the title.
_INSTRUCTION_WORDS = re.compile(
    r"^\s*(?:please\s+)?(?:can\s+you\s+|could\s+you\s+)?"
    r"(?:draft|write|generate|create|produce|prepare|make|export|save)\s+"
    r"(?:me\s+)?(?:an?\s+|the\s+)?"
    r"(?:new\s+)?"
    r"(?:word\s+|docx\s+|doc\s+)?"
    r"(?:excel\s+|spreadsheet\s+|xlsx\s+|sheet\s+)?",
    re.I,
)
_TRAILING_INSTRUCTION = re.compile(
    r"\s*(?:and\s+)?(?:save|write|export)\s+it(?:\s+(?:to|as|in)\s+\S+)?\s*[.!]?\s*$",
    re.I,
)


def _title_for(request: str) -> str:
    """A document title from the instruction, without the instruction."""
    text = " ".join((request or "").split())
    text = _INSTRUCTION_WORDS.sub("", text)
    text = _TRAILING_INSTRUCTION.sub("", text)
    text = text.strip(" .,:;-")
    # "draft it" leaves the bare pronoun, and a Word document titled
    # "It" is not a naming quirk -- it is the filename the operator has
    # to find, send and archive.
    if not text or text.lower() in _NOT_A_TITLE or len(text) < 3:
        return "Drafted Document"
    return text[:1].upper() + text[1:120]


_NOT_A_TITLE = {
    "it", "this", "that", "one", "them", "these", "those", "the", "a", "an",
}


def _heading_for(chunk, index: int) -> str:
    name = getattr(chunk, "source_document", None)
    page = getattr(chunk, "page_number", None)
    if name and page is not None:
        return f"Finding {index} — {name}, p. {page}"
    if name:
        return f"Finding {index} — {name}"
    return f"Finding {index}"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (cleaned or "document")[:60]
