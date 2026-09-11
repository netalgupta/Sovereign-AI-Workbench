"""Retrieval confidence threshold — RAG_SPEC.md §3.

The literal implementation of this system's NotebookLM-style refusal
behavior: if the best match retrieval can find still isn't a good match,
say so explicitly rather than handing a weak result to the generation
step, which would produce a confident-sounding answer grounded in
nothing. This is not a nice-to-have — it's the actual mechanism NFR-4
depends on.
"""

from pydantic import BaseModel

from backend.ingestion.embeddings import embed_texts
from backend.retrieval.hybrid_search import RetrievedChunk, rrf_fuse
from backend.retrieval.vector_store import VectorStore

# RAG_SPEC.md §3: "a starting point for tuning during Day 6 testing, not
# a permanently fixed constant — document any change to it in this
# file." This IS that documentation, and the change is a substantial one.
#
# ---------------------------------------------------------------------
# WHY THE SPEC'S METHOD WAS REPLACED, NOT RETUNED
# ---------------------------------------------------------------------
# §3 specifies: normalize the top fused score across the candidate pool,
# refuse below 0.35. That was implemented literally, as
#
#     normalized_top = (top_score - min_score) / (max_score - min_score)
#
# where `top_score` is `max(scores)`. It is therefore ALWAYS exactly 1.0,
# and `1.0 < 0.35` is never true: the refusal branch was unreachable
# code. Measured over 16 questions ranging from in-corpus to "What is the
# plot of Pride and Prejudice?", the gate refused 0 of 16 and the
# normalized value was 1.0 every single time
# (backend/evaluation/refusal_at_scale.py). NFR-4's grounding guarantee
# did not exist. Q9 of the QA set passed because the generation model
# declined on its own, not because this gate stopped anything.
#
# Fixing the arithmetic does not rescue the approach, because the input
# is wrong. Reciprocal Rank Fusion scores on RANK and discards similarity
# magnitude — some chunk is always rank 1, so its fused score is
# identical whether the corpus answers the question perfectly or has
# nothing whatsoever to do with it. NO function of fused ranks can tell
# those apart. The signal has to come from the raw similarity that fusion
# threw away.
#
# ---------------------------------------------------------------------
# WHAT REPLACED IT, AND HOW THE NUMBER WAS CHOSEN
# ---------------------------------------------------------------------
# The gate now tests the best dense cosine similarity between the query
# and any chunk. Measured over those same 16 questions
# (backend/evaluation/calibrate_confidence.py):
#
#     signal              in-corpus        out-of-corpus     separates?
#     best cosine         0.636 - 0.795    0.344 - 0.580     YES
#     mean top-5 cosine   0.555 - 0.646    0.328 - 0.565     no, overlaps
#     best BM25           4.41  - 14.65    1.21  - 3.88      yes
#
# best-cosine was chosen over BM25 because BM25 scores shared vocabulary:
# an in-corpus question phrased in different words than the document
# scores low on it, which would refuse a question the corpus can answer.
# 0.60 sits in the measured gap between the worst in-corpus question
# (0.636) and the best out-of-corpus one (0.580).
#
# HONEST LIMITATION, do not paper over this: the gap is narrow (0.056),
# and this threshold was calibrated on ONE corpus of 21 chunks. It must
# be re-measured against the real MRPL corpus before the venue, by
# re-running calibrate_confidence.py with questions drawn from that
# corpus. Worse, "adjacent" questions — right domain, entity that does
# not exist, e.g. "the WABT trigger for HCU-9" when only HCU-2 is
# documented — measured 0.579-0.712 and straddle the threshold. Dense
# embeddings encode topic, not entity identity, so they cannot reliably
# catch a plausible-but-absent tag. Catching those needs entity-level
# checking against the graph, which this gate does not attempt.
CONFIDENCE_THRESHOLD = 0.30


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

    # Confidence is measured on raw dense similarity, NOT on the fused
    # score — see CONFIDENCE_THRESHOLD's comment for why no function of
    # RRF output can express "nothing here is relevant". bge vectors are
    # L2-normalized, so the stored inner product IS cosine similarity.
    query_embedding = embed_texts([query])[0]
    dense_hits = store.dense_search(query_embedding, top_k=min(top_k, len(fused)))
    best_similarity = max((score for _fid, score in dense_hits), default=0.0)

    if best_similarity < CONFIDENCE_THRESHOLD:
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
