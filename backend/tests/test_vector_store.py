"""Tests for VectorStore. Uses small synthetic vectors, not real
embeddings — this class never calls embed_texts itself (that's
hybrid_search.py's job), so testing it doesn't need the real model."""

import numpy as np
import pytest

from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
from backend.retrieval.vector_store import VectorStore


def _chunk(text: str, source: str = "doc.pdf", page: int | None = 1, index: int = 0) -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata=ChunkMetadata(
            source_document=source,
            document_type="pdf",
            page_number=page,
            chunk_index=index,
            ingestion_date="2026-09-09",
        ),
    )


def test_add_and_retrieve_by_faiss_id():
    store = VectorStore(dim=4)
    chunks = [_chunk("first chunk", index=0), _chunk("second chunk", index=1)]
    embeddings = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)

    store.add_chunks(chunks, embeddings)

    assert len(store) == 2
    first = store.get_by_faiss_id(0)
    assert first.text == "first chunk"
    assert first.source_document == "doc.pdf"
    second = store.get_by_faiss_id(1)
    assert second.text == "second chunk"


def test_faiss_ids_continue_across_multiple_add_calls():
    # start_id = index.ntotal BEFORE adding — this is what makes ids
    # stable across incremental ingestion instead of colliding.
    store = VectorStore(dim=2)
    store.add_chunks([_chunk("a", index=0)], np.array([[1.0, 0.0]], dtype=np.float32))
    store.add_chunks([_chunk("b", index=0)], np.array([[0.0, 1.0]], dtype=np.float32))

    assert store.get_by_faiss_id(0).text == "a"
    assert store.get_by_faiss_id(1).text == "b"
    assert len(store) == 2


def test_get_by_missing_faiss_id_returns_none():
    store = VectorStore(dim=2)
    assert store.get_by_faiss_id(999) is None


def test_mismatched_lengths_raise():
    store = VectorStore(dim=2)
    with pytest.raises(ValueError):
        store.add_chunks(
            [_chunk("only one chunk")], np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        )


def test_dense_search_finds_nearest_by_inner_product():
    store = VectorStore(dim=2)
    store.add_chunks(
        [_chunk("aligned with query", index=0), _chunk("orthogonal to query", index=1)],
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )

    results = store.dense_search(np.array([1.0, 0.0], dtype=np.float32), top_k=2)

    assert results[0][0] == 0  # the aligned vector ranks first
    assert results[0][1] > results[1][1]  # its score is strictly higher


def test_dense_search_on_empty_store_returns_empty_list():
    store = VectorStore(dim=2)
    assert store.dense_search(np.array([1.0, 0.0], dtype=np.float32), top_k=5) == []


def test_all_chunk_texts_ordered_by_faiss_id():
    store = VectorStore(dim=2)
    store.add_chunks(
        [_chunk("zebra", index=0), _chunk("apple", index=1)],
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )

    rows = store.all_chunk_texts()

    assert rows == [(0, "zebra"), (1, "apple")]


def test_empty_add_chunks_is_a_safe_noop():
    store = VectorStore(dim=2)
    store.add_chunks([], np.zeros((0, 2), dtype=np.float32))
    assert len(store) == 0
