"""Tests for the LangGraph orchestrator state engine (AGENTS_SPEC §1-§6, FR-5).

Verifies:
1. Critical setpoint / action requests trigger the Safety Interlock Gate immediately.
2. Informational questions pass through the planner and dispatch loop.
3. Plan DAG dependency resolution correctly resolves ready_steps.
4. Tool call log and verification result are populated in state.
"""

from unittest.mock import patch

from backend.audit.approval_gate import ApprovalGate, ApprovalState
from backend.orchestrator.graph import (
    is_action_approval_request,
    run_agent_turn,
)
from backend.orchestrator.state import AgentState, PlanStep


def test_is_action_approval_request_detection():
    # Commands requiring safety gate
    assert is_action_approval_request("Increase feed rate to 115%")
    assert is_action_approval_request("raise feed-rate to 120%")
    assert is_action_approval_request("set feed rate = 1600 m3/h")
    assert is_action_approval_request("modify the feed rate to 115")

    # Inquiries that must NOT trigger safety gate
    assert not is_action_approval_request("What is the maximum feed rate limit?")
    assert not is_action_approval_request("Can you explain how HCU-2 works?")
    assert not is_action_approval_request("Tell me about the catalyst deactivation trend.")
    assert not is_action_approval_request("Why is feed rate constrained to 110%?")


def test_critical_action_triggers_approval_gate(tmp_path):
    # Route approval gate storage to temporary directory
    with patch("backend.orchestrator.graph.ApprovalGate") as mock_gate_cls:
        test_gate = ApprovalGate(
            requests_file=tmp_path / "requests.jsonl",
            audit_log=None,
        )
        mock_gate_cls.return_value = test_gate

        state = run_agent_turn("Increase feed rate to 115%", session_id="test-session-1")

        assert state.awaiting_human_approval is True
        assert state.final_output_path is not None
        assert "Safety Interlock Gate" in (state.draft_output or "")

        # Verify the request was recorded in the gate
        req = test_gate.get(state.final_output_path)
        assert req.state is ApprovalState.PENDING
        assert req.tool_name == "dcs_setpoint_write"


def test_standard_query_executes_plan_and_dispatch():
    state = run_agent_turn(
        "Analyze operating limits for hydrocracker reactor",
        session_id="test-session-2",
    )

    assert state.awaiting_human_approval is False
    assert len(state.plan) >= 2
    assert all(s.status == "done" for s in state.plan)
    assert len(state.tool_call_log) >= 1
    assert state.draft_output is not None
    assert state.verification_result is not None


def test_agent_state_ready_steps_dependency_resolution():
    step1 = PlanStep(
        step_id="step-1",
        description="First step",
        assigned_agent="retrieval",
        status="pending",
        depends_on=[],
    )
    step2 = PlanStep(
        step_id="step-2",
        description="Second step",
        assigned_agent="math",
        status="pending",
        depends_on=["step-1"],
    )

    state = AgentState(
        session_id="test-dep",
        original_request="test",
        plan=[step1, step2],
    )

    # Initially only step1 is ready
    ready = state.ready_steps()
    assert len(ready) == 1
    assert ready[0].step_id == "step-1"

    # Once step1 is done, step2 becomes ready
    step1.status = "done"
    ready = state.ready_steps()
    assert len(ready) == 1
    assert ready[0].step_id == "step-2"
