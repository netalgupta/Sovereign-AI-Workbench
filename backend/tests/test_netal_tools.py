"""Netal's four tools — rows 16, 18, 32, 60.

Every test here calls the tool THROUGH THE REGISTRY, the way the
orchestrator does. That is deliberate: all four shipped raising
ImportError on their first line of real work, because they imported
`get_vector_store` from backend.retrieval.vector_store, which does not
exist and never has. Nothing caught it, because nothing ever called
them.

A tool the orchestrator cannot execute is not a tool. These tests are
the thing that makes that statement checkable.
"""

import pytest

from backend.tools import catalog  # noqa: F401 - registers everything
from backend.tools.registry import all_tools, call_tool

NETAL_TOOLS = [
    ("get_document_revision", {"document_name": "SOP-114"}),
    ("summarise_correspondence", {"document_or_query": "Kasargod depot tank calibration"}),
    ("graph_analytics", {"metric": "degree"}),
    ("summarise_depot_correspondence", {"location": "Kasargod"}),
]


def _registered() -> set[str]:
    registry = all_tools()
    return set(registry) if isinstance(registry, dict) else {t.name for t in registry}


@pytest.mark.parametrize("name,arguments", NETAL_TOOLS)
def test_the_tool_is_registered(name, arguments):
    assert name in _registered()


@pytest.mark.parametrize("name,arguments", NETAL_TOOLS)
def test_the_tool_actually_executes(name, arguments):
    """The test that was missing.

    Each of these raised ImportError on a name that does not exist. The
    registry happily listed them, the schemas derived correctly from the
    type hints, and `/api/tools` showed all four -- everything looked
    right except calling them.
    """
    result = call_tool(name, arguments)
    assert isinstance(result, dict), f"{name} returned {type(result).__name__}"


@pytest.mark.parametrize("name,arguments", NETAL_TOOLS)
def test_the_tool_reports_absence_rather_than_raising(name, arguments):
    """An empty or unreachable corpus is a normal condition, not an
    error. A tool that raises takes the whole turn down; one that says
    "not found" leaves the agent able to try something else."""
    result = call_tool(name, arguments)
    # Every one of these returns a dict carrying its own status field.
    assert any(
        key in result for key in ("found", "source", "locations_covered", "note")
    ), f"{name} returned no status field: {sorted(result)[:6]}"


def test_revision_tracking_finds_a_real_revision():
    """Row 16's actual job: is the SOP I am about to cite current?

    Citing a superseded revision of a safety procedure is a compliance
    failure, which is why this tool exists rather than being folded into
    ordinary retrieval.
    """
    result = call_tool("get_document_revision", {"document_name": "SOP-114"})
    if not result.get("found"):
        pytest.skip("SOP-114 is not in the loaded corpus on this machine")
    assert result["revisions"], "found a document but no revision information"
    assert any(r.get("revision") for r in result["revisions"])


def test_graph_analytics_reads_in_process_not_over_http():
    """It used to urlopen http://127.0.0.1:8000/api/graph -- the server
    asking itself a question.

    That deadlocks on a single-worker server, fails whenever the tool is
    called from a test or script with no server running (which is how it
    is being called right now), and makes a local tool read like a
    network call in a product whose whole claim is that it makes none.
    """
    import backend.tools.netal_tools as module

    source = module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()

    # Allowed in comments explaining the history; not as an import.
    assert "import urllib.request" not in text, (
        "a network client is imported in a backend tool"
    )

    result = call_tool("graph_analytics", {"metric": "degree"})
    assert result["source"] in ("live", "snapshot", "unavailable")
    if result["source"] != "unavailable":
        assert result["node_count"] > 0
        assert result["top_nodes"], "a populated graph produced no ranking"


def test_all_chunk_records_carries_metadata_and_is_cache_invalidated():
    """The accessor these tools needed and did not have.

    all_chunk_texts() returns (faiss_id, text) for BM25. Anything
    filtering by SOURCE needs the metadata, and get_by_faiss_id() in a
    loop is one query per chunk.
    """
    import numpy as np

    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
    from backend.retrieval.vector_store import VectorStore

    def make(n, offset=0):
        chunks = [
            IngestedChunk(
                text=f"chunk {i + offset}",
                metadata=ChunkMetadata(
                    source_document=f"doc{i + offset}.pdf",
                    document_type="pdf",
                    page_number=1,
                    chunk_index=i + offset,
                    ingestion_date="2026-01-01",
                ),
            )
            for i in range(n)
        ]
        return chunks, np.random.rand(n, 8).astype("float32")

    store = VectorStore(dim=8)
    store.add_chunks(*make(3))

    records = store.all_chunk_records()
    assert len(records) == 3
    assert records[0]["source_document"] == "doc0.pdf"
    assert records[0]["text"] and records[0]["page_number"] == 1

    assert store.all_chunk_records() is records, "the corpus was re-read unchanged"

    store.add_chunks(*make(2, offset=3))
    assert len(store.all_chunk_records()) == 5, "a stale record view survived ingest"
