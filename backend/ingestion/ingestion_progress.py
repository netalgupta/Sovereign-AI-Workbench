"""Live, per-document ingestion progress.

THE PROBLEM THIS SOLVES. Ingesting a folder ran entirely inside one HTTP
request: the browser sent a path and waited, with a spinner reading
"chunking document(s) & generating embeddings", until every file was
done. On a folder of scans that is minutes with no signal — no idea
which document is being worked on, how many remain, whether one failed,
or whether anything is happening at all. A progress bar that cannot
report progress is just a spinner with extra words.

WHAT "PROGRESS" HAS TO MEAN HERE. Not a percentage. The work per
document varies by two orders of magnitude — a 2KB text file is
milliseconds, a scanned 40-page PDF is minutes of OCR — so "7 of 20
files" is a misleading fraction. What a person actually needs to know
is: which document is being processed RIGHT NOW, what stage it is at,
what has finished, and what failed and why. So this tracks STAGES per
document, and reports counts rather than a synthetic percentage.

WHY FAILURES ARE FIRST-CLASS. A folder ingest that silently skips three
unreadable PDFs and reports success is the failure mode that makes
people distrust the whole corpus later, when an answer is missing and
nobody knows why. Every document ends in a terminal state that is
recorded and shown, including the reason.

Thread-safe because ingestion runs on a worker thread while the API
serves status reads concurrently.
"""

import threading
import time
import uuid
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class DocumentStage(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"  # reading the file; OCR/ASR happens here
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    # Terminal states
    INDEXED = "indexed"
    FAILED = "failed"
    SKIPPED = "skipped"  # not an ingestible type, or unchanged since last run


TERMINAL_STAGES = {DocumentStage.INDEXED, DocumentStage.FAILED, DocumentStage.SKIPPED}


class DocumentProgress(BaseModel):
    path: str
    name: str
    suffix: str
    byte_size: int = 0
    stage: DocumentStage = DocumentStage.QUEUED
    chunks: int = 0
    pages: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    # The reason, in words a user can act on — not a traceback. A
    # failure nobody can interpret is the same as a silent skip.
    detail: str | None = None

    @property
    def seconds(self) -> float | None:
        if self.started_at is None:
            return None
        return round((self.finished_at or time.time()) - self.started_at, 2)


class JobState(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"  # the job itself could not run, not a per-document failure


class IngestionJob(BaseModel):
    job_id: str
    root_path: str
    state: JobState = JobState.RUNNING
    started_at: float = Field(default_factory=time.time)
    finished_at: float | None = None
    documents: list[DocumentProgress] = Field(default_factory=list)
    error: str | None = None

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for doc in self.documents:
            counts[doc.stage.value] = counts.get(doc.stage.value, 0) + 1

        done = sum(1 for d in self.documents if d.stage in TERMINAL_STAGES)
        current = next(
            (d for d in self.documents if d.stage not in TERMINAL_STAGES
             and d.stage is not DocumentStage.QUEUED),
            None,
        )
        # Never leave current_document null while a job is running with unfinished docs
        if current is None and self.state == JobState.RUNNING:
            current = next(
                (d for d in self.documents if d.stage not in TERMINAL_STAGES),
                None,
            )
        elapsed = (self.finished_at or time.time()) - self.started_at

        # An ETA from the documents that have ACTUALLY FINISHED, not from
        # a file count. Per-document cost spans orders of magnitude — a
        # 2KB text file is milliseconds, a scanned page is tens of
        # seconds of OCR — so "7 of 20 files" is a fraction that looks
        # precise and misleads. Measured on a real chart folder: 37.2s
        # for the first scan, 16.1s for the second.
        #
        # Averaging only completed documents means the estimate starts
        # absent and sharpens as evidence arrives, rather than being
        # confidently wrong from the first tick. Reported as an estimate
        # and never as a percentage.
        finished = [d for d in self.documents if d.stage in TERMINAL_STAGES and d.seconds]
        eta = None
        if finished and done < len(self.documents):
            eta = round((sum(d.seconds for d in finished) / len(finished))
                        * (len(self.documents) - done))

        return {
            "estimated_remaining_seconds": eta,
            "average_seconds_per_document": (
                round(sum(d.seconds for d in finished) / len(finished), 1) if finished else None
            ),
            "job_id": self.job_id,
            "root_path": self.root_path,
            "state": self.state.value,
            "elapsed_seconds": round(elapsed, 1),
            "total_documents": len(self.documents),
            "completed": done,
            "remaining": len(self.documents) - done,
            "counts_by_stage": counts,
            "total_chunks": sum(d.chunks for d in self.documents),
            "current_document": (
                {"name": current.name, "stage": current.stage.value,
                 "seconds": current.seconds}
                if current else None
            ),
            "failures": [
                {"name": d.name, "path": d.path, "detail": d.detail}
                for d in self.documents if d.stage is DocumentStage.FAILED
            ],
            "error": self.error,
        }


class ProgressTracker:
    """Process-wide registry of ingestion jobs.

    Jobs are kept after completion so a UI that polls slowly, or a user
    who opens the panel afterwards, can still see what happened — a
    result that vanishes the moment it finishes cannot be read.
    """

    # Enough to cover a working session without growing without bound.
    MAX_RETAINED_JOBS = 20

    def __init__(self) -> None:
        self._jobs: dict[str, IngestionJob] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def create(self, root_path: str, files: list[Path], job_id: str | None = None) -> IngestionJob:
        jid = job_id or f"job-{uuid.uuid4().hex[:10]}"
        job = IngestionJob(
            job_id=jid,
            root_path=str(root_path),
            documents=[
                DocumentProgress(
                    path=str(f),
                    name=f.name,
                    suffix=f.suffix.lower(),
                    byte_size=f.stat().st_size if f.exists() else 0,
                )
                for f in files
            ],
        )
        if job.documents:
            job.documents[0].stage = DocumentStage.EXTRACTING
            job.documents[0].started_at = time.time()
        with self._lock:
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            while len(self._order) > self.MAX_RETAINED_JOBS:
                self._jobs.pop(self._order.pop(0), None)
        return job

    def get(self, job_id: str) -> IngestionJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 10) -> list[IngestionJob]:
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order[-limit:]) if i in self._jobs]

    def set_stage(
        self,
        job_id: str,
        path: str,
        stage: DocumentStage,
        chunks: int | None = None,
        pages: int | None = None,
        detail: str | None = None,
    ) -> None:
        """Record a document reaching a stage.

        Timing is stamped here rather than by the caller so every
        document is measured the same way — a per-document duration that
        some code paths forget to set is worse than none, because the
        gaps look like instant successes.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            # Exact match first, then the same path spelled differently
            # (case, separators, relative vs absolute) -- string
            # normalisation, NOT Path.resolve(). Resolving every document
            # on every stage change is a filesystem call per document per
            # transition, O(n²) for a folder, all while holding the lock
            # the 450ms progress poll needs.
            #
            # Never by bare filename: two README.md files in different
            # folders are different documents, and matching on the name
            # marked the wrong one done.
            target_norm = _norm(path)
            for doc in job.documents:
                if doc.path != path and _norm(doc.path) != target_norm:
                    continue
                if doc.started_at is None and stage is not DocumentStage.QUEUED:
                    doc.started_at = time.time()
                doc.stage = stage
                if chunks is not None:
                    doc.chunks = chunks
                if pages is not None:
                    doc.pages = pages
                if detail is not None:
                    doc.detail = detail
                if stage in TERMINAL_STAGES:
                    doc.finished_at = time.time()
                break

    def finish(self, job_id: str, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.finished_at = time.time()
            job.state = JobState.FAILED if error else JobState.COMPLETE
            job.error = error
            # Anything still mid-flight when the job ends did not finish.
            # Leaving it showing "embedding" forever would read as work
            # still in progress on a job that is over.
            for doc in job.documents:
                if doc.stage not in TERMINAL_STAGES:
                    doc.stage = DocumentStage.FAILED
                    doc.detail = doc.detail or "Ingestion stopped before this document finished."
                    doc.finished_at = time.time()


def _norm(path: str | None) -> str:
    import os

    return os.path.normcase(os.path.abspath(path)) if path else ""


_tracker: ProgressTracker | None = None


def get_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker
