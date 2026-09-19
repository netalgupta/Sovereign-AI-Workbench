import json
"""Tests for FastAPI chat, health, and network endpoints (FRONTEND.md §2-§4).

Verifies:
1. GET /api/health returns ok: True and status: 'ok'.
2. POST /api/chat with informational query returns reply, citations, and plan DAG.
3. POST /api/chat with critical setpoint command triggers awaiting_human_approval.
4. POST /api/approvals/resolve allows the operator to approve or refuse.
5. GET /api/network/status returns telemetry conforming to NetworkMonitorBar contract.
"""

import pytest

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_api_health_shape_compatibility():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert "corpus_loaded" in data
    assert "graph_available" in data


@pytest.mark.live_model
def test_api_chat_standard_query():
    payload = {
        "message": "What is the design capacity and operational profile of MRPL?",
        "session_id": "test-chat-session",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "reply" in data
    assert isinstance(data["reply"], str)
    assert len(data["reply"]) > 0

    assert "citations" in data
    assert isinstance(data["citations"], list)

    assert "plan" in data
    assert isinstance(data["plan"], list)

    # A PLAN EXISTS AND IS WELL FORMED -- not "has at least two steps".
    #
    # This asserted >= 2, which pinned the old behaviour where every
    # question, however simple, went through the LLM planner and came
    # back with a multi-step DAG. That was not a feature. Measured, the
    # planner cost 10.9s against 4.3s to actually answer, and for a
    # single lookup it invented work: a `math` step to "calculate the
    # average" of a value printed verbatim in the source table, and a
    # `code` step to "create standard operating procedures" that
    # dispatched to the sandbox and failed.
    #
    # Simple lookups now get a one-step plan without an LLM call
    # (simple_intent.py). Asserting >= 2 would forbid that improvement,
    # which is the same trap as the earlier planner test that asserted a
    # tangled plan must RAISE when the cycle-breaker repairs it.
    assert len(data["plan"]) >= 1
    for step in data["plan"]:
        assert step.get("assigned_agent")
        assert step.get("description")
        assert isinstance(step.get("depends_on", []), list)

    # Check Plan DAG fields required by PlanGraphView.jsx
    first_step = data["plan"][0]
    assert "id" in first_step
    assert "description" in first_step
    assert "assigned_agent" in first_step
    assert "status" in first_step
    assert "depends_on" in first_step
    assert "tool_call_event_id" in first_step

    assert "tool_call_events" in data
    assert data["awaiting_human_approval"] is False
    assert data["approval_action"] is None
    assert data["session_id"] == "test-chat-session"


def test_api_chat_critical_action_approval():
    payload = {
        "message": "Increase feed rate to 115%",
        "session_id": "test-action-session",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["awaiting_human_approval"] is True
    assert data["approval_action"] is not None

    action = data["approval_action"]

    # THIS TEST USED TO PIN THE FABRICATION IN PLACE.
    #
    # It asserted action_type == "DCS_SETPOINT_WRITE", risk_level ==
    # "CRITICAL", and "FFC-201" in target. All three were hardcoded
    # literals in the route, invented rather than derived from the
    # request -- the same three appeared for EVERY gated action,
    # including a request to write a Word document.
    #
    # So the suite guaranteed the bug: any honest fix failed these
    # assertions. That is the same trap as the planner test that
    # asserted a tangled plan must RAISE when the cycle-breaker repairs
    # it, and the gate test that pinned the literal string "Safety
    # Interlock Gate". A test can hold a defect in place as firmly as
    # it can catch one.
    #
    # What is actually true: this request IS a setpoint change, so the
    # category must be recognised -- but the system has NOT resolved
    # which device, which tag, or what the current value is, and must
    # not claim to have.
    assert action["action_type"] == "SETPOINT_WRITE"
    assert "setpoint" in action["title"].lower()
    assert "Increase feed rate to 115%" in action["detail"]

    # Unresolved must read as unresolved.
    assert action["target"] is None
    assert action["resolved_parameters"] is False
    assert action["risk_level"] == "REQUIRES_REVIEW"

    # And none of the invented specifics may return.
    blob = json.dumps(action)
    for invented in ("FFC-201", "1,450", "1,667", "LHSV", "QFC-18"):
        assert invented not in blob, (
            f"fabricated value {invented!r} is back in the approval payload"
        )

    # Test resolving the approval
    resolve_payload = {
        "request_id": action["id"],
        "confirmed": True,
        "operator": "test_operator",
    }
    res_response = client.post("/api/approvals/resolve", json=resolve_payload)
    assert res_response.status_code == 200
    res_data = res_response.json()
    assert res_data["status"] == "approved"
    assert "token" in res_data


def test_api_network_status_telemetry():
    response = client.get("/api/network/status")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "externalCount" in data
    assert "connections" in data
    assert "metrics" in data
    assert "cpuPercent" in data["metrics"]
    assert "memoryGb" in data["metrics"]


def test_multi_step_request_still_gets_a_multi_step_plan():
    """The planner is skipped for lookups, NOT disabled.

    Companion to the assertion above: relaxing it to >= 1 would pass
    even if the planner had been removed entirely, so this pins the
    other half -- a request carrying two distinct asks must still be
    decomposed rather than collapsed into one retrieval.
    """
    from backend.orchestrator.simple_intent import is_simple_lookup

    multi = "Summarise the inspection report and then calculate the deviation"
    assert not is_simple_lookup(multi), (
        "a request with two distinct asks must reach the real planner"
    )

    # And the shape that SHOULD bypass it.
    assert is_simple_lookup("What is the average MFI for Homopolymer H030SG?")


def test_the_approval_modal_describes_the_action_that_was_requested():
    """The payload used to describe a DIFFERENT action entirely.

    Every field except the id and description was a hardcoded literal
    about a feed-rate change. Asked to "Draft a DOCX report on the
    Hassan incident and save it", the modal rendered:

        DCS_SETPOINT_WRITE
        "Confirm Operational Setpoint Modification"
        Target: HCU-2 / FFC-201
        CURRENT 100% (1,450 m3/h) -> PROPOSED 115% (1,667 m3/h)
        "+15.0% Excursion"
        "Operating above 110% reduces catalyst residence time..."

    for a request to write a Word document.

    This is the worst possible place for invented content. It is the one
    screen where a human signs off, so approval recorded against
    fabricated figures produces a signed audit entry for something
    nobody approved -- worse than no gate at all, because the gate is
    what makes the record trustworthy.
    """
    response = client.post(
        "/api/chat",
        json={
            "message": "Draft a DOCX report on the Hassan incident and save it",
            "session_id": "test-approval-shape",
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["awaiting_human_approval"] is True
    action = data["approval_action"]
    assert action, "a gated request must carry an approval_action"

    # It is a FILE WRITE, and must not be labelled as a setpoint change.
    assert action["action_type"] == "FILE_WRITE"
    assert "setpoint" not in (action["title"] or "").lower()

    # The operator's own words, not a paraphrase or a substitute.
    assert "DOCX report" in action["detail"]

    # None of the fabricated specifics, anywhere in the payload.
    blob = json.dumps(action)
    for invented in (
        "1,450", "1,667", "FFC-201", "HCU-2", "LHSV", "QFC-18",
        "Excursion", "exothermic",
    ):
        assert invented not in blob, (
            f"fabricated value {invented!r} is back in the approval payload"
        )

    # Unknown must read as unknown -- AND KNOWN AS KNOWN. This asserted
    # target None / unresolved unconditionally, but a document request
    # resolves to a real draft_docx call with an exact output file, and
    # the card then said "has NOT resolved a file path" directly above a
    # preview naming it. Accuracy in both directions.
    if action["resolved_parameters"]:
        assert action["target"] and action["target"].endswith(".docx")
        assert action["warning"] is None
    else:
        assert action["target"] is None
        assert "NOT resolved" in action["warning"]
