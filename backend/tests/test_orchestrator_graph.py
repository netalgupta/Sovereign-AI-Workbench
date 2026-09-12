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

        # Assert the BEHAVIOUR, not the wording. This previously pinned
        # the literal string "Safety Interlock Gate", which made the
        # copy load-bearing: the sentence could be reworded and the test
        # would fail, while the gate could stop firing and, as long as
        # the phrase survived, it would pass.
        assert "approval" in (state.draft_output or "").lower()
        assert state.draft_output and "executed" in state.draft_output.lower()

        # Verify the request was recorded in the gate
        req = test_gate.get(state.final_output_path)
        assert req.state is ApprovalState.PENDING

        # The gate must describe the action the operator actually asked
        # for. It used to hardcode its own subject -- every gated request,
        # whatever it said, was recorded as "Change HCU feed rate setpoint
        # from 100% (1,450 m3/h) to 115% (1,667 m3/h) via FFC-201", with
        # a controller tag and two flow figures that came from neither
        # the request nor any document. Consent recorded against a
        # description of a different action is worse than no gate: it
        # produces a signed audit entry for something nobody approved.
        assert "Increase feed rate to 115%" in req.effect
        assert "FFC-201" not in req.effect
        assert "1,450" not in req.effect


def test_write_actions_other_than_feed_rate_are_also_gated(tmp_path):
    """Hard constraint #4 covers every write, not one demo sentence.

    The detector was a single regex for the words "feed rate". A request
    to delete the audit log, email a report outside the plant, or post a
    write to SAP matched nothing and executed ungated -- while the UI
    displayed a safety-interlock badge. The gate existed for exactly the
    one sentence in the demo script.
    """
    from backend.orchestrator.graph import classify_action_request

    gated = {
        "Delete the August audit log": "destructive change",
        "Email the QA report to the depot": "outbound send",
        "Write the batch result to SAP": "SAP / ERP write",
        "Export this analysis as a docx file": "file write",
        "Override the interlock on HCU-2": "setpoint change",
    }
    for instruction, expected_category in gated.items():
        assert classify_action_request(instruction) == expected_category, instruction

    # Questions are requests for information, never instructions to act.
    # Gating them would train operators to click through the dialog,
    # which costs the gate its meaning on the request that matters.
    for question in (
        "What is in the August audit log?",
        "Can you summarise the QA report?",
        "Which batches were written to SAP?",
        "Explain how the interlock works",
    ):
        assert classify_action_request(question) is None, question


def test_math_step_uses_the_requested_expression_not_a_fixed_one():
    """The dispatcher must compute what was asked, or nothing.

    The math branch called evaluate_expression with the hardcoded string
    "381.95 - 400" for every request, so the trace showed the same
    subtraction regardless of the question. That defeats hard constraint
    #3 while appearing to satisfy it -- a tool really did execute, on
    input no one requested.
    """
    from backend.orchestrator.graph import extract_arithmetic_expression

    assert extract_arithmetic_expression("what is 381.95 - 400") == "381.95 - 400"
    assert extract_arithmetic_expression("compute 12 * 4 + 2") == "12 * 4 + 2"

    # Nothing computable is a real answer, not a cue to invent a sum.
    assert extract_arithmetic_expression("Check Unit 44 status") is None
    assert extract_arithmetic_expression("See SOP-114-Rev3 section 4.2") is None
    assert extract_arithmetic_expression("reactor running at 382C") is None

    # Parenthesised expressions must be recovered WHOLE. The raw match
    # starts at the digit, so "(12 + 8) * 3" captures "12 + 8) * 3";
    # dropping the orphan bracket to make it parse yields 36 where the
    # operator asked for 60 -- a wrong number, produced by a real tool
    # call, which is exactly the failure the constraint exists to stop.
    assert extract_arithmetic_expression("compute (12 + 8) * 3") == "(12 + 8) * 3"
    assert extract_arithmetic_expression("((2+3)*4) - 1") == "((2+3)*4) - 1"


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


def test_ungrounded_question_refuses_instead_of_reassuring():
    """The most dangerous sentence this system ever emitted.

    synthesize_node's no-context branch used to reply:

        "Evaluated against internal refinery standards and verified
         process calculations. All parameters remain within nominal
         design thresholds."

    That is a safety assurance, stated in the product's own voice,
    produced when retrieval had found NOTHING -- and it was the DEFAULT
    for every question the corpus could not answer. Nothing was
    evaluated, no calculation was verified, and no parameter had been
    read. verify_node then stamped it as self-verified, because that
    node returned a hardcoded satisfied:true.

    This pins the replacement: no corpus support means a refusal.
    """
    state = run_agent_turn(
        "What is the plot of Pride and Prejudice?", session_id="test-refusal"
    )
    reply = (state.draft_output or "").lower()

    assert "not found" in reply
    # The specific fabrications, named so they cannot quietly return.
    assert "nominal design thresholds" not in reply
    assert "all parameters remain within" not in reply
    assert "verified process calculations" not in reply

    # A refusal must not carry citations - there is nothing to cite.
    assert not state.retrieved_context
