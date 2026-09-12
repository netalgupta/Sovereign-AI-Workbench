"""Tests for the HTTP surface.

Two things these protect that are easy to regress:

  * every route stays OFFLINE — CLAUDE.md hard constraint #1. The
    FastAPI default docs page pulls Swagger UI from a CDN at page load,
    which is a real phone-home in a system whose whole premise is that it
    has none, so it is disabled and a test says so.
  * responses declare their PROVENANCE. Corpus data can come from a live
    ingestion or an exported snapshot, and those disagree once the
    snapshot ages. Silently serving a stale export as live data is the
    same class of mistake as citing a document that has since changed.
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_reports_each_dependency_not_just_ok():
    """On an air-gapped box the useful question is not "is the API up"
    but "is Neo4j up, has anything been ingested" — a UI that knows can
    explain an empty screen instead of just showing one."""
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    for key in (
        "graph_available", "corpus_loaded", "snapshot_available",
        "images_stored", "documents_registered", "watched_sources",
    ):
        assert key in body


def test_cdn_backed_docs_are_disabled():
    """FastAPI's default /docs fetches Swagger UI from cdn.jsdelivr.net.
    That is an outbound request on page load, in a system that must make
    none."""
    assert app.docs_url is None
    assert app.redoc_url is None
    assert client.get("/docs").status_code == 404


def test_cors_is_restricted_to_local_origins():
    """Frontend and backend run on the same machine, so there is never a
    legitimate cross-origin caller from anywhere else."""
    origins = [
        m.kwargs["allow_origins"]
        for m in app.user_middleware
        if "allow_origins" in getattr(m, "kwargs", {})
    ]
    assert origins, "expected CORS middleware to be configured"
    for origin in origins[0]:
        assert "localhost" in origin or "127.0.0.1" in origin


def test_graph_returns_nodes_and_declares_its_source():
    body = client.get("/api/graph").json()

    assert body["source"] in ("live", "snapshot")
    assert isinstance(body["nodes"], list)
    assert isinstance(body["relationships"], list)


def test_chunks_default_to_the_snapshot_rather_than_a_multi_minute_ingest():
    """A request that silently triggered a full corpus ingestion would
    time out and look like a hang."""
    from backend.api.state import reset_state
    reset_state()
    body = client.get("/api/chunks").json()

    assert body["source"] == "snapshot"
    assert body["chunks"]
    assert body["chunking"]["chunk_size_tokens"] == 512


def test_metrics_carry_when_they_were_measured():
    """This project has three times been misled by an artifact that
    outlived the code that produced it. A dashboard must be able to show
    that a number is older than the change it is being used to judge."""
    body = client.get("/api/metrics").json()

    present = {k: v for k, v in body.items() if v}
    assert present, "expected at least one measured result on disk"
    for value in present.values():
        assert "measured_at" in value
        assert "data" in value


def test_images_list_does_not_inline_pixels():
    """Fifteen charts is ~3MB of base64 if inlined, for a grid that only
    needs thumbnails on demand."""
    body = client.get("/api/images").json()

    assert body["source"] in ("live", "snapshot", "empty")
    for image in body["images"]:
        if body["source"] == "live":
            assert "data_uri" not in image
            assert image["url"].endswith("/raw")


def test_image_bytes_round_trip_when_the_store_has_any():
    listing = client.get("/api/images").json()
    if listing["source"] != "live" or not listing["images"]:
        return  # nothing stored on this machine yet; covered by test_image_store

    image_id = listing["images"][0]["image_id"]
    response = client.get(f"/api/images/{image_id}/raw")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 0


def test_unknown_image_is_404_not_an_empty_200():
    assert client.get("/api/images/" + "0" * 64 + "/raw").status_code == 404


def test_sources_lists_watched_documents_and_queue():
    body = client.get("/api/sources").json()

    assert set(body) == {"watched", "documents", "queue"}
    assert "pending" in body["queue"]


def test_adding_a_nonexistent_source_is_a_400_not_a_crash():
    response = client.post("/api/sources", json={"path": "Z:/definitely/not/here"})
    assert response.status_code == 400


def test_preview_of_an_unregistered_document_is_404_with_a_useful_message():
    response = client.get("/api/preview", params={"document": "nope.pdf", "page": 1})

    assert response.status_code == 404
    assert "registered" in response.json()["detail"]
