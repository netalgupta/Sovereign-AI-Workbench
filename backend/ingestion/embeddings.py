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

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        cache_dir = require_cached("embeddings", MODEL_ID)
        # Loading FROM THE LOCAL PATH (not the hub id "BAAI/...") is what
        # makes this a filesystem read instead of a network lookup.
        _model = SentenceTransformer(str(cache_dir))
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts with bge-large-en-v1.5.

    Returns an (n_texts, 1024) float32 array, L2-normalized per row.
    """
    model = _get_model()
    return model.encode(texts, batch_size=32, normalize_embeddings=True)
