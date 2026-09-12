"""Embedding generation — RAG_SPEC.md §2 step 5.

Exact model (BAAI/bge-large-en-v1.5), exact batch size (32), and
normalized embeddings are all specified precisely in RAG_SPEC.md — do not
substitute a different bge variant without updating DEPENDENCIES.md, and
do not skip normalization: FAISS's IndexFlatIP (RAG_SPEC.md §2 step 6)
computes plain inner product, which only equals cosine similarity when
every vector is unit-normalized first. Skip normalization and every
"similarity score" downstream is quietly wrong.
"""

from backend.ingestion.model_cache import force_offline_mode, require_cached

# MUST run before importing sentence_transformers/transformers — some of
# their Hub-reachability checks happen at import/construction time, not
# only when actually downloading a model. See model_cache.py.
force_offline_mode()

import numpy as np  # noqa: E402 — see force_offline_mode() ordering note above

MODEL_ID = "BAAI/bge-large-en-v1.5"

# Declared at module level because _get_model() does `global _model`.
# Without this the first call raises NameError — and since embed_texts
# caught every exception and fell through to the hash fallback, that
# NameError was SILENT: the real model was never loaded on ANY machine,
# including ones where it is cached. Measured after the merge that
# introduced it: two sentences with the same meaning and different words
# scored cosine 0.0000, because every vector in the system was a
# bag-of-words hash rather than an embedding.
_model = None

# Which backend actually produced the last vectors. Read this rather than
# assuming — the whole failure above was invisible precisely because
# nothing reported which embedder was running.
_active_backend = "uninitialised"

# Set only when a load has been ATTEMPTED and genuinely failed. This is
# what stops a retry on every single call when the model is absent,
# without coupling that decision to _active_backend.
#
# Keying the retry guard on _active_backend instead was a real bug:
# test_embeddings.py resets `_model = None` to force a fresh load (it is
# testing that construction performs no network access), but that left
# _active_backend still reading "bge-large-en-v1.5", so the reload branch
# was skipped, _get_model() returned None, and EVERY later test in the
# session silently got hash vectors. Two globals that must agree, where
# only one is reset, is a trap — so the retry decision now depends on the
# same variable a caller would reset.
_load_failed = False

SEMANTIC_BACKEND = "bge-large-en-v1.5"
FALLBACK_BACKEND = "deterministic-hash"


def reset_model_cache() -> None:
    """Force the next embed call to reload the model from scratch.

    Exists so a test can exercise a genuine construction (the operation
    that would touch the network, if anything did) without reaching into
    module globals and leaving them inconsistent.
    """
    global _model, _active_backend, _load_failed
    _model = None
    _active_backend = "uninitialised"
    _load_failed = False


def active_backend() -> str:
    """Which embedder is in use: SEMANTIC_BACKEND or FALLBACK_BACKEND.

    Load-bearing, not diagnostic. The hash fallback and the real model
    produce similarity scores on completely different scales, so every
    calibrated threshold downstream (the NFR-4 confidence gate, the image
    match floor) is only valid for one of them. A caller that cannot tell
    them apart cannot pick the right threshold.
    """
    if _active_backend == "uninitialised":
        _get_model()
    return _active_backend

def _deterministic_embed(texts: list[str], dim: int = 1024) -> np.ndarray:
    """Zero-download deterministic 1024-d unit-normalized dense embeddings.

    Projects token hashes and character n-grams to a 1024-dimensional space
    and L2-normalizes each row. Fully deterministic, 0 network downloads,
    and 100% compatible with FAISS IndexFlatIP(1024) and cosine similarity.
    """
    import hashlib

    vecs = np.zeros((len(texts), dim), dtype=np.float32)
    for row_idx, text in enumerate(texts):
        words = text.lower().split()
        if not words:
            vecs[row_idx, 0] = 1.0
            continue
        for i, w in enumerate(words):
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
            sign = 1.0 if (h & 1) else -1.0
            bucket = (h >> 1) % dim
            vecs[row_idx, bucket] += sign
            if i + 1 < len(words):
                bi = f"{w}_{words[i+1]}"
                h2 = int(hashlib.sha1(bi.encode("utf-8")).hexdigest()[:8], 16)
                sign2 = 1.0 if (h2 & 1) else -1.0
                bucket2 = (h2 >> 1) % dim
                vecs[row_idx, bucket2] += 0.5 * sign2
        norm = float(np.linalg.norm(vecs[row_idx]))
        if norm > 1e-6:
            vecs[row_idx] /= norm
        else:
            vecs[row_idx, 0] = 1.0
    return vecs


def _get_model():
    """Load the real embedding model, or return None if unavailable.

    Failure to load is reported ONCE, loudly. The previous version
    swallowed every exception silently, which is how a NameError in this
    very function went unnoticed while the entire system ran on hash
    vectors — a degradation invisible in every test that only checked
    vector SHAPE, since the fallback returns correctly-shaped garbage.
    """
    global _model, _active_backend, _load_failed
    if _model is None and not _load_failed:
        try:
            cache_dir = require_cached("embeddings", MODEL_ID)
            if cache_dir.exists() and any(cache_dir.iterdir()):
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(str(cache_dir), device=_embedding_device())
                _active_backend = SEMANTIC_BACKEND
            else:
                _load_failed = True
                _active_backend = FALLBACK_BACKEND
                _warn_fallback("the model directory is empty")
        except Exception as exc:  # noqa: BLE001 — reported, never hidden
            _model = None
            _load_failed = True
            _active_backend = FALLBACK_BACKEND
            _warn_fallback(f"{type(exc).__name__}: {exc}")
    return _model


def _embedding_device() -> str:
    """Where the embedding model runs: "cuda" when it can, else "cpu".

    WHY THIS IS EXPLICIT RATHER THAN LEFT TO THE DEFAULT.

    sentence-transformers does pick CUDA automatically when torch sees
    it, so on a correctly configured box this changes nothing. It is
    written down because for most of this project's life torch was the
    CPU-only build and this ran on the processor, and nothing in the
    code said so.

    The consequence was sustained 99% CPU spikes severe enough to make
    the whole desktop unresponsive. PyTorch defaults its thread pool to
    every physical core (measured: 24 of 24 here), every query embeds
    its text and every ingested document embeds every chunk, so ordinary
    use took the entire machine. Ollama was fine throughout -- it
    manages its own GPU placement -- which made it look as though the
    GPU was being used when the embedding half of the pipeline was not.

    Fixed by installing torch 2.9.1+cu126: the SAME version already
    present, only the CUDA build. Pinning the version is what matters --
    a previous attempt let versions drift and hit cascading
    torch/torchvision/torchao/triton conflicts in this shared,
    system-wide Python, and had to be reverted.

    Falls back to CPU rather than raising: an air-gapped venue machine
    may have no NVIDIA GPU at all, and slow embeddings are a great deal
    better than a workbench that will not start.

    Override with WORKBENCH_EMBEDDING_DEVICE (e.g. "cpu" to reproduce a
    CPU-only run, or "cuda:1" on a multi-GPU box).
    """
    import os

    override = os.environ.get("WORKBENCH_EMBEDDING_DEVICE")
    if override:
        return override

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def active_device() -> str:
    """The device the loaded model is actually on, for diagnostics.

    Reads it back off the model rather than recomputing the preference,
    so this reports what IS rather than what was intended -- the
    distinction that hid the CPU-only embeddings for so long.
    """
    if _model is None:
        return "not loaded"
    try:
        return str(next(_model.parameters()).device)
    except Exception:  # noqa: BLE001
        return _embedding_device()


def _warn_fallback(reason: str) -> None:
    """Say plainly that retrieval is degraded, once.

    Not a debug log. Running on hash vectors means the system cannot
    match a question to a passage that answers it in different words —
    which is the entire point of dense retrieval — and every downstream
    similarity threshold was calibrated for the real model.
    """
    import warnings

    warnings.warn(
        f"Embedding model unavailable ({reason}). Falling back to "
        f"{FALLBACK_BACKEND} vectors: these are bag-of-words hashes, NOT semantic "
        "embeddings. Retrieval will only match shared vocabulary, and every "
        "similarity threshold calibrated for bge-large is invalid. Run "
        "`python -m backend.ingestion.fetch_models` to restore semantic retrieval.",
        RuntimeWarning,
        stacklevel=3,
    )


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts with bge-large-en-v1.5 (or zero-download fallback).

    Returns an (n_texts, 1024) float32 array, L2-normalized per row.
    Never initiates an online model download.
    """
    if not texts:
        return np.empty((0, 1024), dtype=np.float32)

    global _active_backend

    model = _get_model()
    if model is not None:
        try:
            return model.encode(texts, batch_size=32, normalize_embeddings=True)
        except Exception as exc:  # noqa: BLE001
            # A model that loaded but cannot encode is a different failure
            # from one that never loaded, and silently degrading here
            # would hide it the same way. Report, then fall back so a
            # single bad batch does not take the pipeline down.
            _active_backend = FALLBACK_BACKEND
            _warn_fallback(f"encode failed: {type(exc).__name__}: {exc}")

    return _deterministic_embed(texts, dim=1024)

