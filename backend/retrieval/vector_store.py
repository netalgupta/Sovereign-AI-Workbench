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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def add_chunks(self, chunks: list[IngestedChunk], embeddings: np.ndarray) -> None:
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

    def get_by_faiss_id(self, faiss_id: int) -> StoredChunk | None:
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
        if self.index.ntotal == 0:
            return []
        top_k = min(top_k, self.index.ntotal)
        query = np.ascontiguousarray(query_embedding.reshape(1, -1), dtype=np.float32)
        scores, ids = self.index.search(query, top_k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def all_chunk_texts(self) -> list[tuple[int, str]]:
        """[(faiss_id, text), ...] for every stored chunk, ordered by
        faiss_id. Needed by CARD 09's BM25 sparse index, which must be
        built over exactly the same corpus as the dense index — not a
        separately-maintained copy that could drift out of sync.
        """
        cursor = self._conn.execute("SELECT faiss_id, text FROM chunks ORDER BY faiss_id")
        return cursor.fetchall()

    def __len__(self) -> int:
        return self.index.ntotal
