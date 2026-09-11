"""Tests for retrieve_with_grounding_check — RAG_SPEC.md §3's 0.35
confidence-threshold refusal, the literal implementation of the
NotebookLM-style "not found in the provided corpus" behavior."""

import pytest

from backend.ingestion import model_cache
from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

pytestmark = pytest.mark.skipif(
    not model_cache.local_cache_dir("embeddings", "BAAI/bge-large-en-v1.5").exists(),
    reason=(
        "bge-large-en-v1.5 is not cached locally — run "
        "`python -m backend.ingestion.fetch_models --model bge-large-en-v1.5` "
        "once (with internet) before running this suite."
    ),
)

_CORPUS = [
    "The hydrocracker catalyst is showing WABT creep and may need a change-out soon.",
    "Valve V-204 on the Mangalore-Hassan pipeline segment was inspected with no anomalies found.",
    "The CCR unit's hydrogen output feeds the hydrotreating units downstream.",
]


def _build_store():
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.vector_store import VectorStore

    chunks = [
        IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document="doc.pdf", document_type="pdf", page_number=1,
                chunk_index=i, ingestion_date="2026-09-09",
            ),
        )
        for i, text in enumerate(_CORPUS)
    ]
    store = VectorStore(dim=1024)
    store.add_chunks(chunks, embed_texts([c.text for c in chunks]))
    return store


def test_relevant_query_is_found_and_grounded():
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store = _build_store()
    result = retrieve_with_grounding_check(store, "catalyst deactivation trend", top_k=3)

    assert result.found is True
    assert result.chunks
    assert result.reason is None


def test_empty_corpus_is_explicitly_not_found():
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
    from backend.retrieval.vector_store import VectorStore

    store = VectorStore(dim=1024)
    result = retrieve_with_grounding_check(store, "anything at all", top_k=3)

    assert result.found is False
    assert result.chunks == []
    assert result.reason == "No documents in the corpus matched this query."


def test_wildly_unrelated_query_is_refused():
    """This test used to accept EITHER outcome — it asserted only that
    the function ran, with a docstring reasoning that "either outcome is
    legitimate depending on how the embedding model happens to score
    this". A test that passes whether or not the feature works tests
    nothing, and this is the exact test that let a completely dead
    refusal gate through unnoticed: the old implementation computed
    (top - min) / (max - min) where top IS max, so it was always exactly
    1.0 and the refusal branch was unreachable. Measured across 16
    questions spanning in-corpus to "the plot of Pride and Prejudice",
    it refused 0 of 16.

    So this now asserts the actual behaviour. If the embedding model is
    swapped and this fails, that is the test doing its job — recalibrate
    with backend/evaluation/calibrate_confidence.py rather than
    weakening the assertion back to "either is fine"."""
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store = _build_store()
    result = retrieve_with_grounding_check(
        store, "what is the plot of Pride and Prejudice", top_k=3
    )

    assert result.found is False
    assert result.chunks == []
    assert result.reason == "not found in the provided corpus"


def test_in_corpus_query_is_not_refused():
    """The inverse guard, and the one that stops an over-tight threshold
    from shipping. A gate that refuses everything satisfies the test
    above perfectly while being just as broken as one that refuses
    nothing — both were observed during this fix."""
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store = _build_store()
    result = retrieve_with_grounding_check(store, "hydrocracker catalyst WABT", top_k=3)

    assert result.found is True
    assert result.chunks


def test_confidence_is_measured_on_similarity_not_on_fused_rank():
    """Pins the actual mechanism, not just its output.

    Reciprocal Rank Fusion scores on RANK and discards similarity
    magnitude — some chunk is always rank 1, so its fused score is
    identical whether the corpus answers the question or has nothing to
    do with it. No function of fused ranks can distinguish those, which
    is why the gate reads dense similarity directly. If someone later
    "simplifies" this back to using the fused score, the refusal above
    silently dies again; this test fails loudly instead, because a
    corpus where every fused score is identical must still refuse an
    unrelated query."""
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
    from backend.retrieval.hybrid_search import rrf_fuse

    store = _build_store()
    query = "what is the plot of Pride and Prejudice"

    fused = rrf_fuse(store, query, 3)
    # Every candidate is rank-1-ish in fusion terms; the fused scores
    # carry no signal about relevance at all.
    assert fused, "expected candidates to exist"
    assert max(fused.values()) > 0

    # ...and yet the query is still correctly refused.
    assert retrieve_with_grounding_check(store, query, top_k=3).found is False


def test_single_document_corpus_has_no_denominator_to_normalize_against():
    # min_score == max_score when there's only one real candidate --
    # must not divide by zero, and must not be automatically treated as
    # "low confidence" just because there's nothing to compare it to.
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.vector_store import VectorStore

    chunk = IngestedChunk(
        text="Only one document exists in this tiny corpus.",
        metadata=ChunkMetadata(
            source_document="solo.pdf", document_type="pdf", page_number=1,
            chunk_index=0, ingestion_date="2026-09-09",
        ),
    )
    store = VectorStore(dim=1024)
    store.add_chunks([chunk], embed_texts([chunk.text]))

    result = retrieve_with_grounding_check(store, "the only document", top_k=3)

    assert result.found is True
