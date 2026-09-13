"""The three gaps Advay's pre-rehearsal audit found. All were real.

Each was a flagship demo claim with no backend behind it, and each
failed in the way this codebase keeps failing: the UI looked correct
while nothing underneath was wired.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _first_event(body, event_type):
    with client.stream("POST", "/api/chat/stream", json=body) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == event_type:
                return event
    return None


@pytest.mark.live_model
def test_the_stream_emits_a_plan_before_doing_any_work():
    """The Plan Graph rendered empty on every live turn.

    /api/chat/stream ran a tool-calling loop and never called the
    planner, so no plan event was ever sent. POST /api/plan existed and
    nothing invoked it. The highest-impact visual in the demo showed
    nothing during the demo.
    """
    event = _first_event(
        {"message": "What is the average MFI for Homopolymer H030SG?"}, "plan"
    )
    assert event is not None, "no plan event was emitted"
    assert event["steps"], "the plan event carried no steps"
    for step in event["steps"]:
        assert step["step_id"] and step["description"]
        assert step["assigned_agent"]
        assert isinstance(step["depends_on"], list)


def test_switching_a_source_off_actually_excludes_it():
    """Toggling a source off was pure client-side React state.

    Nothing reached retrieval, so an excluded document kept appearing in
    citations and kept grounding answers -- while the panel displayed
    "This session is grounded only in the sources listed here". That is
    a trust defect, not a missing feature: the panel exists to say what
    an answer rests on, and it was wrong.
    """
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store, _ = get_state().ensure_corpus()
    question = "What is the average MFI for Homopolymer H030SG?"

    unfiltered = retrieve_with_grounding_check(store, question, 5)
    documents = {c.source_document for c in unfiltered.chunks}
    assert len(documents) > 1, "fixture needs multiple documents to prove filtering"

    keep = sorted(documents)[0]
    filtered = retrieve_with_grounding_check(
        store, question, 5, active_documents=[keep]
    )
    assert {c.source_document for c in filtered.chunks} <= {keep}, (
        "an excluded document survived the filter"
    )


def test_excluded_documents_cannot_return_as_neighbours():
    """Neighbour expansion must respect the filter too.

    Chunks adjacent to a match are pulled in to repair procedures cut at
    a chunk boundary. Without the same filter, an excluded document
    would re-enter through the back door of an included one.
    """
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store, _ = get_state().ensure_corpus()
    keep = "SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx"
    result = retrieve_with_grounding_check(
        store, "catalyst changeout procedure", 5, active_documents=[keep]
    )
    assert all(c.source_document == keep for c in result.chunks)


def test_switching_everything_off_is_honoured_not_ignored():
    """An empty list means "the user switched everything off".

    That is a different instruction from None ("no filter supplied"),
    and collapsing the two would turn a deliberate exclusion into a
    silent search-everything.
    """
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store, _ = get_state().ensure_corpus()
    result = retrieve_with_grounding_check(
        store, "anything at all", 5, active_documents=[]
    )
    assert result.found is False
    assert result.chunks == []
    assert "switched off" in (result.reason or "").lower()


def test_adding_a_model_refuses_a_tag_ollama_does_not_have():
    """FR-4 had no backend at all: the form posted into a 405.

    And the validation matters as much as the endpoint. Two tags in this
    repo's own registry never existed -- qwen2-vl:7b and phi-3.5-mini --
    and both were found only when something tried to use them. One had
    been silently 404ing the router and the verifier for weeks. A
    registry that accepts an unchecked name is how that happens.
    """
    response = client.post(
        "/api/models", json={"id": "test-ghost", "model": "definitely-not-a-model:99b"}
    )
    assert response.status_code in (400, 503), (
        "an unverifiable model tag must be refused, not written"
    )
    if response.status_code == 400:
        assert "ollama pull" in response.json()["detail"].lower()


def test_adding_a_duplicate_registry_id_is_refused():
    response = client.post(
        "/api/models", json={"id": "reasoning-model", "model": "qwen2.5:7b"}
    )
    assert response.status_code == 409
