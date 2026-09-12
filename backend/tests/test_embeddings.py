"""Tests for embed_texts — offline-only embedding generation.

No mocking here: this test suite requires the real bge-large-en-v1.5
cache produced by `fetch_models.py` to be present (it is, after the
one-time fetch step). That's a deliberate choice — mocking the embedding
model itself would only prove our own mock behaves as expected, not that
offline loading of the real model actually works. If the cache genuinely
isn't present, these skip with an actionable reason rather than failing
mysteriously.
"""

import os

import numpy as np
import pytest

from backend.ingestion import model_cache

_CACHE_PRESENT = model_cache.local_cache_dir(
    "embeddings", "BAAI/bge-large-en-v1.5"
).exists()

pytestmark = pytest.mark.skipif(
    not _CACHE_PRESENT,
    reason=(
        "bge-large-en-v1.5 is not cached locally — run "
        "`python -m backend.ingestion.fetch_models --model bge-large-en-v1.5` "
        "once (with internet) before running this suite."
    ),
)


def test_embed_texts_never_touches_network_env_flags():
    # Importing the module must have forced offline mode as a side
    # effect, unconditionally — this is the actual mechanism that
    # prevents a runtime network call, not just a docstring promise.
    from backend.ingestion import embeddings  # noqa: F401  (import triggers force_offline_mode)

    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"


def test_embed_texts_returns_correct_shape_and_dtype():
    from backend.ingestion.embeddings import embed_texts

    vectors = embed_texts(["hydrocracker catalyst deactivation", "unrelated sentence"])

    assert vectors.shape == (2, 1024)  # bge-large-en-v1.5's native dimension
    assert vectors.dtype == np.float32


def test_embeddings_are_l2_normalized():
    # RAG_SPEC.md §2 step 5 requires normalize_embeddings=True, because
    # FAISS's IndexFlatIP (§2 step 6) is a plain inner product — it only
    # behaves as cosine similarity when every vector has unit norm.
    from backend.ingestion.embeddings import embed_texts

    vectors = embed_texts(["a test sentence about pipeline maintenance"])

    norm = np.linalg.norm(vectors[0])
    assert norm == pytest.approx(1.0, abs=1e-4)


def test_embed_texts_works_with_sockets_hard_blocked(monkeypatch):
    """CLAUDE.md's testing expectations: prove offline by actually
    blocking network access, not just by checking an env var was set —
    an env var is a promise, a blocked socket that still succeeds is
    proof. Any attempt to open an outbound connection during this test
    raises immediately; embed_texts must complete anyway.

    Deliberately forces a FRESH model load (resets the module-level
    cache) rather than reusing whatever another test already loaded —
    the risky operation is model *construction* (that's where a Hub-
    reachability check would fire), not re-encoding with an
    already-resident model. A cache hit here would prove nothing.
    """
    import socket

    from backend.ingestion import embeddings

    embeddings._model = None  # force a real reload under the block

    def _blocked(*args, **kwargs):
        raise AssertionError("embed_texts attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    vectors = embeddings.embed_texts(["this must work with sockets blocked"])

    assert vectors.shape == (1, 1024)


def test_similar_sentences_score_higher_than_unrelated_ones():
    from backend.ingestion.embeddings import embed_texts

    query, similar, unrelated = embed_texts(
        [
            "catalyst deactivation trend in the hydrocracker",
            "WABT creep is a sign the hydrocracker catalyst is deactivating",
            "the marketing depot in Kasargod needs a new delivery schedule",
        ]
    )

    # Both vectors are unit-normalized, so a plain dot product IS cosine
    # similarity here — same operation FAISS's IndexFlatIP performs.
    sim_to_similar = float(np.dot(query, similar))
    sim_to_unrelated = float(np.dot(query, unrelated))

    assert sim_to_similar > sim_to_unrelated


def test_a_failed_load_is_retried_not_abandoned_forever():
    """A transient failure must not degrade the process permanently.

    `_load_failed = True` used to be set once and never cleared, so a
    single error disabled semantic retrieval for the lifetime of the
    process. It happened for real: the server was running while a CUDA
    torch install replaced torch's DLLs, one load failed mid-swap, and
    every query afterwards silently used hash vectors.

    The effect was total and invisible. Asked for "assignments and tasks
    for advay", retrieval returned two other people's files and the
    answer described a third person. Every vector still had the right
    shape, every search still returned results, every answer still had
    citations.
    """
    import time

    from backend.ingestion import embeddings

    original_model = embeddings._model
    original_failed = embeddings._load_failed
    original_at = embeddings._last_failure_at
    try:
        # Simulate a failure that happened just now.
        embeddings._model = None
        embeddings._load_failed = True
        embeddings._last_failure_at = time.time()

        # Inside the backoff window: does not hammer the loader.
        assert embeddings._get_model() is None

        # Past the window: retries rather than staying degraded.
        embeddings._last_failure_at = time.time() - embeddings._RETRY_AFTER_SECONDS - 1
        model = embeddings._get_model()
        assert model is not None, (
            "a failed load must be retried after the backoff window, not "
            "abandoned for the lifetime of the process"
        )
        assert embeddings.active_backend() == embeddings.SEMANTIC_BACKEND
    finally:
        embeddings._model = original_model
        embeddings._load_failed = original_failed
        embeddings._last_failure_at = original_at


def test_degradation_is_reportable():
    """Degraded retrieval must be visible, not inferable from one log line.

    The only evidence of a whole session running on hash vectors was a
    trace line reading "embedding backend: deterministic-hash" among
    hundreds of others. /api/health and the per-turn trace now both
    report it.
    """
    from backend.ingestion import embeddings

    original = embeddings._active_backend
    try:
        embeddings._active_backend = embeddings.SEMANTIC_BACKEND
        assert embeddings.degraded_reason() is None

        embeddings._active_backend = embeddings.FALLBACK_BACKEND
        reason = embeddings.degraded_reason()
        assert reason, "a degraded backend must explain itself"
        assert "hash" in reason.lower()
    finally:
        embeddings._active_backend = original
