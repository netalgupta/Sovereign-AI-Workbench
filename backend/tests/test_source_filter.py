"""The Sources panel's toggles, end to end.

The panel carries the line "This session is grounded only in the sources
listed here". That is a promise, and it is only true if the toggle
reaches retrieval. Three states, and all three are distinct:

    None   no filter supplied  -> search everything
    []     the user switched everything off -> refuse, and say so
    [...]  search only these

Collapsing None into [] is the bug this file exists to catch: the
frontend store starts empty and is only filled once /api/corpus
resolves, so a message sent before that told the backend every source
was off. The user then sees "you have disabled all sources" having
touched nothing.
"""

import pytest

from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
from backend.retrieval.vector_store import VectorStore


@pytest.fixture
def store():
    import numpy as np

    from backend.ingestion.embeddings import embed_texts

    texts = {
        "Hydrocracker_SOP.pdf": "The hydrocracker catalyst changeout procedure "
                                "requires reactor isolation before bed removal.",
        "Maintenance_Log.xlsx": "Pump P-101 was overhauled in August after a "
                                "seal failure caused downtime.",
    }
    chunks = [
        IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document=name,
                document_type="pdf",
                page_number=1,
                chunk_index=0,
                ingestion_date="2026-01-01",
            ),
        )
        for name, text in texts.items()
    ]
    embeddings = np.asarray(embed_texts([c.text for c in chunks]), dtype="float32")
    vector_store = VectorStore(dim=embeddings.shape[1])
    vector_store.add_chunks(chunks, embeddings)
    return vector_store


def test_no_filter_searches_everything(store):
    result = retrieve_with_grounding_check(
        store, "hydrocracker catalyst changeout procedure", top_k=5, active_documents=None
    )
    assert result.found
    assert any(c.source_document == "Hydrocracker_SOP.pdf" for c in result.chunks)


def test_an_empty_selection_refuses_and_explains_itself(store):
    """[] is a real instruction, not a missing one. It must refuse -- and
    the refusal has to say WHY, or it reads as the product being
    broken."""
    result = retrieve_with_grounding_check(
        store, "hydrocracker catalyst changeout procedure", top_k=5, active_documents=[]
    )
    assert not result.found
    assert result.chunks == []
    assert result.reason, "an empty selection refused without saying why"


def test_a_filter_excludes_rather_than_hides(store):
    """Toggling a source off was once pure client-side React state, so an
    excluded document kept appearing in citations and kept grounding
    answers. Exclusion has to happen in retrieval."""
    result = retrieve_with_grounding_check(
        store,
        "hydrocracker catalyst changeout procedure",
        top_k=5,
        active_documents=["Maintenance_Log.xlsx"],
    )
    for chunk in result.chunks:
        assert chunk.source_document == "Maintenance_Log.xlsx", (
            "a disabled document was still retrieved"
        )


def test_the_stream_endpoint_defaults_to_no_filter_not_an_empty_one():
    """AgentStreamRequest must default active_documents to None.

    A default of [] would mean every client that omits the field is
    telling the backend the user deselected everything.
    """
    from backend.api.routes import AgentStreamRequest

    body = AgentStreamRequest(message="hello")
    assert body.active_documents is None, (
        "omitting the field must mean 'no filter', never 'everything off'"
    )

    assert AgentStreamRequest(message="x", active_documents=[]).active_documents == []
    assert AgentStreamRequest(
        message="x", active_documents=["a.pdf"]
    ).active_documents == ["a.pdf"]


def test_sources_enabled_flag_on_stream_request_and_tools():
    """sources_enabled must default to True and filter search tools when False."""
    from backend.api.routes import AgentStreamRequest
    from backend.orchestrator.agent_loop import _tools_for_request

    req_default = AgentStreamRequest(message="test query")
    assert req_default.sources_enabled is True

    req_disabled = AgentStreamRequest(message="test query", sources_enabled=False)
    assert req_disabled.sources_enabled is False

    # When sources_enabled is False, search_documents and list_documents must not be offered
    tools_with_sources = _tools_for_request("test query", sources_enabled=True)
    tools_without_sources = _tools_for_request("test query", sources_enabled=False)

    search_tool_names = {"search_documents", "list_documents"}
    assert any(t["function"]["name"] in search_tool_names for t in tools_with_sources)
    assert not any(t["function"]["name"] in search_tool_names for t in tools_without_sources)
