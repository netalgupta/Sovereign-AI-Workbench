from __future__ import annotations

"""FAISS + SQLite chunk storage — RAG_SPEC.md §2 step 6.

Exact index type per spec: `IndexFlatIP` — "flat is fine at hackathon
corpus scale, don't over-engineer with IVF/HNSW for a demo-sized
corpus." IndexFlatIP computes a plain inner product; it only equals
cosine similarity because embeddings.py's embed_texts() L2-normalizes
every vector first (RAG_SPEC.md §2 step 5). If a future change ever
embeds without normalizing, this store's scores silently stop meaning
"similarity" — that dependency is real, not decorative.

WHY FAISS (a pure in-memory index with no text of its own) PLUS SQLITE
(the raw text/metadata), NOT ONE STORE: FAISS is excellent at "find the
nearest vectors" and bad at storing arbitrary metadata; SQLite is the
reverse. RAG_SPEC.md §2 step 6 specifies exactly this pairing — a
parallel SQLite table "keyed by the same chunk ID as the FAISS vector
index position." That id is FAISS's own insertion order (0, 1, 2, ...),
which is why `add_chunks` computes `start_id = self.index.ntotal` before
adding — it's the only way to know what id FAISS is about to assign.
"""

import sqlite3
import threading

import numpy as np
from pydantic import BaseModel

try:
    import faiss
except ImportError as exc:  # pragma: no cover - environment guard, not a code path
    raise ImportError(
        "faiss-cpu is required for VectorStore. Install with: pip install faiss-cpu"
    ) from exc

from backend.ingestion.document_ingestion import IngestedChunk


class StoredChunk(BaseModel):
    faiss_id: int
    text: str
    source_document: str
    document_type: str
    page_number: int | None
    chunk_index: int
    ingestion_date: str


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    faiss_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    source_document TEXT NOT NULL,
    document_type TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER NOT NULL,
    ingestion_date TEXT NOT NULL
)
"""


class VectorStore:
    """Dense vector index (FAISS) + parallel chunk text/metadata (SQLite).

    `dim` must match whatever embedding model produced the vectors
    passed to `add_chunks`/`search` — 1024 for bge-large-en-v1.5
    (embeddings.py's MODEL_ID). This class doesn't call embed_texts
    itself; hybrid_search.py owns that, keeping this class a pure
    storage/lookup layer with no model dependency of its own.
    """

    def __init__(self, dim: int = 1024, db_path: str = ":memory:"):
        self.index = faiss.IndexFlatIP(dim)
        # ONE LOCK FOR THE INDEX AND THE TABLE. FAISS is not safe to read
        # while another thread adds: add() can reallocate the vector
        # buffer under a concurrent search or reconstruct. MEASURED as a
        # segfault (exit 139) of the whole API while a folder was being
        # indexed and a page read the vectors -- and a chat search during
        # an ingest takes the same path. The SQLite connection is shared
        # across threads (check_same_thread=False) and needs the same
        # guard. Re-entrant so a locked method may call another.
        self._rw = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()
        # Moves only when the corpus changes; see `generation`.
        self._generation = 0
        self._texts_cache: list | None = None
        self._texts_cache_gen = -1
        self._records_cache: list | None = None
        self._records_cache_gen = -1

    def add_chunks(self, chunks: list[IngestedChunk], embeddings: np.ndarray) -> None:
        with self._rw:
            if len(chunks) != embeddings.shape[0]:
                raise ValueError(
                    f"chunks ({len(chunks)}) and embeddings ({embeddings.shape[0]}) "
                    f"must be the same length"
                )
            if not chunks:
                return

            start_id = self.index.ntotal  # see module docstring for why this must come first
            self.index.add(np.ascontiguousarray(embeddings, dtype=np.float32))

            rows = [
                (
                    start_id + i,
                    chunk.text,
                    chunk.metadata.source_document,
                    chunk.metadata.document_type,
                    chunk.metadata.page_number,
                    chunk.metadata.chunk_index,
                    chunk.metadata.ingestion_date,
                )
                for i, chunk in enumerate(chunks)
            ]
            self._conn.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)", rows
            )
            self._conn.commit()
            # The corpus changed. Anything holding a view of it is now stale
            # and must rebuild rather than answer from what it remembers.
            self._generation += 1

    def get_by_faiss_id(self, faiss_id: int) -> StoredChunk | None:
        with self._rw:
            cursor = self._conn.execute(
                "SELECT faiss_id, text, source_document, document_type, page_number, "
                "chunk_index, ingestion_date FROM chunks WHERE faiss_id = ?",
                (faiss_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return StoredChunk(
                faiss_id=row[0],
                text=row[1],
                source_document=row[2],
                document_type=row[3],
                page_number=row[4],
                chunk_index=row[5],
                ingestion_date=row[6],
            )

    def dense_search(self, query_embedding: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        """Returns [(faiss_id, inner_product_score), ...], best first.

        Empty store returns [] rather than letting FAISS error on a
        search against zero vectors.
        """
        with self._rw:
            if self.index.ntotal == 0:
                return []
            top_k = min(top_k, self.index.ntotal)
            query = np.ascontiguousarray(query_embedding.reshape(1, -1), dtype=np.float32)
            scores, ids = self.index.search(query, top_k)
            return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def document_names(self) -> list[str]:
        """Every indexed document's name."""
        with self._rw:
            return [r[0] for r in self._conn.execute("SELECT DISTINCT source_document FROM chunks").fetchall()]

    def faiss_ids_for_documents(self, names) -> set[int]:
        """Every chunk id belonging to the named documents (a chat's switched-on sources)."""
        names = list(names)
        if not names:
            return set()
        with self._rw:
            ids: set[int] = set()
            for start in range(0, len(names), 500):  # SQLite's bound-parameter limit
                batch = names[start:start + 500]
                cursor = self._conn.execute(
                    f"SELECT faiss_id FROM chunks WHERE source_document IN ({','.join('?' * len(batch))})",
                    batch,
                )
                ids.update(int(r[0]) for r in cursor.fetchall())
            return ids

    def get_neighbours(
        self, source_document: str, chunk_index: int, window: int = 1
    ) -> list["StoredChunk"]:
        """Chunks either side of `chunk_index` in the same document.

        WHY THIS IS NEEDED. Retrieval scores chunks independently, so it
        returns the single passage that best matches the query and
        nothing around it. For a procedure that is the wrong unit of
        retrieval. Measured on the real corpus:

            "What is the SOP for Hydrocracker"
              -> one SOP-114 chunk retrieved
              -> answer listed 3 steps

            "Summarise SOP-114-Rev3"
              -> two SOP-114 chunks retrieved (4.3 happened to rank)
              -> answer listed all 8 steps, with parameters

        Same document, same procedure, same model. The difference was
        purely which chunks happened to score. The answer was not
        wrong -- it was truncated by the retriever, and nothing in the
        output said so, which is the dangerous part: a procedure
        missing steps 4 through 8 reads exactly like a complete one.

        Neighbouring chunks are cheap to fetch (an indexed lookup, no
        embedding, no scoring) and are the passages a human would read
        next. This is the standard repair for chunk-boundary truncation.
        """
        with self._rw:
            rows = self._conn.execute(
                "SELECT faiss_id, text, source_document, document_type, page_number, "
                "chunk_index, ingestion_date FROM chunks "
                "WHERE source_document = ? AND chunk_index BETWEEN ? AND ? "
                "ORDER BY chunk_index",
                (source_document, chunk_index - window, chunk_index + window),
            ).fetchall()
            return [
                StoredChunk(
                    faiss_id=row[0],
                    text=row[1],
                    source_document=row[2],
                    document_type=row[3],
                    page_number=row[4],
                    chunk_index=row[5],
                    ingestion_date=row[6],
                )
                for row in rows
            ]

    @property
    def generation(self) -> int:
        """Bumped whenever the corpus changes.

        Anything caching a view of the corpus must key on this. A cache
        that outlives the data it was built from is the single most
        repeated bug in this repository -- a committed JSON artifact
        with stale numbers, a resume path serving a cached score instead
        of the model's output, hash embeddings that satisfied every
        shape assertion. A counter that only the write path can touch is
        the cheap version of checking provenance.
        """
        return self._generation

    def all_chunk_texts(self) -> list[tuple[int, str]]:
        """[(faiss_id, text), ...] for every stored chunk, ordered by
        faiss_id. Needed by CARD 09's BM25 sparse index, which must be
        built over exactly the same corpus as the dense index — not a
        separately-maintained copy that could drift out of sync.

        CACHED, because this is a full read of the corpus and it runs
        THREE TIMES PER QUERY -- hybrid_search builds the sparse index
        from it, grounded_retrieval reads it again for lexical evidence,
        and generation reads it a third time to explain the query. At 52
        documents that is invisible. At the 1000-page PDFs this is meant
        for it is the dominant cost of a search that should be
        sub-second.

        Invalidated by `generation`, which only add_chunks can move, so
        a re-ingest cannot be served from a stale list.
        """
        with self._rw:
            if self._texts_cache is not None and self._texts_cache_gen == self._generation:
                return self._texts_cache
            cursor = self._conn.execute("SELECT faiss_id, text FROM chunks ORDER BY faiss_id")
            rows = cursor.fetchall()
            self._texts_cache = rows
            self._texts_cache_gen = self._generation
            return rows

    def all_chunk_records(self) -> list[dict]:
        """Every chunk with its metadata, as dicts.

        all_chunk_texts() returns (faiss_id, text) because that is what
        BM25 needs. Anything that filters by SOURCE -- revision
        tracking, correspondence summarisation, per-document analysis --
        needs the metadata too, and doing that as
        get_by_faiss_id() in a loop is one query per chunk.

        Cached on the same generation counter as all_chunk_texts, so a
        re-ingest invalidates it and nothing can serve a view of a
        corpus that has moved.
        """
        with self._rw:
            if self._records_cache is not None and self._records_cache_gen == self._generation:
                return self._records_cache
            cursor = self._conn.execute(
                "SELECT faiss_id, text, source_document, document_type, page_number, "
                "chunk_index, ingestion_date FROM chunks ORDER BY faiss_id"
            )
            records = [
                {
                    "faiss_id": row[0],
                    "text": row[1],
                    "source_document": row[2],
                    "document_type": row[3],
                    "page_number": row[4],
                    "chunk_index": row[5],
                    "ingestion_date": row[6],
                }
                for row in cursor.fetchall()
            ]
            self._records_cache = records
            self._records_cache_gen = self._generation
            return records

    def vectors(self, n: int) -> np.ndarray | None:
        """The first `n` stored vectors, or None if fewer are stored.

        Read under the store lock -- see __init__ for why reading the
        index while an ingest adds to it is not safe.
        """
        with self._rw:
            if n <= 0 or self.index.ntotal < n:
                return None
            return np.asarray(self.index.reconstruct_n(0, n), dtype=np.float32)

    def __len__(self) -> int:
        with self._rw:
            return self.index.ntotal
