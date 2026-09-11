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
    assert len(data["plan"]) >= 2

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
