"""Tests for FastAPI chat, health, and network endpoints (FRONTEND.md §2-§4).

Verifies:
1. GET /api/health returns ok: True and status: 'ok'.
2. POST /api/chat with informational query returns reply, citations, and plan DAG.
3. POST /api/chat with critical setpoint command triggers awaiting_human_approval.
4. POST /api/approvals/resolve allows the operator to approve or refuse.
5. GET /api/network/status returns telemetry conforming to NetworkMonitorBar contract.
"""

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
    assert action["action_type"] == "DCS_SETPOINT_WRITE"
    assert action["risk_level"] == "CRITICAL"
    assert "FFC-201" in action["target"]

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
