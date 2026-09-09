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
