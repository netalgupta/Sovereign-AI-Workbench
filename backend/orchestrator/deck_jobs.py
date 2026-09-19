"""Presentations as background jobs: write, illustrate, review and fix, THEN ask.

WHY A JOB. A deck worth approving takes minutes: planning and writing
with the local LLM (the larger writer for long sources), abstract artwork
from the image model, then every page rendered by PowerPoint, measured,
looked at by the page reviewer and repaired where it is weak. Holding a
chat request open for that long is not an interface. The operator starts
the job, watches its stages, and is asked to approve only a deck that has
already been reviewed -- with its quality report on the approval card.

WHAT IS WRITTEN WHERE. Nothing reaches outputs/ until the operator
approves: the job renders previews into a temporary directory to measure
and review them, and deletes it. Approval runs generate_deck with the
FINAL spec (including the review loop's pagination fixes), which renders
exactly the deck that was reviewed (hard constraint #4).

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


@dataclass
class DeckJob:
    job_id: str
    request: str
    session_id: str
    status: str = "queued"      # a STAGES entry, or "refused" | "failed"
    detail: str = ""            # what the current stage is doing, e.g. "Reviewing page 4 of 11"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    stage_times: dict[str, float] = field(default_factory=dict)
    writer: str | None = None
    slide_titles: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    quality: dict | None = None
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


_jobs: dict[str, DeckJob] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def start(request: str, session_id: str = "default") -> DeckJob:
    """Queue a deck for `request`. Returns immediately."""
    global _worker
    job = DeckJob(job_id=f"deck-{uuid.uuid4().hex[:10]}", request=request.strip(), session_id=session_id)
    with _lock:
        _jobs[job.job_id] = job
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="deck-jobs", daemon=True)
            _worker.start()
    _queue.put(job.job_id)
    return job


def get(job_id: str) -> DeckJob | None:
    return _jobs.get(job_id)


def all_jobs() -> list[DeckJob]:
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
            logger.exception("Deck job %s failed", job_id)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = job.finished_at or time.time()


def _stage(job: DeckJob, status: str, detail: str = "") -> None:
    job.status, job.detail = status, detail
    job.stage_times[status] = time.time()
    logger.info("Deck job %s: %s %s", job.job_id, status, detail)


def run(job: DeckJob) -> DeckJob:
    """Every stage, in order, on the calling thread (the worker, or a test)."""
    from backend.orchestrator.deck_agent import NotInCorpus
    from backend.orchestrator.slide_agent import prepare_deck
    from backend.tools.generation.deck import improve, render

    _stage(job, "writing", "Finding the source documents and writing the slides")
    try:
        prepared = prepare_deck(job.request, session_id=job.session_id)
    except NotInCorpus as exc:
        job.status, job.error, job.finished_at = "refused", str(exc), time.time()
        return job
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

        _stage(job, "reviewing", "Rendering and measuring every page")
        result = improve.improve(spec, Path(tmp) / "preview.pptx", vision=True,
                                 progress=lambda msg: setattr(job, "detail", msg))
        spec = result.spec
        job.quality = result.quality.to_dict()
        job.rounds = [asdict(r) for r in result.rounds]
    job._spec = spec

    request_approval(job)
    return job


def request_approval(job: DeckJob) -> dict:
    """File (or re-file, after expiry) the approval for this job's final deck."""
    from backend.audit.approval_gate import ApprovalGate
    from backend.orchestrator.action_resolver import OUTPUT_DIR, deck_preview

    if job._spec is None:
        raise ValueError(f"Job {job.job_id} has no finished deck to approve ({job.status}).")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = OUTPUT_DIR / f"{Path(job._filename).stem}-{stamp}.pptx"
    titles = [t for t in job.slide_titles if t]
    effect = (
        f'Requested: "{job.request}"\n'
        f"Effect: write a {len(titles)}-slide PowerPoint presentation to {output_path.name}, "
        f"grounded in {len(job.citations)} source reference(s)."
    )
    preview = deck_preview(output_path, titles, job.citations, [], quality=job.quality)
    req = ApprovalGate().request(
        tool_name="generate_deck",
        arguments={"deck_spec": job._spec, "output_path": str(output_path)},
        effect=effect,
    )
    job.approval = {
        "id": req.request_id,
        "title": "Confirm file write",
        "action_type": "file write",
        "description": req.effect,
        "detail": job.request,
        "executable": True,
        "tool_name": "generate_deck",
        "preview": preview,
        "reason": "",
        "expires_at": req.expires_at,
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


__all__: list[Any] = ["DeckJob", "start", "get", "all_jobs", "run", "request_approval", "quality_line"]
