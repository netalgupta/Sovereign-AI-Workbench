"""Tests for dispatch, the sub-agent contracts, and verification —
AGENTS_SPEC.md §3/§5/§6, NFR-5.

The centrepiece is test_math_tool_node_never_constructs_an_llm_call:
AGENTS_SPEC §8 asks for that one by name ("grep/mock-assert this
directly, since it's a hard architectural guarantee, not just an
expected behavior"), because an LLM asked for a trend slope produces a
confident number, and a number that looks computed but was not is
indistinguishable downstream from one that was.
"""

import json

import pytest

from backend.orchestrator.dispatch import (
    ContractViolation,
    SubAgentError,
    allowed_tools,
    call_tool_as,
    dispatch,
    node_for,
    run_code_step,
    run_math_step,
)
from backend.orchestrator.state import AgentState, PlanStep
from backend.orchestrator.verification import (
    MAX_REPLAN_CYCLES,
    VerificationOutcome,
    build_verification_prompt,
    parse_verification,
    replan_context,
    unconfirmed_warning,
    verify_output,
)


def _plan(*specs) -> list[PlanStep]:
    return [
        PlanStep(step_id=i, description=d, assigned_agent=a, depends_on=list(deps))
        for i, d, a, deps in specs
    ]


def _state(plan=None, request="Check WABT creep on HCU-2.", draft=None):
    return AgentState(
        session_id="s1", original_request=request, plan=plan or [], draft_output=draft
    )


# ---- NFR-5: the architectural guarantee ---------------------------------


def test_math_tool_node_never_constructs_an_llm_call():
    """AGENTS_SPEC §8 asks for this specific assertion by name.

    Checked by inspecting the module's own source rather than by mocking
    a call: a mock proves one code path did not call a model on one run,
    while this proves there is no such path to take. NFR-5 is a
    structural claim, so it gets a structural test."""
    import inspect

    import backend.orchestrator.dispatch as module

    source = inspect.getsource(module.run_math_step)

    for forbidden in ("requests.post", "ollama", "resolve_model_name", "api/generate", "prompt"):
        assert forbidden not in source, (
            f"math_tool must not reference {forbidden!r} — NFR-5 requires this node be a "
            "direct function call with no path to a model."
        )


def test_math_tool_actually_computes_through_the_registry():
    """The other half of NFR-5: it must really call the numeric library,
    not just avoid calling a model."""
    step = PlanStep(step_id="m1", description="Fit WABT trend", assigned_agent="math")

    event = run_math_step(step, "analyse_trend", {"values": [408.0, 409.5, 411.0, 412.8, 414.1]})

    assert step.status == "done"
    assert event.status == "done"
    assert event.output["direction"] == "increasing"
    assert event.output["method"].startswith("least-squares")


# ---- §6 sub-agent contracts ---------------------------------------------


def test_vision_agent_cannot_write_files():
    """§6 forbids it, and the forbidding is a closed tool set rather than
    a convention the agent is trusted to follow."""
    with pytest.raises(ContractViolation, match="may not call"):
        call_tool_as("vision_agent", "draft_docx", {"title": "x", "sections": [], "output_path": "x.docx"})


def test_math_tool_cannot_reach_a_vision_model():
    """Chart reading is an estimate. Letting the math node reach it would
    put an estimated number where a computed one is expected."""
    with pytest.raises(ContractViolation):
        call_tool_as("math_tool", "describe_chart_image", {"image_path": "x.png"})


def test_code_agent_has_no_tools_until_the_sandbox_exists():
    """Sandbox mechanics are Aditya's (Aryan.md: explicitly not your
    job). An empty set is the honest representation."""
    assert allowed_tools("code_agent") == set()


def test_code_step_refuses_rather_than_reporting_a_step_done_without_running():
    """A step that reports success without running is worse than one that
    fails: the plan continues on output that does not exist, and
    verification is then asked to check nothing."""
    step = PlanStep(step_id="c1", description="Run the calc", assigned_agent="code")

    with pytest.raises(SubAgentError, match="sandbox"):
        run_code_step(step, "print(1)")

    assert step.status == "failed"


def test_every_plan_agent_maps_to_a_node():
    """PlanStep uses short names, the graph uses long ones. math_tool
    breaks the "_agent" suffix pattern, and a silent mismatch there would
    route arithmetic to a model — exactly what NFR-5 forbids."""
    for agent in ("vision", "code", "reasoning", "math", "retrieval"):
        step = PlanStep(step_id="x", description="d", assigned_agent=agent)
        assert node_for(step) in allowed_tools.__globals__["_ALLOWED_TOOLS"]

    assert node_for(PlanStep(step_id="x", description="d", assigned_agent="math")) == "math_tool"


# ---- dispatch ------------------------------------------------------------


def test_dispatch_releases_all_independent_steps_at_once():
    """The whole point of depends_on. Collapsing this to a sequence
    throws away the only thing the dependency graph buys."""
    state = _state(_plan(
        ("a", "retrieve x", "retrieval", []),
        ("b", "retrieve y", "retrieval", []),
        ("c", "draft", "reasoning", ["a", "b"]),
    ))

    ready = dispatch(state)

    assert {s.step_id for s in ready} == {"a", "b"}


def test_dispatch_does_not_hand_out_the_same_step_twice():
    """State is shared. A caller that dispatches, awaits, then dispatches
    again would otherwise re-issue work already in flight."""
    state = _state(_plan(("a", "x", "math", [])))

    first = dispatch(state)
    second = dispatch(state)

    assert len(first) == 1
    assert second == []


def test_a_failed_dependency_blocks_rather_than_silently_completing():
    state = _state(_plan(
        ("a", "x", "math", []),
        ("b", "y", "reasoning", ["a"]),
    ))
    state.plan[0].status = "failed"

    assert dispatch(state) == []
    assert state.is_blocked() is True
    assert state.is_complete() is False


# ---- §5 verification -----------------------------------------------------


def _verifier(payload):
    def call(prompt, model_name):
        return json.dumps(payload) if not isinstance(payload, str) else payload
    return call


def test_the_prompt_is_the_spec_text_with_both_fields_substituted():
    prompt = build_verification_prompt("Draft a safety note.", "Here is the note.")

    assert "You are checking whether an AI assistant's output" in prompt
    assert "Draft a safety note." in prompt
    assert "Here is the note." in prompt
    # The JSON example's braces must survive substitution intact.
    assert '{"satisfied": true/false' in prompt


def test_a_satisfied_output_passes():
    state, outcome = verify_output(
        _state(draft="The WABT trigger is 415 degC [1]."),
        verifier_fn=_verifier({"satisfied": True, "reason": "Answers the request.", "missing": []}),
    )

    assert outcome is VerificationOutcome.PASSED
    assert state.verification_result.passed is True


def test_an_unsatisfied_output_routes_to_replan_and_counts_the_cycle():
    state, outcome = verify_output(
        _state(draft="Something vague."),
        verifier_fn=_verifier({"satisfied": False, "reason": "No citation.", "missing": ["citation"]}),
    )

    assert outcome is VerificationOutcome.REPLAN
    assert state.replan_count == 1


def test_after_two_cycles_it_halts_as_unconfirmed_rather_than_looping():
    """§5: "rather than looping indefinitely or silently shipping an
    unverified result". Looping burns an afternoon of local inference
    with the user watching a spinner."""
    state = _state(draft="Still vague.")
    state.replan_count = MAX_REPLAN_CYCLES

    state, outcome = verify_output(
        state,
        verifier_fn=_verifier({"satisfied": False, "reason": "Still no citation.", "missing": ["citation"]}),
    )

    assert outcome is VerificationOutcome.UNCONFIRMED
    assert state.replan_count == MAX_REPLAN_CYCLES  # not incremented past the cap


def test_unconfirmed_is_a_third_state_not_a_pass():
    """An output that failed verification and is presented identically to
    one that passed makes the verification step actively harmful — it
    creates confidence it did not earn."""
    assert VerificationOutcome.UNCONFIRMED is not VerificationOutcome.PASSED
    assert VerificationOutcome.UNCONFIRMED.value == "unconfirmed"


def test_an_unreadable_verdict_fails_closed():
    """Defaulting to satisfied when the verifier is unintelligible means
    a malformed response silently becomes a pass — the one direction this
    node must never fail in."""
    result = parse_verification("I think it looks good to me!")

    assert result.passed is False
    assert "unverified" in result.reason


def test_a_verdict_without_the_satisfied_field_fails_closed():
    result = parse_verification(json.dumps({"reason": "seems fine"}))

    assert result.passed is False


def test_nothing_to_verify_is_not_a_pass():
    """A step that produced no output reaching the gate as "verified" is
    precisely the silent-ship failure §5 names."""
    state, outcome = verify_output(_state(draft=None), verifier_fn=_verifier({"satisfied": True}))

    assert outcome is VerificationOutcome.UNCONFIRMED
    assert state.verification_result.passed is False


def test_replan_context_keeps_the_original_request():
    """A re-plan that sees only the gaps plans to fill the gaps, and
    loses the task they were gaps in."""
    state, _ = verify_output(
        _state(request="Draft a benzene safety note.", draft="x"),
        verifier_fn=_verifier(
            {"satisfied": False, "reason": "no limit", "missing": ["the 8-hour TWA limit"]}
        ),
    )

    context = replan_context(state)

    assert "Draft a benzene safety note." in context
    assert "the 8-hour TWA limit" in context


def test_the_unconfirmed_warning_is_usable_verbatim_in_the_approval_ui():
    state = _state(draft="x")
    state.replan_count = MAX_REPLAN_CYCLES
    state, _ = verify_output(
        state,
        verifier_fn=_verifier(
            {"satisfied": False, "reason": "No source given.", "missing": ["a citation"]}
        ),
    )

    warning = unconfirmed_warning(state)

    assert "could not confirm" in warning
    assert "No source given." in warning
    assert "a citation" in warning
    assert "Review it" in warning
