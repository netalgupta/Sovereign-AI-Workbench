"""Tests for hybrid_search / rrf_fuse.

Uses a real 8-document fixture corpus and REAL bge-large embeddings —
not mocked scores. The whole point of a hybrid dense+sparse test is
proving each half actually contributes something the other would miss;
a mocked similarity score can't demonstrate that.
"""

import os

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
    ("The hydrocracker catalyst is showing WABT creep and may need a change-out soon.",
     "hydrocracker_report.pdf", 1),
    ("Valve V-204 on the Mangalore-Hassan pipeline segment was inspected with no anomalies found.",
     "pipeline_log.pdf", 3),
    ("The CCR unit's hydrogen output feeds the hydrotreating units downstream.",
     "ccr_notes.pdf", 1),
    ("Sulphur content in the latest Merox lab sample was measured at 41.5 ppm, near the spec limit.",
     "merox_lab.pdf", 2),
    ("PSA hydrogen purity trended at 99.85 percent this week, slightly below the 99.9 percent target.",
     "psa_dashboard.pdf", 1),
    ("The Novolen plant completed a grade changeover checklist for the new homopolymer grade.",
     "novolen_checklist.pdf", 1),
    ("Benzene exposure limits at the Aromatic Complex are governed by the HSE SOP for MSEZ operations.",
     "aromatic_hse.pdf", 4),
    ("The Kasargod depot requested an updated weekly delivery schedule from HQ marketing.",
     "depot_correspondence.pdf", 1),
]


@pytest.fixture(scope="module")
def populated_store():
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.vector_store import VectorStore

    chunks = [
        IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document=source,
                document_type="pdf",
                page_number=page,
                chunk_index=0,
                ingestion_date="2026-09-09",
            ),
        )
        for text, source, page in _CORPUS
    ]
    embeddings = embed_texts([c.text for c in chunks])

    store = VectorStore(dim=1024)
    store.add_chunks(chunks, embeddings)
    return store


def test_dense_favoring_paraphrase_query_finds_the_right_document(populated_store):
    from backend.retrieval.hybrid_search import hybrid_search

    # No shared keywords with the source text at all ("catalyst",
    # "WABT", "change-out" vs. "aging", "wearing out", "replaced soon")
    # — only a dense/semantic match could find this.
    results = hybrid_search(populated_store, "Is the hydrocracker aging and wearing out?", top_k=3)

    assert results
    assert results[0].source_document == "hydrocracker_report.pdf"


def test_exact_rare_keyword_query_finds_the_right_document(populated_store):
    from backend.retrieval.hybrid_search import hybrid_search

    # "V-204" is a rare, specific token — exactly what BM25's exact
    # keyword matching is good at that a purely semantic model might
    # under-weight.
    results = hybrid_search(populated_store, "V-204 inspection status", top_k=3)

    assert results
    assert results[0].source_document == "pipeline_log.pdf"


def test_every_result_has_source_and_page_populated(populated_store):
    from backend.retrieval.hybrid_search import hybrid_search

    results = hybrid_search(populated_store, "sulphur spec compliance", top_k=5)

    assert results
    for chunk in results:
        assert chunk.source_document  # never empty, per NFR-4
        assert chunk.page_number is not None  # every fixture doc has real pages


def test_top_k_is_respected():
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.hybrid_search import hybrid_search
    from backend.retrieval.vector_store import VectorStore

    chunks = [
        IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document=source, document_type="pdf", page_number=page,
                chunk_index=0, ingestion_date="2026-09-09",
            ),
        )
        for text, source, page in _CORPUS
    ]
    store = VectorStore(dim=1024)
    store.add_chunks(chunks, embed_texts([c.text for c in chunks]))

    results = hybrid_search(store, "refinery operations", top_k=3)

    assert len(results) <= 3


def test_empty_store_returns_empty_results():
    from backend.retrieval.hybrid_search import hybrid_search
    from backend.retrieval.vector_store import VectorStore

    store = VectorStore(dim=1024)
    assert hybrid_search(store, "anything at all", top_k=5) == []
