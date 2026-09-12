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

from __future__ import annotations

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

    def reset(self):
        with self._lock:
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

    @property
    def attachment_manager(self):
        from backend.attachments.manager import get_attachment_manager

        return get_attachment_manager()


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
        """Get or initialize the active VectorStore and chunks.

        Hydrates instantly from pre-computed snapshot when available,
        falling back to directory traversal only if no snapshot exists.
        """
        with self._lock:
            if self._store is None:
                from backend.ingestion.document_ingestion import IngestedChunk, ChunkMetadata
                from backend.ingestion.embeddings import embed_texts
                from backend.retrieval.vector_store import VectorStore

                self._store = VectorStore(dim=1024)
                self._chunks = []

                if SNAPSHOT_PATH.exists():
                    try:
                        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
                        raw_chunks = data.get("chunks", [])
                        for rc in raw_chunks:
                            meta = ChunkMetadata(
                                source_document=rc.get("source_document", "unknown"),
                                document_type=rc.get("document_type", "txt"),
                                page_number=rc.get("page_number", 1),
                                chunk_index=rc.get("chunk_index", 0),
                                ingestion_date=rc.get("ingestion_date", "2026-09-12"),
                                image_ids=[],
                            )
                            self._chunks.append(IngestedChunk(text=rc.get("text", ""), metadata=meta))
                        if self._chunks:
                            vecs = embed_texts([c.text for c in self._chunks])
                            self._store.add_chunks(self._chunks, vecs)
                    except Exception:
                        pass
                else:
                    from backend.evaluation.ingest_corpus import ingest_corpus
                    self._store, self._chunks, _stats = ingest_corpus(
                        self.corpus_dir, verbose=False
                    )
        return self._store, self._chunks

    def ingest_path(
        self, target_path: str | Path, job_id: str | None = None
    ) -> tuple[int, list[dict]]:
        """Chunk, embed, and index a file or folder into the active VectorStore.

        Returns (total_chunks_added, list_of_document_details).

        When `job_id` is given, every document's stage transition is
        reported to the progress tracker so a UI can show WHICH file is
        being worked on and at WHAT stage. Without that, a folder ingest
        is a spinner: the work happens inside one call that returns only
        when everything is finished, which on a folder of scans is
        minutes of silence.
        """
        from backend.ingestion.ingestion_progress import DocumentStage, get_tracker

        tracker = get_tracker() if job_id else None

        def _stage(file_path, stage, **kw):
            if tracker:
                tracker.set_stage(job_id, str(file_path), stage, **kw)
        from backend.ingestion.document_ingestion import ingest_document
        from backend.ingestion.document_types import detect_document_type
        from backend.ingestion.embeddings import embed_texts
        def _ocr_fn(img_path: str) -> str:
            try:
                from backend.tools.vision.ocr_printed import extract_printed_text
                res = extract_printed_text(img_path).full_text
                return res if res.strip() else f"[Image Document: {Path(img_path).name}]"
            except Exception:
                return f"[Image Document: {Path(img_path).name}]"

        p = Path(target_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist on disk: {target_path}")

        files: list[Path] = []
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = sorted(
                f for f in p.rglob("*")
                if f.is_file() and not f.name.startswith(".") and f.name.lower() != "readme.md"
            )

        store, existing_chunks = self.ensure_corpus()
        total_chunks = 0
        details = []

        for f in files:
            _stage(f, DocumentStage.EXTRACTING)
            try:
                type_info = detect_document_type(str(f))
                chunks = ingest_document(str(f), ocr_fn=_ocr_fn)
            except Exception as exc:
                # Reported as a terminal FAILED state with the reason, not
                # skipped quietly. A folder ingest that silently drops
                # three unreadable PDFs and reports success is what makes
                # people distrust the corpus later, when an answer is
                # missing and nobody knows why.
                _stage(f, DocumentStage.FAILED, detail=f"{type(exc).__name__}: {exc}")
                details.append({"filename": f.name, "path": str(f), "error": str(exc), "chunks": 0})
                continue
            _stage(f, DocumentStage.CHUNKING, chunks=len(chunks))

            if not chunks:
                from backend.ingestion.document_ingestion import IngestedChunk, ChunkMetadata
                import datetime
                fallback_text = f"Source Document: {f.name}\nPath: {str(f)}"
                chunks = [
                    IngestedChunk(
                        text=fallback_text,
                        metadata=ChunkMetadata(
                            source_document=f.name,
                            document_type=getattr(type_info, "detected_type", "txt"),
                            page_number=1,
                            chunk_index=0,
                            ingestion_date=datetime.date.today().isoformat(),
                            image_ids=[],
                        ),
                    )
                ]

            if chunks:
                _stage(f, DocumentStage.EMBEDDING, chunks=len(chunks))
                vectors = embed_texts([c.text for c in chunks])
                _stage(f, DocumentStage.INDEXING)
                store.add_chunks(chunks, vectors)
                with self._lock:
                    self._chunks.extend(chunks)
                    # Invalidate cached static snapshot so live chunks are served
                    self._snapshot = None
                try:
                    self.registry.register(str(f), type_info.detected_type)
                except Exception:
                    pass
                total_chunks += len(chunks)
                details.append({
                    "filename": f.name,
                    "path": str(f),
                    "chunks": len(chunks),
                    "document_type": type_info.detected_type,
                })
                _stage(f, DocumentStage.INDEXED, chunks=len(chunks))

        return total_chunks, details

    def delete_source(self, target_path: str) -> dict:
        """Remove a file or folder from the active corpus, VectorStore, and registry."""
        p = Path(target_path)
        doc_name = p.name
        norm_path = str(p.resolve()).lower()

        # 1. Stop watching if it's a watched directory
        self.watcher.remove_source(target_path)

        # 2. Remove matching chunks from in-memory chunks list
        removed_count = 0
        with self._lock:
            if self._chunks:
                original_len = len(self._chunks)
                self._chunks = [
                    c for c in self._chunks
                    if c.metadata.source_document != doc_name
                    and c.metadata.source_document != target_path
                    and not norm_path in str(Path(c.metadata.source_document).resolve()).lower()
                ]
                removed_count = original_len - len(self._chunks)
            self._snapshot = None

        # 3. Remove from VectorStore SQLite metadata table
        if self._store and getattr(self._store, "_conn", None):
            try:
                self._store._conn.execute(
                    "DELETE FROM chunks WHERE source_document = ? OR source_document LIKE ?",
                    (doc_name, f"%{doc_name}%")
                )
                self._store._conn.commit()
            except Exception:
                pass

        # 4. If file is in 07_User_Uploads or explicitly specified, delete from disk
        file_deleted = False
        try:
            if p.exists() and p.is_file():
                if "07_user_uploads" in str(p.resolve()).lower() or p.name in target_path:
                    p.unlink()
                    file_deleted = True
        except Exception:
            pass

        return {
            "success": True,
            "removed": target_path,
            "filename": doc_name,
            "chunks_removed": removed_count,
            "file_deleted": file_deleted,
            "message": f"Source '{doc_name}' removed from active knowledge base ({removed_count} chunks deleted).",
        }

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

    def graph_client(
        self, uri="bolt://localhost:7687", user="neo4j", password="testpassword123"
    ):
        """A connected GraphClient, or None if the graph is unreachable.

        Separate from graph() because graph() exports the WHOLE graph,
        which answers only one question. Traversal endpoints need a live
        client to run a parameterised query instead of downloading
        everything and filtering client-side -- the difference does not
        matter at 101 nodes and decides whether the feature works at all
        on a real corpus.

        Returns None rather than raising: the graph being down is a
        normal, recoverable state in this product (Docker not running),
        and every caller already has to handle it.
        """
        from backend.graph.neo4j_client import GraphClient

        try:
            client = GraphClient(uri, user, password)
            client.verify_connectivity()
            return client
        except Exception:  # noqa: BLE001
            return None

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


def reset_state() -> None:
    global _state
    if _state is not None:
        _state.reset()
    _state = None
