"""Shared pipeline state for the API layer.

The API serves things with wildly different costs. Reading the graph
from Neo4j or listing the image store is milliseconds. Ingesting the
corpus — OCR every scan, embed every chunk — is minutes. An endpoint
that re-ingested per request would be unusable, and one that ingested at
startup would make the app take minutes to boot.

So state is built LAZILY and cached: the first request that needs the
corpus pays for it, everything after is instant, and endpoints that
don't need it never trigger it.

WHY EVERY RESPONSE DECLARES ITS PROVENANCE. Corpus data can come from
two places — a live ingestion, or a snapshot exported earlier by
backend/evaluation/export_*.py. Those can disagree: a snapshot is a
photograph of a corpus that may since have changed. Rather than hide
that behind a uniform response, every payload carries `source:
"live" | "snapshot"` and, for snapshots, when it was written. A UI
showing numbers from a stale export must be able to say so; silently
presenting yesterday's corpus as today's is the same class of mistake as
a citation pointing at a document that has since been edited.
"""

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

DEFAULT_CORPUS_DIR = "MRPL_RAG_Test_Corpus"
SNAPSHOT_PATH = Path("backend/evaluation/inspection_data.json")
IMAGE_SNAPSHOT_PATH = Path("backend/evaluation/image_data.json")
METRICS_PATHS = {
    "retrieval_metrics": Path("backend/evaluation/retrieval_metrics.json"),
    "precision_ceiling": Path("backend/evaluation/precision_ceiling_analysis.json"),
    "chart_stress": Path("backend/evaluation/chart_stress_results.json"),
    "refusal": Path("backend/evaluation/refusal_after_fix.json"),
    "boilerplate": Path("backend/evaluation/boilerplate_precision_comparison.json"),
}


class PipelineState:
    """Lazily-built, process-wide pipeline handles.

    Guarded by a lock because uvicorn serves concurrently and two
    simultaneous first-requests would otherwise both start a
    multi-minute ingestion.
    """

    def __init__(self, corpus_dir: str = DEFAULT_CORPUS_DIR):
        self.corpus_dir = corpus_dir
        self._lock = Lock()
        self._store = None
        self._chunks = None
        self._snapshot = None

    # ---- stores that are cheap to open -------------------------------

    @property
    def image_store(self):
        from backend.ingestion.image_store import ImageStore

        return ImageStore()

    @property
    def registry(self):
        from backend.ingestion.document_registry import DocumentRegistry

        return DocumentRegistry()

    @property
    def watcher(self):
        from backend.ingestion.source_watcher import SourceWatcher

        return SourceWatcher(self.registry)

    @property
    def queue(self):
        from backend.ingestion.ingestion_queue import IngestionQueue

        return IngestionQueue()

    # ---- corpus: expensive, cached -----------------------------------

    def snapshot(self) -> dict | None:
        """The exported corpus snapshot, if one exists."""
        if self._snapshot is None and SNAPSHOT_PATH.exists():
            self._snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return self._snapshot

    def snapshot_age(self) -> str | None:
        if not SNAPSHOT_PATH.exists():
            return None
        return datetime.fromtimestamp(SNAPSHOT_PATH.stat().st_mtime).isoformat(timespec="seconds")

    def ensure_corpus(self):
        """Ingest the corpus once, on demand. Returns (store, chunks).

        This is the multi-minute path. Endpoints that can answer from a
        snapshot should do so and leave this untouched.
        """
        with self._lock:
            if self._store is None:
                from backend.evaluation.ingest_corpus import ingest_corpus

                self._store, self._chunks, _stats = ingest_corpus(
                    self.corpus_dir, verbose=False
                )
        return self._store, self._chunks

    @property
    def corpus_is_loaded(self) -> bool:
        return self._store is not None

    # ---- graph --------------------------------------------------------

    def graph(self, uri="bolt://localhost:7687", user="neo4j", password="testpassword123") -> dict:
        """Live graph read. Cheap, so never cached — a graph rebuilt in
        another terminal should show up on the next refresh rather than
        requiring an API restart."""
        from backend.evaluation.export_inspection_data import export_graph

        return export_graph(uri, user, password)

    # ---- measured metrics ---------------------------------------------

    def metrics(self) -> dict:
        """Every measured result the evaluation harnesses have produced.

        Read from disk each call rather than cached: these files are
        rewritten by harness runs, and a dashboard showing a number the
        harness has already superseded is the stale-artifact bug this
        project has now hit three times.
        """
        out = {}
        for name, path in METRICS_PATHS.items():
            if not path.exists():
                out[name] = None
                continue
            try:
                out[name] = {
                    "data": json.loads(path.read_text(encoding="utf-8")),
                    "measured_at": datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(timespec="seconds"),
                }
            except json.JSONDecodeError:
                out[name] = None
        return out


_state: PipelineState | None = None


def get_state() -> PipelineState:
    global _state
    if _state is None:
        _state = PipelineState()
    return _state
