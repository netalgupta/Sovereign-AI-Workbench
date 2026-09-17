"""Tests for document ingestion, chunking, embedding, and sources API endpoints.

Covers:
  - POST /api/chunk
  - POST /api/embed
  - POST /api/sources/upload
  - POST /api/sources/ingest
  - POST /api/sources
  - GET /api/chunks
  - DELETE /api/sources
"""

import base64
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def preserve_configured_sources():
    sources_file = Path("backend/evaluation/configured_sources.json")
    original = sources_file.read_text(encoding="utf-8") if sources_file.exists() else None
    yield
    if original is not None:
        sources_file.write_text(original, encoding="utf-8")


def test_chunk_endpoint():
    """POST /api/chunk splits text into ~512-token chunks with 64-token overlap."""
    sample_text = (
        "Hydrocracker unit 44 emergency shutdown protocol. "
        "In the event of a sudden loss of cooling water to E-201, "
        "operators must immediately reduce hydrocarbon feed rate to 50% "
        "and initiate depressurization to the flare system. "
    ) * 25  # ~500 words to test tokenization

    res = client.post("/api/chunk", json={"text": sample_text, "source_document": "sop-44.txt"})
    assert res.status_code == 200
    data = res.json()
    assert "chunks" in data
    assert data["count"] >= 1
    assert data["chunk_size_tokens"] == 512
    assert data["chunk_overlap_tokens"] == 64
    assert data["encoding"] == "cl100k_base"
    assert isinstance(data["chunks"], list)
    assert len(data["chunks"][0]) > 0


def test_embed_endpoint():
    """POST /api/embed produces 1024-dimensional normalized dense vectors."""
    texts = [
        "Hydrocracker reactor bed temperature gradient exceeds 15 C.",
        "Crude distillation column overhead accumulator pressure steady at 2.4 bar.",
    ]
    res = client.post("/api/embed", json={"texts": texts})
    assert res.status_code == 200
    data = res.json()
    assert "embeddings" in data
    assert data["count"] == 2
    assert data["dim"] == 1024

    # Assert unit normalization
    vecs = np.array(data["embeddings"], dtype=np.float32)
    assert vecs.shape == (2, 1024)
    for v in vecs:
        norm = np.linalg.norm(v)
        assert pytest.approx(norm, abs=1e-3) == 1.0


def test_sources_upload_endpoint(tmp_path):
    """POST /api/sources/upload saves file to 07_User_Uploads and indexes into FAISS."""
    content = "Pump P-HS-02 vibration level monitored on Mangalore-Hassan segment."
    b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "files": [
            {
                "name": "test_pump_log.txt",
                "relPath": "test_pump_log.txt",
                "contentBase64": b64_content,
                "sizeBytes": len(content),
            }
        ]
    }

    target = Path("MRPL_RAG_Test_Corpus") / "07_User_Uploads" / "test_pump_log.txt"
    # A leftover from an interrupted run would be skipped as already
    # indexed, which is correct behaviour and not what this test checks.
    client.delete("/api/sources", params={"path": str(target)})

    res = client.post("/api/sources/upload", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["count"] == 1

    # Ingestion runs in the background now, so "indexed" is checked on
    # the JOB, not assumed from a 200. A response that returns before
    # the work is done proves nothing about the work.
    import time

    deadline = time.time() + 120
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/ingestion/{data['job_id']}").json()
        if job.get("state") in ("complete", "failed"):
            break
        time.sleep(0.5)
    assert job and job["state"] == "complete", job
    docs = [d for d in job["documents"] if d["name"] == "test_pump_log.txt"]
    assert len(docs) == 1
    assert docs[0]["stage"] == "indexed", docs[0]
    assert docs[0]["chunks"] >= 1

    # Verify file exists on disk in 07_User_Uploads
    assert target.exists()

    # Clean up test artifact from disk
    try:
        client.delete("/api/sources", params={"path": str(target)})
    except Exception:
        pass


def test_sources_ingest_endpoint(tmp_path):
    """POST /api/sources/ingest indexes a specific file on disk."""
    import uuid

    # A UNIQUE name. This endpoint indexes into the real corpus, which is
    # cached on disk across runs, and a file already indexed is skipped
    # rather than duplicated -- so a fixed name passes once and then
    # correctly reports 0 new chunks on every later run.
    name = f"sop_test_procedure_{uuid.uuid4().hex[:8]}.txt"
    test_file = tmp_path / name
    test_file.write_text("SOP 901: Nitrogen purging of reactor vessel R-101 before catalyst load.")

    res = client.post("/api/sources/ingest", json={"path": str(test_file)})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["total_chunks"] >= 1
    assert len(data["documents"]) == 1
    assert data["documents"][0]["filename"] == name


def test_sources_add_folder_and_list(tmp_path):
    """POST /api/sources watches a folder and immediately chunks and embeds its contents."""
    doc_dir = tmp_path / "watched_docs"
    doc_dir.mkdir()
    doc_file = doc_dir / "sample_flow_rate.txt"
    doc_file.write_text("Flow rate indicator FI-102 reading 450 m3/h at crude feed pump.")

    res = client.post("/api/sources", json={"path": str(doc_dir), "recursive": True})
    assert res.status_code == 200
    data = res.json()
    assert "source" in data or "total_chunks" in data or "watched" in data

    # Verify listing shows in /api/sources
    list_res = client.get("/api/sources")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "watched" in list_data
    assert "documents" in list_data


def test_get_chunks_live_with_pca():
    """GET /api/chunks?live=true returns live chunks with 2D PCA coordinates and similarity."""
    res = client.get("/api/chunks?live=true")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "live"
    assert "chunking" in data
    assert "embedding_dim" in data
    assert data["embedding_dim"] == 1024
    assert "pca_explained_variance" in data
    assert "chunks" in data
    assert "similarity" in data

    if data["chunks"]:
        first_chunk = data["chunks"][0]
        assert "x" in first_chunk
        assert "y" in first_chunk
        assert "text" in first_chunk
        assert "source_document" in first_chunk
