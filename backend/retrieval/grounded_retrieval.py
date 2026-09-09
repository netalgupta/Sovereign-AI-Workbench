"""Retrieval confidence threshold — RAG_SPEC.md §3.

The literal implementation of this system's NotebookLM-style refusal
behavior: if the best match retrieval can find still isn't a good match,
say so explicitly rather than handing a weak result to the generation
step, which would produce a confident-sounding answer grounded in
nothing. This is not a nice-to-have — it's the actual mechanism NFR-4
depends on.
"""

from pydantic import BaseModel

from backend.retrieval.hybrid_search import RetrievedChunk, rrf_fuse
from backend.retrieval.vector_store import VectorStore

# RAG_SPEC.md §3: "a starting point for tuning during Day 6 testing, not
# a permanently fixed constant — document any change to it in this
# file." It hasn't been changed since; this constant IS that file's
# current value.
CONFIDENCE_THRESHOLD = 0.35


class GroundedRetrievalResult(BaseModel):
    found: bool
    chunks: list[RetrievedChunk]
    reason: str | None = None


def retrieve_with_grounding_check(
    store: VectorStore, query: str, top_k: int = 5
) -> GroundedRetrievalResult:
    """hybrid_search, gated by RAG_SPEC.md §3's confidence threshold.

    Normalizes the top fused score against the FULL fused candidate pool
    (every chunk that appeared in either the dense or sparse ranking),
    not just the top_k slice returned to the caller — re-normalizing
    against a shrinking top_k window would make the threshold's meaning
    drift with top_k itself, which isn't what "normalizing across the
    candidate set" in the spec means.
    """
    fused = rrf_fuse(store, query, top_k)
    if not fused:
        return GroundedRetrievalResult(
            found=False, chunks=[], reason="No documents in the corpus matched this query."
        )

    scores = list(fused.values())
    min_score, max_score = min(scores), max(scores)
    top_score = max(scores)

    if max_score == min_score:
        # Every candidate tied (often: exactly one candidate exists at
        # all) — nothing to normalize against, so there's no basis to
        # call this "low confidence" relative to anything else.
        normalized_top = 1.0
    else:
        normalized_top = (top_score - min_score) / (max_score - min_score)

    if normalized_top < CONFIDENCE_THRESHOLD:
        return GroundedRetrievalResult(
            found=False, chunks=[], reason="not found in the provided corpus"
        )

    ranked_ids = sorted(fused, key=lambda fid: fused[fid], reverse=True)[:top_k]
    chunks = []
    for faiss_id in ranked_ids:
        stored = store.get_by_faiss_id(faiss_id)
        if stored is None:
            continue
        chunks.append(
            RetrievedChunk(
                text=stored.text,
                source_document=stored.source_document,
                page_number=stored.page_number,
                score=fused[faiss_id],
            )
        )
    return GroundedRetrievalResult(found=True, chunks=chunks)
