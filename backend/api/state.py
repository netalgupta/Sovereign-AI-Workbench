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


def _path_key(path) -> str:
    import os

    return os.path.normcase(os.path.abspath(str(path)))


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
        # ONE INGEST AT A TIME, across every entry point. Two overlapping
        # ingests of the same folder each saw the file as "not indexed
        # yet" and both added it: MEASURED 6,797 chunks for 3,523
        # distinct passages after adding one 195-file folder, so every
        # search result arrived twice. Held for a whole ingest, never by
        # a read, so it cannot stall a page load.
        self._ingest_lock = Lock()
        # filename -> the paths indexed under it. The store records only
        # the bare filename, and skipping on that alone skipped a
        # DIFFERENT file that happened to share a name with an indexed one.
        # Persisted with the corpus cache.
        self._indexed_paths: dict[str, set[str]] = {}
        self._store = None
        self._chunks = None
        self._snapshot = None
        self._cached_chunks = None
        # The background job indexing files the cache has not seen, if
        # one is running. Exposed so the UI can show it rather than a
        # corpus that silently lacks a folder.
        self.catch_up_job_id: str | None = None

    def reset(self):
        with self._lock:
            self._store = None
            self._chunks = None
            self._snapshot = None
            self._cached_chunks = None

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
                "indexed_paths": {n: sorted(p) for n, p in self._indexed_paths.items()},
                "chunks": [
                    {
                        "text": c.text,
                        "source_document": c.metadata.source_document,
                        "document_type": c.metadata.document_type,
                        "page_number": c.metadata.page_number,
                        "chunk_index": c.metadata.chunk_index,
                        "ingestion_date": c.metadata.ingestion_date,
                        # Preserve image references so a cached chunk can
                        # still hand back the pictures from its page.
                        "image_ids": list(c.metadata.image_ids or []),
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
        """Every filename under every enabled source folder, plus any
        individual file sources.

        configured_sources.json may contain both directory entries and
        single-file entries. Previously this method called rglob("*") on
        every entry unconditionally — when the entry is a file (not a
        directory) rglob returns nothing, the file name never appeared in
        scanned_files, and the staleness check returned True on every boot,
        triggering a full re-ingest every server start.
        """
        names: set[str] = set()
        for entry in self._configured_folders() or []:
            if not entry.exists():
                continue
            if entry.is_file():
                # Single-file source entry — include it directly
                if not entry.name.startswith("."):
                    names.add(entry.name)
            elif entry.is_dir():
                for path in entry.rglob("*"):
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
                #
                # A STALE CACHE IS STILL LOADED, then caught up in the
                # background. Its chunks are real and still searchable;
                # only the files it has never seen are missing, and those
                # are indexed by a tracked job (see _schedule_catch_up)
                # rather than inside this lock. Ingesting them HERE held
                # the lock for the whole ingest, so every page that
                # touched the corpus hung behind it -- and the files were
                # then ingested a second time by the request that added
                # them.
                #
                # The committed inspector snapshot is only trusted while
                # it matches; it describes one machine's 13 documents.
                hydrate_from = None
                if CORPUS_CACHE_PATH.exists():
                    hydrate_from = CORPUS_CACHE_PATH
                    self._cache_matches_sources(CORPUS_CACHE_PATH)
                elif SNAPSHOT_PATH.exists() and self._snapshot_matches_sources():
                    hydrate_from = SNAPSHOT_PATH

                if hydrate_from is not None:
                    try:
                        data = json.loads(hydrate_from.read_text(encoding="utf-8"))
                        raw_chunks = data.get("chunks", [])
                        self._indexed_paths = {
                            n: set(p) for n, p in (data.get("indexed_paths") or {}).items()
                        }
                        for rc in raw_chunks:
                            meta = ChunkMetadata(
                                source_document=rc.get("source_document", "unknown"),
                                document_type=rc.get("document_type", "txt"),
                                page_number=rc.get("page_number", 1),
                                chunk_index=rc.get("chunk_index", 0),
                                ingestion_date=rc.get("ingestion_date", "2026-09-12"),
                                # Restore image_ids persisted by _write_corpus_cache.
                                image_ids=list(rc.get("image_ids") or []),
                            )
                            self._chunks.append(IngestedChunk(text=rc.get("text", ""), metadata=meta))
                        if self._chunks:
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
                    except Exception:  # noqa: BLE001
                        logging.getLogger(__name__).exception(
                            "Could not hydrate the corpus from %s; files will be "
                            "re-indexed in the background.", hydrate_from,
                        )
                    missing = list(getattr(self, "_last_staleness", None) or [])
                    if missing:
                        # Scheduled after the lock is released: see the
                        # thread body, which re-enters ensure_corpus.
                        self._pending_catch_up = missing
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
        pending = getattr(self, "_pending_catch_up", None)
        if pending:
            self._pending_catch_up = None
            self._schedule_catch_up(pending)
        return self._store, self._chunks

    def _schedule_catch_up(self, missing_names: list[str]) -> str | None:
        """Index configured files the cache has never seen, in the
        background, as a tracked job.

        Tracked, not silent: the UI polls /api/ingestion like any other
        add, so a folder that is still being indexed says so instead of
        looking like a corpus that is missing it.
        """
        import threading

        from backend.ingestion.ingestion_progress import get_tracker

        # Files an ingest in flight has already claimed are its job, not
        # this one's; taking them would show the user's add stuck at 0
        # while a second job does its work.
        wanted = set(missing_names) - set(getattr(self, "_ingesting_names", None) or ())
        files: list[Path] = []
        seen: set[str] = set()
        for entry in self._configured_folders() or []:
            if not entry.exists():
                continue
            candidates = [entry] if entry.is_file() else entry.rglob("*")
            for cand in candidates:
                if (
                    cand.is_file()
                    and cand.name in wanted
                    and cand.name not in seen
                    and not cand.name.startswith(".")
                ):
                    seen.add(cand.name)
                    files.append(cand)
        if not files:
            return None

        tracker = get_tracker()
        job = tracker.create("configured sources (catch-up)", files)
        self.catch_up_job_id = job.job_id
        logging.getLogger(__name__).info(
            "Indexing %d file(s) the corpus cache has not seen, in the background "
            "(job %s).", len(files), job.job_id,
        )

        def _run():
            try:
                self.ingest_files(files, job_id=job.job_id)
                tracker.finish(job.job_id)
            except Exception as exc:  # noqa: BLE001 - recorded on the job
                tracker.finish(job.job_id, error=f"{type(exc).__name__}: {exc}")

        threading.Thread(target=_run, name=f"corpus-catch-up-{job.job_id}", daemon=True).start()
        return job.job_id

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
        p = Path(target_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist on disk: {target_path}")

        files: list[Path] = []
        if p.is_file():
            files = [p]
        elif p.is_dir():
            ignored_dirs = {
                ".git", ".venv", "venv", "node_modules", "__pycache__",
                ".idea", ".vscode", "dist", "build", ".next", ".cache"
            }

            def _is_safe_doc(candidate: Path) -> bool:
                if not candidate.is_file() or candidate.name.startswith("."):
                    return False
                try:
                    rel_parts = candidate.relative_to(p).parts[:-1]
                    for part in rel_parts:
                        if part.startswith(".") or part.lower() in ignored_dirs:
                            return False
                except Exception:
                    pass
                return True

            files = sorted(f for f in p.rglob("*") if _is_safe_doc(f))

        return self.ingest_files(files, job_id=job_id, label=Path(target_path).name)

    @staticmethod
    def _already_indexed(f: Path, indexed_names: set, indexed_paths: dict) -> bool:
        """Is THIS file already in the index?

        By path where the path is known. A name indexed only from an older
        cache that did not record paths is treated as this file: skipping
        a same-named file is recoverable, and a duplicated corpus is the
        bug this exists to prevent.
        """
        if f.name not in indexed_names:
            return False
        known = indexed_paths.get(f.name)
        return not known or _path_key(f) in known

    def ingest_files(
        self, files: list[Path], job_id: str | None = None, label: str = "files"
    ) -> tuple[int, list[dict]]:
        """Index these files. THE ONE PLACE INGESTION HAPPENS.

        Every route that adds sources, and the background catch-up,
        comes through here, so two rules hold for all of them:

          * one ingest at a time (self._ingest_lock), and
          * a file already in the index is SKIPPED, not appended again.

        Identity is the bare filename because that is what the store
        records as source_document; the store cannot tell two same-named
        files apart either, so a stricter check here would not help.
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
            """The page's printed text, or "" when there is none to read.

            THIS USED TO RETURN A PLACEHOLDER, "[Image Document: tmpXXXX.png]",
            for a page with no text AND for a page whose OCR raised -- and the
            placeholder was indexed as that page's content. MEASURED on a
            593-page scanned book whose last 156 pages are blank: 156 chunks
            of "[Image Document: tmp….png]" in the index, and an ingest that
            reported success. A blank page now adds nothing, and an OCR
            failure is logged with its cause instead of disappearing into a
            string that looks like text.
            """
            try:
                from backend.tools.vision.ocr_printed import extract_printed_text

                return extract_printed_text(img_path).full_text or ""
            except Exception as exc:  # noqa: BLE001 - logged, never indexed as content
                logger.warning("OCR failed on %s: %s: %s", Path(img_path).name, type(exc).__name__, exc)
                return ""

        newly_ingested: list = []

        with self._ingest_lock:
            # Claimed BEFORE ensure_corpus, so a stale-cache catch-up it
            # schedules leaves these files to this call instead of racing
            # it for them.
            self._ingesting_names = {f.name for f in files}
            try:
                store, existing_chunks = self.ensure_corpus()
                with self._lock:
                    indexed_names = {c.metadata.source_document for c in (self._chunks or [])}
                indexed_paths = self._indexed_paths

                total_chunks = 0
                details = []

                for f in files:
                    if self._already_indexed(f, indexed_names, indexed_paths):
                        # Already searchable. Indexing it again does not refresh
                        # it, it DUPLICATES it: the store appends, so every
                        # passage would come back twice in every search.
                        _stage(f, DocumentStage.SKIPPED, detail="already indexed")
                        details.append({"filename": f.name, "path": str(f), "chunks": 0, "skipped": "already indexed"})
                        continue
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
                            self._cached_chunks = None
                            indexed_names.add(f.name)
                            indexed_paths.setdefault(f.name, set()).add(_path_key(f))
                        # register() only takes file_path — the second arg (document_type)
                        # was causing a silent TypeError on every successful ingest, meaning
                        # nothing was ever recorded in the registry.
                        try:
                            self.registry.register(str(f))
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
                        newly_ingested.extend(chunks)

                # THE GRAPH FOLLOWS THE CORPUS NOW.
                #
                # Adding a source used to update the chunk index and leave the
                # graph exactly as it was, because entity extraction only ever
                # ran by hand. With 63 documents loaded the graph still described
                # the 13 somebody extracted weeks earlier -- real data, correctly
                # stored, silently covering a fraction of what every other tab
                # showed.
                #
                # Scheduled rather than awaited: extraction is one model call per
                # chunk (10-25s each), so doing it inline would hold this request
                # open for the better part of an hour. Ingestion returns as soon
                # as the documents are SEARCHABLE, which is what the user is
                # waiting for, and the graph catches up behind it.
                #
                # Cannot fail this call: see backend/graph/auto_extract.py.
                if newly_ingested:
                    try:
                        from backend.graph import auto_extract

                        auto_extract.schedule(newly_ingested, reason=f"ingest of {label}")
                    except Exception:  # noqa: BLE001
                        pass

                # PERSIST the updated store so the next boot loads from cache.
                #
                # ingest_path() extended self._chunks and added vectors to
                # self._store, but _write_corpus_cache() was never called here --
                # so a server restart (uvicorn --reload on any file save) would
                # re-check the cache, find newly added documents missing from
                # scanned_files, declare it stale, and trigger a full re-ingest.
                # Writing the cache immediately after each successful ingest
                # means the next boot is always fast.
                if newly_ingested and self._chunks:
                    # Snapshot the chunk list UNDER the lock so a concurrent ingest
                    # that extends self._chunks between the lock release and the disk
                    # write does not produce a partially-modified cache file.
                    with self._lock:
                        chunks_snapshot = list(self._chunks)
                    try:
                        self._write_corpus_cache(chunks_snapshot)
                    except Exception:  # noqa: BLE001 - a failed cache write costs time, not correctness
                        pass

                return total_chunks, details
            finally:
                self._ingesting_names = set()


    def _remove_chunks(self, drop) -> int:
        """Remove every chunk `drop(chunk)` is true for, and persist that.

        The store is rebuilt from the kept chunks and their EXISTING vectors
        (no re-embedding), under the ingest lock so an ingest cannot
        interleave, and the cache is rewritten -- the same guarantees
        delete_source needed, now in one place for every caller.
        """
        removed = 0
        with self._ingest_lock:
            self.ensure_corpus()
            with self._lock:
                old_chunks = list(self._chunks or [])
                keep = [i for i, c in enumerate(old_chunks) if not drop(c)]
                removed = len(old_chunks) - len(keep)

            if removed:
                from backend.ingestion.embeddings import embed_texts
                from backend.retrieval.vector_store import VectorStore

                kept_chunks = [old_chunks[i] for i in keep]
                vectors = self._store.vectors(len(old_chunks)) if len(self._store) == len(old_chunks) else None
                new_store = VectorStore(dim=1024)
                if kept_chunks:
                    kept_vecs = (
                        vectors[keep] if vectors is not None
                        else embed_texts([c.text for c in kept_chunks])
                    )
                    new_store.add_chunks(kept_chunks, kept_vecs)
                with self._lock:
                    self._store = new_store
                    self._chunks = kept_chunks
                self._write_corpus_cache(kept_chunks)

            with self._lock:
                self._snapshot = None
                self._cached_chunks = None
        return removed

    def purge_placeholder_chunks(self) -> int:
        """Remove chunks that are only an OCR placeholder, not text.

        Earlier builds indexed "[Image Document: tmpXXXX.png]" for every page
        OCR found nothing on. Such a chunk matches no question and pollutes
        every search; this removes the ones already in an index.
        """
        import re as _re

        placeholder = _re.compile(r"^\s*(\[Image Document:[^\]]*\]\s*)+$")
        return self._remove_chunks(lambda c: bool(placeholder.match(c.text or "")))

    def delete_source(self, target_path: str) -> dict:
        """Remove a file or folder from the active corpus, VectorStore, and registry."""
        p = Path(target_path)
        doc_name = p.name
        norm_path = str(p.resolve()).lower()

        # 1. Stop watching if it's a watched directory
        self.watcher.remove_source(target_path)

        # 2 + 3. Remove the chunks AND their vectors, and persist that.
        #
        # This filtered the in-memory list and deleted SQLite rows with
        # LIKE '%name%', which went wrong three ways:
        #   * on a backend that had not loaded the corpus yet it removed
        #     nothing, so the "deleted" document came back from the disk
        #     cache on the next start;
        #   * FAISS kept every vector, so the index and the chunk list no
        #     longer lined up by position -- and positions are the only
        #     link between a vector and its text;
        #   * LIKE '%notes.txt%' also deleted old_notes.txt's rows.
        # The store is rebuilt from the kept chunks and their EXISTING
        # vectors (no re-embedding), under the ingest lock so an ingest
        # cannot interleave, and the cache is rewritten.
        def _matches(c) -> bool:
            name = c.metadata.source_document.lower()
            return name == doc_name.lower() or name == target_path.lower()

        removed_count = self._remove_chunks(_matches)
        if removed_count:
            self._indexed_paths.pop(doc_name, None)

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
        import threading
        import time as _time

        from backend.evaluation.export_inspection_data import export_graph

        cached = getattr(self, "_graph_failure", None)
        if cached is not None:
            result, failed_at = cached
            if (_time.time() - failed_at) < self._GRAPH_FAILURE_TTL_SECONDS:
                return result
            # EXPIRED: answer with the known failure NOW and re-probe
            # behind it. Re-probing inline still cost one poller 4.1s
            # every twenty seconds -- MEASURED as a /api/health stall
            # recurring on exactly that period while Neo4j was down.
            # Recovery is noticed on the next call after the probe lands.
            if not getattr(self, "_graph_probe_running", False):
                self._graph_probe_running = True

                def _probe():
                    try:
                        fresh = export_graph(uri, user, password)
                        self._graph_failure = (
                            None if fresh.get("available") else (fresh, _time.time())
                        )
                    except Exception:  # noqa: BLE001 - keep the old failure
                        self._graph_failure = (result, _time.time())
                    finally:
                        self._graph_probe_running = False

                threading.Thread(target=_probe, name="graph-probe", daemon=True).start()
            return result

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
