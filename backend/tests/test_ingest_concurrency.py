"""Regressions from adding one large folder while the Sources page was open.

Each was MEASURED on a real 195-file folder before it was fixed:

  * every document indexed twice -- 6,797 chunks, 3,523 distinct
  * /api/chunks never returning, then IndexError on a list that grew
    mid-request
  * the whole API segfaulting (exit 139) when a read of the FAISS index
    raced an ingest adding to it
  * the progress tracker matching documents by bare filename
  * /api/health stalling 4.1s every twenty seconds with Neo4j down

No model is loaded here: embeddings are faked, because what is under
test is the concurrency and bookkeeping around them.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from backend.api.state import PipelineState
from backend.retrieval.vector_store import VectorStore


def _fake_embed(texts):
    rng = np.random.default_rng(len(texts))
    v = rng.normal(size=(len(texts), 1024)).astype("float32")
    return v / np.linalg.norm(v, axis=1, keepdims=True)


class _NullRegistry:
    def register(self, *_a, **_k):
        return None


@pytest.fixture
def state(monkeypatch):
    """A PipelineState with an in-memory store and no disk side effects."""
    import backend.ingestion.embeddings as embeddings

    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed)
    monkeypatch.setenv("WORKBENCH_AUTO_EXTRACT_GRAPH", "0")
    monkeypatch.setattr(PipelineState, "registry", property(lambda self: _NullRegistry()))
    monkeypatch.setattr(PipelineState, "_write_corpus_cache", lambda self, chunks: None)

    s = PipelineState()
    s._store = VectorStore(dim=1024)
    s._chunks = []
    return s


def _docs(tmp_path: Path, n: int) -> list[Path]:
    files = []
    for i in range(n):
        f = tmp_path / f"doc_{i}.txt"
        f.write_text(f"Inspection note {i}: exchanger E-{100 + i} fouling observed.", encoding="utf-8")
        files.append(f)
    return files


def test_concurrent_ingests_of_the_same_files_index_each_file_once(state, tmp_path):
    """The measured failure: two ingests of one folder both added it."""
    files = _docs(tmp_path, 6)
    threads = [threading.Thread(target=state.ingest_files, args=(files,)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    names = [c.metadata.source_document for c in state._chunks]
    assert sorted(names) == sorted(f.name for f in files), "a file was indexed more than once"
    assert len(state._store) == len(state._chunks)


def test_reingesting_an_indexed_file_is_reported_as_skipped(state, tmp_path):
    files = _docs(tmp_path, 2)
    state.ingest_files(files)
    added, details = state.ingest_files(files)

    assert added == 0
    assert all(d.get("skipped") == "already indexed" for d in details)
    assert len(state._chunks) == 2


def test_a_different_file_with_an_indexed_name_is_still_indexed(state, tmp_path):
    """Skipping on bare filename skipped a DIFFERENT file that shared a
    name with one already indexed (caught by test_sources_ingest_endpoint)."""
    a = tmp_path / "a" / "notes.txt"
    b = tmp_path / "b" / "notes.txt"
    for f, body in ((a, "Exchanger E-101 fouling."), (b, "Pump P-HS-02 seal leak.")):
        f.parent.mkdir()
        f.write_text(body, encoding="utf-8")

    state.ingest_files([a])
    added, _ = state.ingest_files([b])
    again, _ = state.ingest_files([b])

    assert added >= 1
    assert again == 0


def test_reading_vectors_while_ingesting_does_not_crash(state, tmp_path):
    """Segfaulted the API before the store had a lock. A crash here takes
    the test process down rather than failing an assertion, which is
    itself the signal."""
    files = _docs(tmp_path, 40)
    errors: list[BaseException] = []
    done = threading.Event()

    def reader():
        while not done.is_set():
            try:
                n = len(state._chunks)
                state._store.vectors(n)
                state._store.dense_search(_fake_embed(["q"])[0], top_k=3)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
                return

    r = threading.Thread(target=reader)
    r.start()
    for f in files:  # one add per file, like a folder ingest
        state.ingest_files([f])
    done.set()
    r.join(timeout=30)

    assert not errors, errors
    assert len(state._store) == 40


def test_deleting_a_source_keeps_vectors_aligned_with_chunks(state, tmp_path, monkeypatch):
    """Delete used to drop chunks from the list but leave every vector in
    FAISS, so position i no longer meant chunk i -- and LIKE '%name%'
    also removed other documents whose names contained this one."""
    monkeypatch.setattr(type(state), "watcher", property(lambda self: type("W", (), {"remove_source": lambda *_: None})()))
    notes = tmp_path / "notes.txt"
    old_notes = tmp_path / "old_notes.txt"
    keep = tmp_path / "keep.txt"
    for f, body in ((notes, "Delete me."), (old_notes, "Similar name, keep me."), (keep, "Keep me too.")):
        f.write_text(body, encoding="utf-8")
    state.ingest_files([notes, old_notes, keep])
    before = {c.metadata.source_document: state._store.vectors(len(state._chunks))[i].copy()
              for i, c in enumerate(state._chunks)}

    result = state.delete_source(str(notes))

    names = [c.metadata.source_document for c in state._chunks]
    assert result["chunks_removed"] == 1
    assert names == ["old_notes.txt", "keep.txt"]
    assert len(state._store) == len(state._chunks)
    after = state._store.vectors(len(state._chunks))
    for i, name in enumerate(names):
        assert np.allclose(after[i], before[name]), f"{name} is paired with another chunk's vector"


def test_store_vectors_returns_what_was_added():
    store = VectorStore(dim=1024)
    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

    vecs = _fake_embed(["a", "b", "c"])
    chunks = [
        IngestedChunk(text=t, metadata=ChunkMetadata(
            source_document="d.txt", document_type="txt", page_number=1,
            chunk_index=i, ingestion_date="2026-09-16", image_ids=[]))
        for i, t in enumerate("abc")
    ]
    store.add_chunks(chunks, vecs)

    assert np.allclose(store.vectors(3), vecs)
    assert store.vectors(4) is None, "must not pretend to hold vectors it does not"


# --------------------------------------------------------------- /api/chunks


def test_nearest_neighbours_match_the_full_matrix():
    from backend.api.routes import _nearest_neighbours

    v = _fake_embed(["x"] * 700)  # crosses the 512-row block boundary
    got = _nearest_neighbours(v, k=5)
    full = v @ v.T
    for i in (0, 511, 512, 699):
        row = full[i].copy()
        row[i] = -np.inf
        expected = list(np.argsort(-row)[:5])
        assert [j for j, _ in got[i]] == expected
        assert i not in [j for j, _ in got[i]], "a chunk is not its own neighbour"


def test_chunks_endpoint_omits_the_matrix_above_the_limit_and_says_why(state, monkeypatch, tmp_path):
    import backend.api.routes as routes

    monkeypatch.setattr(routes, "SIMILARITY_MATRIX_MAX_CHUNKS", 4)
    monkeypatch.setattr(routes, "get_state", lambda: state)
    monkeypatch.setattr(PipelineState, "snapshot", lambda self: None)
    state.ingest_files(_docs(tmp_path, 6))

    data = routes.get_chunks(live=True)

    assert data["similarity"] == []
    assert data["similarity_omitted"]["chunk_count"] == 6
    assert "too large" in data["similarity_omitted"]["reason"]
    assert all(len(c["neighbours"]) == 5 for c in data["chunks"])


def test_chunks_endpoint_serves_the_matrix_below_the_limit(state, monkeypatch, tmp_path):
    import backend.api.routes as routes

    monkeypatch.setattr(routes, "get_state", lambda: state)
    monkeypatch.setattr(PipelineState, "snapshot", lambda self: None)
    state.ingest_files(_docs(tmp_path, 3))

    data = routes.get_chunks(live=True)

    assert len(data["similarity"]) == 3
    assert data["similarity_omitted"] is None


def test_corpus_chunk_count_is_null_when_unknown_never_estimated(monkeypatch):
    """It was `files x 8` -- a number nobody measured, shown as indexed."""
    import backend.api.routes as routes

    s = PipelineState()
    monkeypatch.setattr(routes, "get_state", lambda: s)
    data = routes._get_corpus_data()

    assert data["chunkCount"] is None


# ----------------------------------------------------------- progress tracker


def test_progress_does_not_confuse_same_named_files_in_different_folders(tmp_path):
    from backend.ingestion.ingestion_progress import DocumentStage, ProgressTracker

    a = tmp_path / "a" / "README.md"
    b = tmp_path / "b" / "README.md"
    for f in (a, b):
        f.parent.mkdir()
        f.write_text("x", encoding="utf-8")

    tracker = ProgressTracker()
    job = tracker.create(str(tmp_path), [a, b])
    tracker.set_stage(job.job_id, str(b), DocumentStage.INDEXED, chunks=1)

    stages = {d.path: d.stage for d in tracker.get(job.job_id).documents}
    assert stages[str(b)] is DocumentStage.INDEXED
    assert stages[str(a)] is not DocumentStage.INDEXED


def test_progress_matches_the_same_path_spelled_differently(tmp_path):
    from backend.ingestion.ingestion_progress import DocumentStage, ProgressTracker

    f = tmp_path / "Doc.txt"
    f.write_text("x", encoding="utf-8")
    tracker = ProgressTracker()
    job = tracker.create(str(tmp_path), [f])
    tracker.set_stage(job.job_id, str(f).upper(), DocumentStage.INDEXED)

    assert tracker.get(job.job_id).documents[0].stage is DocumentStage.INDEXED


# ---------------------------------------------------------------- health


def test_expired_graph_failure_is_answered_without_waiting_for_a_probe(monkeypatch):
    import backend.evaluation.export_inspection_data as export

    def slow_down_probe(*_a, **_k):
        time.sleep(2.0)  # stands in for the 4.1s Neo4j connect timeout
        return {"available": False, "error": "down"}

    monkeypatch.setattr(export, "export_graph", slow_down_probe)
    s = PipelineState()
    s._graph_failure = ({"available": False, "error": "down"}, time.time() - 999)

    t0 = time.perf_counter()
    result = s.graph()
    elapsed = time.perf_counter() - t0

    assert result["available"] is False
    assert elapsed < 0.5, f"health waited {elapsed:.1f}s on a graph probe"
