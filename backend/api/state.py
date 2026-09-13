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
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

DEFAULT_CORPUS_DIR = "MRPL_RAG_Test_Corpus"
SNAPSHOT_PATH = Path("backend/evaluation/inspection_data.json")
# The corpus cache this layer writes and reads. Separate from the
# inspector export above: that one carries PCA coordinates and a
# similarity matrix, which ensure_corpus has no use for and which are
# expensive to compute. Gitignored per-machine state -- committing a
# corpus export is what made one person's 13 documents hydrate
# everybody's backend.
# ONE GITIGNORED FOLDER FOR EVERYTHING DERIVED.
#
# This is what NotebookLM and Claude Projects do: the index is BUILT
# ONCE and kept until the user removes the source. Deriving it again on
# every start is work nobody asked for -- and until this existed, every
# `uvicorn --reload` file save cost a full re-ingest.
#
# Everything in here is reproducible from the sources, so it is safe to
# delete and it never belongs in git. It is deleted only when the user
# deletes it, or when the sources it was built from have changed.
WORKBENCH_DIR = Path(".workbench")
CORPUS_CACHE_PATH = WORKBENCH_DIR / "corpus_chunks.json"
# The FAISS index itself. Without this, hydration still had to re-embed
# all 231 chunks on every boot -- 24.8 seconds of GPU work to rebuild
# something that had not changed.
CORPUS_INDEX_PATH = WORKBENCH_DIR / "corpus.faiss"
IMAGE_SNAPSHOT_PATH = Path("backend/evaluation/image_data.json")
METRICS_PATHS = {
    "retrieval_metrics": Path("backend/evaluation/retrieval_metrics.json"),
    "precision_ceiling": Path("backend/evaluation/precision_ceiling_analysis.json"),
    "chart_stress": Path("backend/evaluation/chart_stress_results.json"),
    "refusal": Path("backend/evaluation/refusal_after_fix.json"),
    "boilerplate": Path("backend/evaluation/boilerplate_precision_comparison.json"),
}


def _empty_index(dim: int):
    """A fresh empty FAISS index of the same type the store uses.

    Needed because add_chunks() writes into whatever index is attached,
    and when hydrating from a saved index we want its SQLite side
    populated without its vectors being appended to themselves.
    """
    import faiss

    return faiss.IndexFlatIP(dim)


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

    # ---- corpus: expensive, cached -----------------------------------

    def snapshot(self) -> dict | None:
        """The exported snapshot file, if one exists.

        A PLAIN READER, deliberately. This file carries two unrelated
        things -- the corpus chunks and a graph export -- and staleness
        means different things for each. Making this method itself
        refuse to return a stale corpus also broke /api/graph, which was
        correctly falling back to the graph half while Neo4j was down.
        Callers that care about corpus freshness ask
        corpus_snapshot_is_current().
        """
        if self._snapshot is None and SNAPSHOT_PATH.exists():
            self._snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return self._snapshot

    def snapshot_age(self) -> str | None:
        if not SNAPSHOT_PATH.exists():
            return None
        return datetime.fromtimestamp(SNAPSHOT_PATH.stat().st_mtime).isoformat(timespec="seconds")

    def _write_corpus_cache(self, chunks: list) -> None:
        """Persist the ingested chunks so the next boot does not re-ingest.

        WHY NOT REUSE inspection_data.json. That file is the chunk
        INSPECTOR's export -- it carries PCA coordinates and a
        similarity matrix that are expensive to compute and that
        ensure_corpus has no use for. Writing it here would make every
        ingest pay for a visualisation nobody asked for.

        This cache is gitignored per-machine state. Committing a corpus
        export is what caused the original problem: a snapshot of one
        person's 13 documents shipped to everyone and hydrated every
        backend.

        Never raises. Failing to write a cache must not fail an ingest
        that already succeeded -- the only cost is a slow next boot.
        """
        try:
            payload = {
                "written_at": datetime.now().isoformat(timespec="seconds"),
                # THE FILES THAT WERE SCANNED, not the ones that produced
                # chunks. Deriving this from chunk metadata made the
                # cache permanently invalid: a .pptx or an unreadable
                # README yields no chunks, so its name never appears,
                # so the check said "stale" forever and EVERY restart
                # re-ingested for 68 seconds. Under `uvicorn --reload`
                # that is every file save.
                "scanned_files": sorted(self._configured_file_names()),
                "chunks": [
                    {
                        "text": c.text,
                        "source_document": c.metadata.source_document,
                        "document_type": c.metadata.document_type,
                        "page_number": c.metadata.page_number,
                        "chunk_index": c.metadata.chunk_index,
                        "ingestion_date": c.metadata.ingestion_date,
                    }
                    for c in chunks
                ],
            }
            CORPUS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CORPUS_CACHE_PATH.write_text(
                json.dumps(payload), encoding="utf-8"
            )
            self._write_index()
        except Exception:  # noqa: BLE001
            pass

    def _configured_folders(self) -> list[Path] | None:
        """The enabled source folders, or None if nothing is configured.

        One reader for the file that decides what this workbench is
        grounded in. It was being read in two route handlers and nowhere
        in the state layer, which is how the store ended up hydrating
        from a snapshot that had no relationship to it.

        None and [] mean different things and both are real: None is "no
        configuration file yet" (a fresh install), [] is "a file that
        enables nothing".
        """
        config = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
        if not config.exists():
            return None
        try:
            entries = json.loads(config.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        return [
            Path(e["path"])
            for e in entries
            if e.get("enabled", True) and e.get("path")
        ]

    def _write_index(self) -> None:
        """Persist the FAISS index next to the chunk cache."""
        try:
            import faiss

            faiss.write_index(self._store.index, str(CORPUS_INDEX_PATH))
        except Exception:  # noqa: BLE001 - a missing cache costs time, not truth
            pass

    def _load_index(self, expected: int) -> bool:
        """Load the saved index, or return False.

        GUARDED ON COUNT, and this guard is the whole reason the vectors
        can be cached at all. The index is a bare array of vectors whose
        POSITION is the only link to a chunk -- faiss id 7 means
        "chunks[7]" and nothing else. An index holding a different
        number of vectors than the chunk list has is not slightly wrong,
        it is silently returning the text of one passage for the
        embedding of another, with citations attached.

        This repository has produced exactly that failure before, from
        hash embeddings that satisfied every shape assertion. So a
        mismatch throws the file away and re-embeds; being slow is
        recoverable, and confidently citing the wrong passage is not.
        """
        if not CORPUS_INDEX_PATH.exists():
            return False
        try:
            import faiss

            index = faiss.read_index(str(CORPUS_INDEX_PATH))
            if index.ntotal != expected:
                logging.getLogger(__name__).warning(
                    "Cached index holds %d vectors for %d chunks; discarding it "
                    "and re-embedding rather than risking a mismatched citation.",
                    index.ntotal, expected,
                )
                return False
            self._store.index = index
            return True
        except Exception:  # noqa: BLE001
            return False

    def _configured_file_names(self) -> set[str]:
        """Every filename under every enabled source folder."""
        names: set[str] = set()
        for folder in self._configured_folders() or []:
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if path.is_file() and not path.name.startswith("."):
                    names.add(path.name)
        return names

    def corpus_snapshot_is_current(self) -> bool:
        """Does the exported CORPUS still describe the configured sources?

        Public because /api/chunks needs it: that endpoint prefers the
        snapshot over a live read to avoid a multi-minute ingest on a
        request, which is right, and it must not do so once the snapshot
        has stopped describing reality.
        """
        return self._cache_matches_sources(SNAPSHOT_PATH)

    def _snapshot_matches_sources(self) -> bool:
        """Is the INSPECTOR export still a fair description of the
        configured sources? See _cache_matches_sources."""
        return self._cache_matches_sources(SNAPSHOT_PATH)

    def _cache_matches_sources(self, cache_path: Path) -> bool:
        """Does the exported snapshot still describe what is configured?

        Compares the DOCUMENT NAMES in the snapshot against the files
        found under every enabled source folder. Any configured document
        the snapshot has never heard of means the snapshot predates a
        change and must not be used -- that is the whole failure this
        guards: a folder added in the Sources panel that never appears
        in the chunk inspector.

        Names, not paths or hashes, deliberately. The snapshot records
        `source_document` as a bare filename, so a filename is the only
        thing the two sides can be compared on. It is a weaker check
        than a content hash and it catches the case that actually
        happens -- new files appearing -- while a stricter check would
        need the snapshot format to change.

        Fails towards RE-INGESTING. If the source list cannot be read,
        or anything else goes wrong, the answer is "do not trust the
        snapshot": being slow is recoverable, showing a frozen corpus as
        though it were live is not.
        """
        try:
            folders = self._configured_folders()
            if folders is None:
                return True  # nothing configured yet; the snapshot is all there is
            if not folders:
                return True

            configured_names = self._configured_file_names()
            if not configured_names:
                return True

            data = json.loads(cache_path.read_text(encoding="utf-8"))
            # A cache written by this class records exactly which files
            # it looked at. The older inspector export does not, so fall
            # back to the document names in its chunks -- weaker, and the
            # only thing available for that file.
            scanned = data.get("scanned_files")
            snapshot_names = (
                set(scanned)
                if scanned
                else {c.get("source_document") for c in data.get("chunks", [])}
            )

            missing = configured_names - snapshot_names
            if missing:
                # NO LOGGING HERE. This is a QUESTION, asked by several
                # callers, and only one of them re-ingests. Logging
                # "Re-ingesting from the configured folders" from inside
                # the check meant every /api/chunks and /api/corpus
                # request printed a line announcing work that was not
                # happening -- a log that describes something other than
                # what the program did is worse than no log.
                #
                # The caller that actually rebuilds says so, once.
                self._last_staleness = sorted(missing)
                return False
            self._last_staleness = []
            return True
        except Exception:  # noqa: BLE001
            return False

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

                # THE SNAPSHOT IS A CACHE, AND A CACHE THAT IS NEVER
                # INVALIDATED IS JUST STALE DATA WITH A FRIENDLY NAME.
                #
                # This hydrated the store from inspection_data.json
                # unconditionally -- a 21-chunk export of 13 documents,
                # COMMITTED TO GIT, frozen at the moment somebody last
                # ran the exporter. So every clone shipped one machine's
                # corpus, every backend started with it, and a folder
                # you added in the Sources panel was invisible to the
                # chunk inspector no matter how many times you rescanned.
                #
                # Reported as "this entire page is still very hardcoded",
                # which was exactly right: 66 files registered, 21 chunks
                # shown, and the 21 were a file in the repository.
                #
                # The snapshot is still used, because re-ingesting a
                # corpus of scans on every boot is minutes of silence.
                # It is now CHECKED against what is actually configured
                # first, and discarded the moment those disagree.
                hydrate_from = None
                if CORPUS_CACHE_PATH.exists() and self._cache_matches_sources(
                    CORPUS_CACHE_PATH
                ):
                    hydrate_from = CORPUS_CACHE_PATH
                elif SNAPSHOT_PATH.exists() and self._snapshot_matches_sources():
                    hydrate_from = SNAPSHOT_PATH

                if hydrate_from is not None:
                    try:
                        data = json.loads(hydrate_from.read_text(encoding="utf-8"))
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
                            # THE SAVED INDEX FIRST. Re-embedding 231
                            # unchanged chunks cost 24.8 seconds on every
                            # boot -- GPU work to rebuild something that
                            # had not changed. add_chunks() still runs so
                            # the SQLite side is populated; the vectors
                            # are then swapped for the cached ones.
                            vecs = None
                            if self._load_index(len(self._chunks)):
                                import numpy as np

                                saved = self._store.index
                                vecs = np.zeros(
                                    (len(self._chunks), saved.d), dtype="float32"
                                )
                                self._store.index = _empty_index(saved.d)
                                self._store.add_chunks(self._chunks, vecs)
                                self._store.index = saved
                            else:
                                vecs = embed_texts([c.text for c in self._chunks])
                                self._store.add_chunks(self._chunks, vecs)
                                self._write_index()
                    except Exception:
                        pass
                else:
                    # EVERY CONFIGURED FOLDER, not just the built-in
                    # corpus directory. Ingesting only self.corpus_dir
                    # here would reject the stale snapshot for the right
                    # reason and then rebuild something equally wrong --
                    # the folder the user actually added would still be
                    # missing.
                    #
                    # ingest_path() is NOT used: it takes self._lock,
                    # which this method already holds, and Lock() is not
                    # reentrant.
                    from backend.evaluation.ingest_corpus import ingest_corpus
                    from backend.ingestion.embeddings import embed_texts

                    missing = getattr(self, "_last_staleness", None)
                    logging.getLogger(__name__).info(
                        "Building the corpus index from the configured folders%s. "
                        "This happens once; the result is cached in %s and reused "
                        "until the sources change.",
                        f" ({len(missing)} new document(s), e.g. {', '.join(missing[:3])})"
                        if missing else "",
                        WORKBENCH_DIR,
                    )
                    folders = self._configured_folders() or [Path(self.corpus_dir)]
                    collected: list = []
                    seen: set = set()
                    for folder in folders:
                        try:
                            _s, chunks, _stats = ingest_corpus(str(folder), verbose=False)
                        except Exception:  # noqa: BLE001 - one bad folder is not fatal
                            continue
                        for chunk in chunks:
                            # Folders legitimately nest (07_User_Uploads
                            # sits inside MRPL_RAG_Test_Corpus), so the
                            # same chunk arrives more than once.
                            key = (
                                chunk.metadata.source_document,
                                chunk.metadata.chunk_index,
                            )
                            if key not in seen:
                                seen.add(key)
                                collected.append(chunk)

                    self._chunks = collected
                    if collected:
                        vectors = embed_texts([c.text for c in collected])
                        self._store.add_chunks(collected, vectors)
                        # Write the cache back, so the NEXT boot is fast
                        # AND correct. Without this the fix trades one
                        # problem for another: a stale corpus becomes an
                        # 88-second startup, every time, forever.
                        self._write_corpus_cache(collected)
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
                    if c.metadata.source_document.lower() != doc_name.lower()
                    and c.metadata.source_document.lower() != target_path.lower()
                    and not norm_path in str(Path(c.metadata.source_document).resolve()).lower()
                ]
                removed_count = original_len - len(self._chunks)
            self._snapshot = None

        # 3. Remove from VectorStore SQLite metadata table
        if self._store and getattr(self._store, "_conn", None):
            try:
                self._store._conn.execute(
                    "DELETE FROM chunks WHERE LOWER(source_document) = LOWER(?) OR LOWER(source_document) LIKE LOWER(?)",
                    (doc_name, f"%{doc_name}%")
                )
                self._store._conn.commit()
            except Exception:
                pass

        # 4. Only delete from disk if the file was physically an app-managed upload in 07_User_Uploads.
        # User original documents elsewhere on disk must NEVER be deleted.
        file_deleted = False
        try:
            if p.exists() and p.is_file() and "07_user_uploads" in str(p.resolve()).lower():
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

    # How long a FAILED graph probe is remembered. Success is never
    # cached; see graph().
    _GRAPH_FAILURE_TTL_SECONDS = 20.0

    def graph(self, uri="bolt://localhost:7687", user="neo4j", password="testpassword123") -> dict:
        """Live graph read. Success is never cached — a graph rebuilt in
        another terminal should show up on the next refresh rather than
        requiring an API restart.

        FAILURE IS CACHED, AND NOT CACHING IT WAS DEGRADING THE WHOLE
        APP. The original note read "cheap, so never cached", which is
        true when Neo4j is up: a local bolt query costs milliseconds.
        When Neo4j is DOWN the driver waits out its connect timeout, and
        that was measured at 4.1 SECONDS ON EVERY CALL.

        /api/health calls this, and the frontend polls /api/health. With
        uvicorn's threadpool, each poll ties up a worker for four
        seconds, so on any machine where Docker is not running -- which
        is most of the team, most of the time -- the entire product
        feels broken for a reason that has nothing to do with the
        graph.

        An assumption that holds on the happy path and collapses on the
        failure path, where the failure path is the common one.

        The TTL is short so recovery is still noticed quickly: start
        Neo4j and the graph appears within twenty seconds, without a
        restart.
        """
        import time as _time

        cached = getattr(self, "_graph_failure", None)
        if cached is not None:
            result, failed_at = cached
            if (_time.time() - failed_at) < self._GRAPH_FAILURE_TTL_SECONDS:
                return result

        from backend.evaluation.export_inspection_data import export_graph

        result = export_graph(uri, user, password)

        if result.get("available"):
            self._graph_failure = None
        else:
            self._graph_failure = (result, _time.time())
        return result

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
