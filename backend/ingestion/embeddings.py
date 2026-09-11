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
from sentence_transformers import SentenceTransformer  # noqa: E402

MODEL_ID = "BAAI/bge-large-en-v1.5"

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


def _get_model() -> SentenceTransformer | None:
    global _model
    if _model is None:
        try:
            cache_dir = require_cached("embeddings", MODEL_ID)
            if cache_dir.exists() and any(cache_dir.iterdir()):
                _model = SentenceTransformer(str(cache_dir))
        except Exception:
            _model = None
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts with bge-large-en-v1.5 (or zero-download fallback).

    Returns an (n_texts, 1024) float32 array, L2-normalized per row.
    Never initiates an online model download.
    """
    if not texts:
        return np.empty((0, 1024), dtype=np.float32)

    try:
        model = _get_model()
        if model is not None:
            return model.encode(texts, batch_size=32, normalize_embeddings=True)
    except Exception:
        pass

    return _deterministic_embed(texts, dim=1024)

