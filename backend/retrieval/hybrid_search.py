from __future__ import annotations

"""Hybrid dense + sparse retrieval — VIBECODING_SPEC.md CARD 09.

Dense (FAISS/bge-large) finds semantically similar chunks even when the
exact words differ; sparse (BM25) finds exact keyword/tag matches even
when the embedding model doesn't weight a rare term (e.g. "V-204") as
heavily as a human would. Fusing both catches what either would miss
alone — RAG_SPEC.md §3 locks the fusion method (Reciprocal Rank Fusion,
k=60) and this card's over-fetch factor (2x) specifically so retrieval
quality is comparable across runs, not re-tuned ad hoc per query.
"""

from backend.retrieval import lexical

from backend.ingestion.embeddings import embed_texts
from backend.retrieval.vector_store import VectorStore
from pydantic import BaseModel

RRF_K = 60  # exact, per RAG_SPEC.md §3 — the original RRF paper's standard constant, not tuned


class RetrievedChunk(BaseModel):
    text: str
    source_document: str
    page_number: int | None
    score: float


def rrf_fuse(store: VectorStore, query: str, top_k: int) -> dict[int, float]:
    """Reciprocal Rank Fusion over the WHOLE corpus, not just each
    ranking's top-k. Returns {faiss_id: fused_score} for every faiss_id
    that appears in either ranking.

    Exposed (not private-only) because grounded_retrieval.py's
    confidence check needs to normalize over this same full candidate
    pool, per RAG_SPEC.md §3's "normalizing the fused scores across the
    candidate set" — reusing this function instead of recomputing fusion
    keeps both call sites looking at the same set, not two that could
    silently diverge.
    """
    all_rows = store.all_chunk_texts()
    if not all_rows:
        return {}

    faiss_ids = [row[0] for row in all_rows]
    corpus_texts = [row[1] for row in all_rows]

    # Dense: over-fetch by 2x before fusion, exact per CARD 09.
    query_embedding = embed_texts([query])[0]
    dense_hits = store.dense_search(query_embedding, top_k=min(top_k * 2, len(faiss_ids)))
    dense_rank = {faiss_id: rank for rank, (faiss_id, _score) in enumerate(dense_hits, start=1)}

    # Sparse: BM25Okapi over NORMALISED tokens, and a cached index.
    #
    # This was `[text.split() for text in corpus_texts]` indexed and
    # `bm25.get_scores(query.split())` queried -- raw whitespace splits
    # on both sides. The index therefore held "Inspection", "Report:",
    # "CCR-1," and "(SOP-114-Rev3)" with their capitals and attached
    # punctuation, and a user typing "inspection" matched none of them.
    # Half the hybrid retriever was silently inert; dense search covered
    # for it convincingly enough that nothing looked broken.
    #
    # backend/retrieval/lexical.py tokenizes both sides identically
    # (lowercased, punctuation stripped, identifiers like SOP-114-Rev3
    # and TC-201A kept whole) and caches the index instead of rebuilding
    # it on every single query.
    bm25_scores = lexical.scores(all_rows, query)
    if len(bm25_scores) == 0:
        sparse_order = []
    else:
        sparse_order = sorted(
            range(len(faiss_ids)), key=lambda i: bm25_scores[i], reverse=True
        )
    sparse_rank = {faiss_ids[i]: rank for rank, i in enumerate(sparse_order, start=1)}

    candidate_ids = set(dense_rank) | set(sparse_rank)
    fused: dict[int, float] = {}
    for faiss_id in candidate_ids:
        score = 0.0
        if faiss_id in dense_rank:
            score += 1.0 / (RRF_K + dense_rank[faiss_id])
        if faiss_id in sparse_rank:
            score += 1.0 / (RRF_K + sparse_rank[faiss_id])
        fused[faiss_id] = score
    return fused


def hybrid_search(store: VectorStore, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Hybrid dense+sparse search with Reciprocal Rank Fusion.

    Every returned chunk has `source_document`/`page_number` populated
    from the ingestion metadata — RAG_SPEC.md §3 is explicit that a
    missing citation on a real chunk is a grounding failure (NFR-4), not
    an acceptable gap, so these are never left None if the store has them.
    """
    fused = rrf_fuse(store, query, top_k)
    ranked_ids = sorted(fused, key=lambda fid: fused[fid], reverse=True)[:top_k]

    results = []
    for faiss_id in ranked_ids:
        chunk = store.get_by_faiss_id(faiss_id)
        if chunk is None:
            continue  # defensive: shouldn't happen, but never crash retrieval over it
        results.append(
            RetrievedChunk(
                text=chunk.text,
                source_document=chunk.source_document,
                page_number=chunk.page_number,
                score=fused[faiss_id],
            )
        )
    return results
