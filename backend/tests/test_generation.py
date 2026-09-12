"""Tests for generate_grounded_answer — RAG_SPEC.md §4."""

import pytest
import responses

from backend.ingestion import model_cache
from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

GENERATE_URL = "http://localhost:11434/api/generate"

pytestmark = pytest.mark.skipif(
    not model_cache.local_cache_dir("embeddings", "BAAI/bge-large-en-v1.5").exists(),
    reason=(
        "bge-large-en-v1.5 is not cached locally — run "
        "`python -m backend.ingestion.fetch_models --model bge-large-en-v1.5` "
        "once (with internet) before running this suite."
    ),
)


def _build_store(texts_and_sources):
    from backend.ingestion.embeddings import embed_texts
    from backend.retrieval.vector_store import VectorStore

    chunks = [
        IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document=source, document_type="pdf", page_number=1,
                chunk_index=i, ingestion_date="2026-09-09",
            ),
        )
        for i, (text, source) in enumerate(texts_and_sources)
    ]
    store = VectorStore(dim=1024)
    store.add_chunks(chunks, embed_texts([c.text for c in chunks]))
    return store


def test_out_of_corpus_question_never_calls_the_llm_at_all(monkeypatch):
    """The most important property this function has: when grounding
    fails, there must be NO code path to the reasoning model at all —
    not "the model was told to refuse", but "the model was never
    called".

    Deliberately mocks retrieve_with_grounding_check directly rather
    than relying on a real embedding call to coincidentally score low
    enough — a first version of this test used a real 2-chunk corpus
    and a genuinely off-topic question, and it flaked: with only 2
    candidates, RAG_SPEC.md §3's confidence threshold normalizes
    relative to such a tiny pool that "low confidence" isn't reliably
    distinguishable (the same limitation already called out in
    test_grounded_retrieval.py's own test for this). "Does the
    threshold actually fire on a real embedding" is that other test
    file's job, with a properly-sized corpus; THIS test's job is purely
    "when found=False, is /api/generate ever called" — a control-flow
    property that should be isolated from embedding-similarity specifics,
    not accidentally coupled to them.
    """
    import backend.retrieval.generation as generation_module
    from backend.retrieval.generation import generate_grounded_answer
    # The stubs below take **_ so that adding a parameter to
    # retrieve_with_grounding_check does not break them. A double that
    # pins the exact signature fails on every additive change to the
    # real function, for a reason unrelated to what the test checks --
    # which teaches people to avoid adding parameters rather than to
    # cover them.
    from backend.retrieval.grounded_retrieval import GroundedRetrievalResult

    monkeypatch.setattr(
        generation_module,
        "retrieve_with_grounding_check",
        lambda store, query, top_k=5, **_: GroundedRetrievalResult(
            found=False, chunks=[], reason="not found in the provided corpus"
        ),
    )

    # No /api/generate mock registered at all — if generate_grounded_answer
    # tried to call it, `responses` would raise ConnectionError for the
    # unmocked request rather than silently letting a real call through.
    with responses.RequestsMock(assert_all_requests_are_fired=False):
        result = generate_grounded_answer(_build_store([("x", "y.pdf")]), "anything")

    assert result.found is False
    assert result.answer_text == "Not found in the provided corpus."
    assert result.sources == []


@responses.activate
def test_grounded_question_calls_the_llm_with_formatted_sources():
    from backend.retrieval.generation import generate_grounded_answer

    responses.add(
        responses.POST,
        GENERATE_URL,
        json={"response": "The catalyst is deactivating due to WABT creep [1]."},
        status=200,
    )

    store = _build_store([("The hydrocracker catalyst is showing WABT creep.", "doc1.pdf")])

    result = generate_grounded_answer(store, "Why is the hydrocracker catalyst deactivating?")

    assert result.found is True
    assert "[1]" in result.answer_text
    assert len(result.sources) >= 1

    # Confirm the actual prompt sent included the SOURCES section with a
    # numbered marker, per RAG_SPEC.md §4's exact template.
    sent_body = responses.calls[0].request.body
    assert b"SOURCES:" in sent_body
    assert b"[1]" in sent_body


@responses.activate
def test_citation_resolves_correctly_when_the_answer_is_not_the_top_ranked_chunk(monkeypatch):
    """Regression test for a hypothesis raised about the "[N]" citation
    bug: that citation resolution "assumes the model's cited source is
    always the top-ranked chunk" and breaks when it isn't. Per code
    inspection, generation.py has NO rank-based citation logic at all —
    _format_sources numbers whatever grounding.chunks returns 1..N in
    THAT order (which happens to be rank order, but that's just a label,
    not an assumption about which one gets cited), and the LLM is free
    to cite any [1]-[N]. This test forces the correct-answer chunk to be
    at rank 3 (not rank 1) via a controlled, mocked grounding result, has
    the model correctly cite [3], and confirms it resolves exactly like
    citing [1] would — proving the hypothesis doesn't hold against the
    actual code path, with evidence rather than just an assertion.
    """
    import backend.retrieval.generation as generation_module
    from backend.retrieval.hybrid_search import RetrievedChunk
    from backend.retrieval.grounded_retrieval import GroundedRetrievalResult

    # Chunk order is deliberately NOT relevance order — the genuinely
    # correct answer (WABT) is planted at index 2 (rank 3), with two
    # unrelated-but-higher-scored chunks ahead of it.
    chunks = [
        RetrievedChunk(text="Unrelated content about depot correspondence.", source_document="a.docx", page_number=1, score=0.9),
        RetrievedChunk(text="Unrelated content about sulphur spec limits.", source_document="b.xlsx", page_number=1, score=0.8),
        RetrievedChunk(text="WABT end-of-run trigger is > 410 C.", source_document="SOP-114.docx", page_number=1, score=0.5),
    ]
    monkeypatch.setattr(
        generation_module,
        "retrieve_with_grounding_check",
        lambda store, query, top_k=5, **_: GroundedRetrievalResult(found=True, chunks=chunks),
    )

    responses.add(
        responses.POST,
        GENERATE_URL,
        json={"response": "The WABT end-of-run trigger temperature is > 410 C [3]."},
        status=200,
    )

    result = generation_module.generate_grounded_answer(_build_store([("x", "y.pdf")]), "What is the WABT trigger?")

    assert "[3]" in result.answer_text  # kept, not stripped as invalid
    assert result.invalid_citations_stripped == []
    assert result.unresolved_placeholders_stripped == 0
    # Position 3 (1-indexed) in the returned sources really is the
    # correct chunk -- proving the numbering genuinely tracks whichever
    # chunk the model cited, not an assumption that it's always #1.
    assert result.sources[2].source_document == "SOP-114.docx"


@responses.activate
def test_hallucinated_citation_number_is_stripped_from_the_final_answer():
    from backend.retrieval.generation import generate_grounded_answer

    responses.add(
        responses.POST,
        GENERATE_URL,
        json={"response": "The catalyst is fine [1] per the 2019 audit [9]."},
        status=200,
    )

    store = _build_store([("The hydrocracker catalyst is showing WABT creep.", "doc1.pdf")])

    result = generate_grounded_answer(store, "Is the catalyst fine?", top_k=1)

    assert "[9]" not in result.answer_text
    assert 9 in result.invalid_citations_stripped
