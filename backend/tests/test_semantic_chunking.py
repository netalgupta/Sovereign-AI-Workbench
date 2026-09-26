"""Tests for chunk_text_semantic.

Depends on the real bge-large-en-v1.5 cache (same as test_embeddings.py)
— no mocking of the embedding step, because the entire point being
tested is whether real embeddings actually detect a real topic shift.
"""


import pytest

from backend.ingestion import model_cache

pytestmark = pytest.mark.skipif(
    not model_cache.local_cache_dir("embeddings", "BAAI/bge-large-en-v1.5").exists(),
    reason=(
        "bge-large-en-v1.5 is not cached locally — run "
        "`python -m backend.ingestion.fetch_models --model bge-large-en-v1.5` "
        "once (with internet) before running this suite."
    ),
)

# Two genuinely distinct topics, back to back, so a real topic-shift
# boundary must exist between sentence 3 and sentence 4 — nothing about
# the FIRST group has anything to do with the SECOND.
_TWO_TOPIC_TEXT = (
    "The hydrocracker catalyst showed a gradual WABT creep over the last quarter. "
    "Engineers reviewed the deactivation trend against historical operating data. "
    "A catalyst change-out is being scheduled for the next planned turnaround. "
    "The Kasargod depot requested an updated weekly delivery schedule from HQ. "
    "Marketing confirmed the revised truck loading slots for next week. "
    "HQ approval is still pending for the Kasargod schedule change."
)


def test_semantic_chunking_separates_two_distinct_topics():
    from backend.ingestion.semantic_chunking import chunk_text_semantic

    chunks = chunk_text_semantic(_TWO_TOPIC_TEXT, breakpoint_percentile=70.0)

    assert len(chunks) >= 2
    # The hydrocracker sentences and the depot sentences must not both
    # appear in the SAME chunk — that would mean the "topic shift" was
    # missed entirely.
    hydrocracker_chunks = [c for c in chunks if "hydrocracker" in c.lower()]
    depot_chunks = [c for c in chunks if "kasargod" in c.lower()]
    assert hydrocracker_chunks
    assert depot_chunks
    assert not (set(hydrocracker_chunks) & set(depot_chunks))


def test_semantic_chunking_never_returns_a_chunk_over_the_locked_token_budget():
    from backend.ingestion.chunking import CHUNK_SIZE_TOKENS
    from backend.ingestion.semantic_chunking import chunk_text_semantic

    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")

    # A single long, topic-uniform passage (repeats one idea many times)
    # so semantic chunking would naturally want to keep it as ONE big
    # chunk — this is exactly the case the fixed-size safety net exists
    # to catch.
    long_uniform_text = " ".join(
        [f"Reactor temperature reading number {i} was within the normal band." for i in range(80)]
    )

    chunks = chunk_text_semantic(long_uniform_text, breakpoint_percentile=99.0)

    for chunk in chunks:
        assert len(encoding.encode(chunk)) <= CHUNK_SIZE_TOKENS


def test_single_sentence_falls_back_to_fixed_size_chunker():
    from backend.ingestion.semantic_chunking import chunk_text_semantic

    result = chunk_text_semantic("Just one sentence, nothing to split semantically.")

    assert result == ["Just one sentence, nothing to split semantically."]


def test_empty_text_returns_empty_list():
    from backend.ingestion.semantic_chunking import chunk_text_semantic

    assert chunk_text_semantic("") == []
    assert chunk_text_semantic("   ") == []
