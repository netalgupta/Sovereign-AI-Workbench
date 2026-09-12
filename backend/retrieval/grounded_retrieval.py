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
from backend.retrieval import lexical
from backend.retrieval.query_builder import build_search_query
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
# THE THRESHOLD DEPENDS ON WHICH EMBEDDER IS RUNNING, because the two
# produce similarity on completely different scales. A single global
# number is only ever correct for one of them.
#
# This was learned the hard way during the orchestrator merge. The value
# had been lowered 0.60 -> 0.30 so the gate would stop refusing
# everything on a machine without the model cached. That was a rational
# response to a real symptom, but on a machine WITH the model it inverts
# the safety property: measured out-of-corpus similarity bottoms out at
# 0.344, so a 0.30 floor passes literally everything — the same dead
# gate NFR-4 was fixed for, reintroduced by a constant.
#
#   semantic (bge-large): in-corpus 0.636-0.795, out 0.344-0.580.
#       0.60 sits in the measured gap.
#   hash fallback: vectors are bag-of-words projections with no semantic
#       content, so scores are far lower and compressed. 0.30 is an
#       empirical floor, NOT a calibrated one — on this backend the gate
#       is a coarse filter, not a grounding guarantee, because hash
#       vectors cannot distinguish "about this topic" from "shares
#       vocabulary with it".
_THRESHOLD_BY_BACKEND = {
    "bge-large-en-v1.5": 0.60,
    "deterministic-hash": 0.30,
}

# Kept as the documented default for the real model, so existing readers
# and reports still resolve a number.
CONFIDENCE_THRESHOLD = 0.60


def confidence_threshold() -> float:
    """The refusal floor for whichever embedder is actually running."""
    from backend.ingestion.embeddings import active_backend

    return _THRESHOLD_BY_BACKEND.get(active_backend(), CONFIDENCE_THRESHOLD)


class GroundedRetrievalResult(BaseModel):
    found: bool
    chunks: list[RetrievedChunk]
    reason: str | None = None

    # WHAT A REFUSAL NOW CARRIES, AND WHY.
    #
    # The gate is correct to refuse "Tell me abt inspection" -- measured
    # best cosine falls below the floor, while the same question written
    # out ("Tell me about the inspection report") clears it comfortably
    # and returns the right document. Lowering the threshold to catch the
    # shorthand is exactly how this gate died the first time: out-of-
    # corpus similarity bottoms out at 0.344, so any floor loose enough
    # to admit a vague query admits Pride and Prejudice too.
    #
    # But a bare "not found" against a corpus that plainly contains an
    # inspection report reads as the product being broken, and the user
    # has no way to tell a genuine miss from a phrasing problem. So the
    # refusal reports WHAT IT ALMOST MATCHED -- document names and the
    # margin -- without quoting any of their content.
    #
    # That distinction is the whole point: naming a file is not a claim
    # about what is in it, so nothing ungrounded is asserted, and the
    # user gets the one piece of information that lets them fix their
    # query themselves.
    best_similarity: float = 0.0
    threshold: float = 0.0
    near_miss_documents: list[str] = []

    # Which signal let this through: "dense" (embedding similarity),
    # "lexical" (the query's own rare terms are present), or "neither"
    # (refused). Recorded because a hybrid gate that cannot say WHICH
    # half admitted an answer is untunable -- you cannot tell a
    # correctly-rescued query from a threshold that has drifted loose.
    admitted_by: str = "neither"
    lexical_matched: list[str] = []
    lexical_unknown: list[str] = []


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
    # EXPAND THE SEARCH QUERY, NOT THE REQUEST.
    #
    # People type imperatives and abbreviations, and the retriever scores
    # them literally. Measured: "Give sops for Hydrocrackers" ranked
    # SOP-114-Rev3 FOURTH of five, while the written-out form ranked it
    # first. The documents say "Standard Operating Procedure" and
    # "SOP-114"; nothing in them says "sops", and "Give"/"for"
    # contribute nothing while still occupying the embedding.
    #
    # Rank matters beyond ordering here: the top-k chunks become the
    # SOURCES block in prompt order, so a document at rank 4 sits at the
    # far end of ~5000 characters of context and the model answers from
    # what is nearest. The thin metadata-only answer that prompted this
    # -- document number, effective date, review cycle, no procedure --
    # is what late-ranked context produces.
    #
    # Only the retrieval string is expanded. `query` as shown to the
    # model stays verbatim, so the answer addresses what was asked.
    rows = store.all_chunk_texts()
    search_query = build_search_query(query, rows)

    fused = rrf_fuse(store, search_query, top_k)
    if not fused:
        return GroundedRetrievalResult(
            found=False, chunks=[], reason="No documents in the corpus matched this query."
        )

    # Confidence is measured on raw dense similarity, NOT on the fused
    # score — see CONFIDENCE_THRESHOLD's comment for why no function of
    # RRF output can express "nothing here is relevant". bge vectors are
    # L2-normalized, so the stored inner product IS cosine similarity.
    query_embedding = embed_texts([search_query])[0]
    dense_hits = store.dense_search(query_embedding, top_k=min(top_k, len(fused)))
    best_similarity = max((score for _fid, score in dense_hits), default=0.0)

    threshold = confidence_threshold()

    # THE GATE IS HYBRID, because the retriever is.
    #
    # It used to consult dense cosine alone. That makes the refusal
    # decision blind to the evidence the sparse half exists to provide:
    # a query whose exact, rare terms appear verbatim in a document
    # could still be refused for having an unlucky embedding. Measured:
    # "Tell me abt inspection" scores 0.5228 against a 0.60 floor and is
    # refused, with an inspection report sitting in the corpus.
    #
    # Relaxing the dense floor is the wrong repair and has already
    # failed here once: out-of-corpus similarity bottoms out near 0.344,
    # so any floor loose enough for vague phrasing also passes "What is
    # the plot of Pride and Prejudice?" -- which is precisely how this
    # gate became dead code before.
    #
    # So a second, INDEPENDENT signal decides instead: do the user's own
    # words occur in the corpus with enough discriminating weight to be
    # what the question is about? See lexical.lexical_evidence -- it
    # discards out-of-vocabulary terms rather than counting them as
    # misses, which is what separates a typo from a topic the corpus
    # genuinely does not cover.
    #
    # Either signal may admit an answer; BOTH must fail to refuse. The
    # safety property is preserved because an out-of-domain question
    # fails both: its embedding is far, and its words are absent.
    evidence = lexical.lexical_evidence(rows, search_query)
    dense_ok = best_similarity >= threshold
    if not dense_ok and not evidence.strong:
        # Name the documents that came closest, so the refusal is
        # actionable. Names only -- never their text, which has not
        # cleared the grounding bar and must not be presented as an
        # answer by the back door.
        near_miss: list[str] = []
        for faiss_id, _score in dense_hits:
            stored = store.get_by_faiss_id(faiss_id)
            if stored and stored.source_document not in near_miss:
                near_miss.append(stored.source_document)
            if len(near_miss) == 3:
                break
        return GroundedRetrievalResult(
            found=False,
            chunks=[],
            reason="not found in the provided corpus",
            best_similarity=round(best_similarity, 4),
            admitted_by="neither",
            lexical_matched=evidence.matched,
            lexical_unknown=evidence.unknown,
            threshold=threshold,
            near_miss_documents=near_miss,
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
    return GroundedRetrievalResult(
        found=True,
        chunks=chunks,
        best_similarity=round(best_similarity, 4),
        threshold=threshold,
        admitted_by="dense" if dense_ok else "lexical",
        lexical_matched=evidence.matched,
        lexical_unknown=evidence.unknown,
    )
