"""Deliverables as background jobs: write, check, THEN ask for approval.

WHY A JOB. Anything worth approving takes minutes on local models:
planning and writing (the larger writer for long sources), and for a deck
also artwork and a page-by-page review with repairs. Holding a chat
request open for that long is not an interface. The operator starts the
job, watches its stages, and is asked to approve only a finished
deliverable -- with its quality report on the approval card.

FOUR KINDS, ONE PIPELINE. A presentation, a Word document, a PDF and a
spreadsheet differ in what they write and how they are checked, not in how
they are grounded: each one anchors the request to the documents it is
actually about, refuses when the corpus does not cover it, and verifies
every figure against those documents before anything is offered for
approval.

WHAT IS WRITTEN WHERE. Nothing reaches outputs/ until the operator
approves: a deck job renders previews into a temporary directory to
measure and review them, and deletes it. Approval runs the deliverable's
tool with the FINAL spec (for a deck, including the review loop's
pagination fixes), producing exactly what was checked (hard constraint #4).

ONE AT A TIME. The card holds one of LLM / image model / page reviewer at
once, so jobs run on a single worker in submission order. Jobs live in
memory: a backend restart forgets them, and says so by not finding them.
"""

from __future__ import annotations

import logging
import queue
import re
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("pptx.jobs")

STAGES = ("queued", "writing", "artwork", "reviewing", "awaiting_approval")

# kind -> (what it is called, the registered tool approval runs, file suffix)
KINDS = {
    "deck": ("presentation", "generate_deck", ".pptx"),
    "docx": ("Word document", "draft_docx", ".docx"),
    "pdf": ("PDF document", "generate_pdf", ".pdf"),
    "xlsx": ("spreadsheet", "draft_xlsx", ".xlsx"),
}


@dataclass
class OutputJob:
    job_id: str
    request: str
    session_id: str
    kind: str = "deck"          # a KINDS key
    status: str = "queued"      # a STAGES entry, or "refused" | "failed"
    detail: str = ""            # what the current stage is doing, e.g. "Reviewing page 4 of 11"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    stage_times: dict[str, float] = field(default_factory=dict)
    writer: str | None = None
    # Slide titles for a deck, section headings for a document,
    # sheet names for a spreadsheet: what the approval card lists.
    slide_titles: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    quality: dict | None = None
    # What was checked for a document or spreadsheet: sections
    # written, sources used, anything dropped, cells emptied.
    report: dict | None = None
    rounds: list[dict] = field(default_factory=list)
    approval: dict | None = None
    error: str | None = None
    # The reviewed, final spec. Kept so an expired approval can be asked for
    # again without redoing the job; never sent in the status payload.
    _spec: dict | None = None
    _filename: str = ""

    def public(self) -> dict:
        d = asdict(self)
        d.pop("_spec", None)
        d.pop("_filename", None)
        d["elapsed_seconds"] = round((self.finished_at or time.time()) - self.created_at, 1)
        return d


_jobs: dict[str, OutputJob] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def start(request: str, session_id: str = "default", kind: str = "deck") -> OutputJob:
    """Queue a deliverable of `kind` for `request`. Returns immediately."""
    global _worker
    if kind not in KINDS:
        raise ValueError(f"Unknown output kind {kind!r}; expected one of {', '.join(sorted(KINDS))}")
    job = OutputJob(job_id=f"{kind}-{uuid.uuid4().hex[:10]}", request=request.strip(),
                    session_id=session_id, kind=kind)
    with _lock:
        _jobs[job.job_id] = job
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="deck-jobs", daemon=True)
            _worker.start()
    _queue.put(job.job_id)
    return job


def get(job_id: str) -> OutputJob | None:
    return _jobs.get(job_id)


def all_jobs() -> list[OutputJob]:
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def _work() -> None:
    while True:
        job_id = _queue.get()
        job = _jobs.get(job_id)
        if job is None:
            continue
        try:
            run(job)
        except Exception as exc:  # noqa: BLE001 - recorded on the job, never swallowed
            logger.exception("Output job %s failed", job_id)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = job.finished_at or time.time()


def _stage(job: OutputJob, status: str, detail: str = "") -> None:
    job.status, job.detail = status, detail
    job.stage_times[status] = time.time()
    logger.info("Output job %s (%s): %s %s", job.job_id, job.kind, status, detail)


def run(job: OutputJob) -> OutputJob:
    """Every stage, in order, on the calling thread (the worker, or a test)."""
    from backend.orchestrator.deck_agent import NotInCorpus

    try:
        if job.kind == "deck":
            _run_deck(job)
        elif job.kind == "xlsx":
            _run_spreadsheet(job)
        else:
            _run_document(job)
    except NotInCorpus as exc:
        # The corpus does not cover this. Refusing is the answer, not a
        # plausible file written from whatever came back.
        job.status, job.error, job.finished_at = "refused", str(exc), time.time()
        return job
    request_approval(job)
    return job


def _run_document(job: OutputJob) -> None:
    """A Word or PDF document: anchored, written section by section, checked."""
    from backend.api.state import get_state
    from backend.orchestrator.document_agent import build_document_spec

    _stage(job, "writing", "Finding the source documents and writing the report")
    store, chunks = get_state().ensure_corpus()
    spec = build_document_spec(job.request, store, chunks,
                               progress=lambda msg: setattr(job, "detail", msg))
    by_name = spec["documents"]
    job.writer = spec["writer"]
    job.slide_titles = [s["heading"] for s in spec["sections"]]
    job.citations = by_name
    job._filename = f"MRPL_{_slug(spec['title'])}{KINDS[job.kind][2]}"
    job.report = {
        "sections": len(spec["sections"]),
        "sources": by_name,
        "dropped": spec["dropped_sections"],
        "estimates": sum(1 for s in spec["sections"] if s["contains_estimate"]),
        "relabelled_figures": spec.get("relabelled_figures") or [],
        "timings": spec.get("timings") or {},
    }
    job._spec = {
        "title": spec["title"],
        "subtitle": spec["subtitle"],
        "sections": [_section_for_tool(s, spec) for s in spec["sections"]],
    }


def _run_spreadsheet(job: OutputJob) -> None:
    """A spreadsheet: every cell from the sources, unsourced cells left empty."""
    from backend.api.state import get_state
    from backend.orchestrator.document_agent import build_spreadsheet_spec

    _stage(job, "writing", "Finding the source documents and building the table")
    store, chunks = get_state().ensure_corpus()
    spec = build_spreadsheet_spec(job.request, store, chunks)
    job.writer = spec["writer"]
    job.slide_titles = [s["sheet_name"] for s in spec["sheets"]]
    job.citations = spec["documents"]
    job._filename = f"MRPL_{_slug(spec['title'])}{KINDS[job.kind][2]}"
    job.report = {
        "sheets": len(spec["sheets"]),
        "rows": sum(len(s["rows"]) for s in spec["sheets"]),
        "sources": spec["documents"],
        "dropped": spec["dropped_sheets"],
        "emptied_cells": spec["emptied_cells"],
    }
    job._spec = {
        "title": spec["title"],
        "sheets": [{"sheet_name": s["sheet_name"], "headers": s["headers"],
                    "rows": [{"cells": r["cells"], "sources": _names_for(r["sources"], spec),
                              "is_unsourced": r["is_unsourced"]} for r in s["rows"]]}
                   for s in spec["sheets"]],
    }


def _names_for(source_ids: list, spec: dict) -> list:
    """Source ids -> document names, which is what the writing tools print."""
    documents = spec.get("documents") or []
    return [documents[int(sid[1:]) - 1] for sid in source_ids
            if sid[1:].isdigit() and 0 < int(sid[1:]) <= len(documents)] or documents[:1]


def _section_for_tool(section: dict, spec: dict) -> dict:
    out = {"heading": section["heading"], "body": section["body"],
           "sources": _names_for(section["sources"], spec),
           "contains_estimate": section["contains_estimate"]}
    if section.get("note"):
        out["note"] = section["note"]
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^\w-]+", "_", (text or "Report")[:40]).strip("_") or "Report"


def _run_deck(job: OutputJob) -> None:
    """A presentation: written, illustrated, then reviewed page by page."""
    from backend.orchestrator.slide_agent import prepare_deck
    from backend.tools.generation.deck import improve, render

    _stage(job, "writing", "Finding the source documents and writing the slides")
    prepared = prepare_deck(job.request, session_id=job.session_id)
    spec = prepared["deck_spec"]
    job.writer = prepared.get("writer")
    job.slide_titles, job.citations = prepared["slide_titles"], prepared["citations"]
    job._filename = prepared["filename"]

    with tempfile.TemporaryDirectory(prefix="deckjob-") as tmp:
        _stage(job, "artwork", "Generating cover and section artwork locally")
        spec["artwork"] = True
        # Artwork is cached by key, so every later render reuses it; the
        # image model is then released before the reviewer needs the card.
        render.render_deck(spec, Path(tmp) / "artwork.pptx")
        try:
            from backend.tools.generation.deck import art

            art.release()
        except Exception:  # noqa: BLE001
            pass
        # The reviewer loads inside improve(); it frees the card first
        # (image model, embedding model, Ollama) via models/gpu.py.

        _stage(job, "reviewing", "Rendering and measuring every page")
        result = improve.improve(spec, Path(tmp) / "preview.pptx", vision=True,
                                 progress=lambda msg: setattr(job, "detail", msg))
        spec = result.spec
        job.quality = result.quality.to_dict()
        job.rounds = [asdict(r) for r in result.rounds]
    job._spec = spec


def request_approval(job: OutputJob) -> dict:
    """File (or re-file, after expiry) the approval for this job's final deck."""
    from backend.audit.approval_gate import ApprovalGate
    from backend.orchestrator.action_resolver import OUTPUT_DIR, deck_preview

    if job._spec is None:
        raise ValueError(f"Job {job.job_id} has nothing finished to approve ({job.status}).")
    label, tool_name, suffix = KINDS[job.kind]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = OUTPUT_DIR / f"{Path(job._filename).stem}-{stamp}{suffix}"
    titles = [t for t in job.slide_titles if t]
    unit = {"deck": "slide", "xlsx": "sheet"}.get(job.kind, "section")
    effect = (
        f'Requested: "{job.request}"\n'
        f"Effect: write a {len(titles)}-{unit} {label} to {output_path.name}, "
        f"grounded in {len(job.citations)} source reference(s)."
    )
    preview = deck_preview(output_path, titles, job.citations, [], quality=job.quality,
                           unit=unit, report=job.report)
    arguments = ({"deck_spec": job._spec, "output_path": str(output_path)} if job.kind == "deck"
                 else {**job._spec, "output_path": str(output_path)})
    req = ApprovalGate().request(tool_name=tool_name, arguments=arguments, effect=effect)
    job.approval = {
        "id": req.request_id,
        "title": f"Confirm {label}",
        "action_type": "file write",
        # The file this writes. The other approval path always sent a
        # target; this one did not, so the approval screen for a finished
        # deck or report said "Target not resolved by the system" directly
        # above the file name it was about to write.
        "target": output_path.name,
        "description": req.effect,
        "detail": job.request,
        "executable": True,
        "tool_name": tool_name,
        "preview": preview,
        "reason": "",
        "expires_at": req.expires_at,
        # What was checked, so the approval screen can show the evidence
        # rather than only a sentence about it.
        "quality": job.quality,
        "report": job.report,
        "rounds": job.rounds,
        "kind": job.kind,
    }
    _stage(job, "awaiting_approval", f"Ready: approve to write {output_path.name}")
    job.finished_at = time.time()
    return job.approval


def quality_line(quality: dict | None) -> str:
    """One line for the approval card: what was checked and what it found."""
    if not quality or quality.get("method") == "unavailable":
        return "Quality: not checked (PowerPoint is not available to render the pages)"
    pages = len(quality.get("pages") or [])
    defects = quality.get("layout_defect_pages", 0)
    layout = (f"layout measured on {pages} pages, "
              + ("no defects" if not defects else f"{defects} with defects"))
    if quality.get("score") is None:
        return f"Quality: {layout}; design not reviewed"
    reviewer = re.sub(r"^.*/", "", quality.get("reviewed_by") or "the page reviewer")
    return (f"Quality: design {quality['score']}/10 (grade {quality['grade']}) by {reviewer} "
            f"on {quality.get('pages_reviewed', 0)} pages; {layout}")


def reset_for_tests() -> None:
    with _lock:
        _jobs.clear()


__all__: list[Any] = ["OutputJob", "KINDS", "start", "get", "all_jobs", "run",
                      "request_approval", "quality_line"]
