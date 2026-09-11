"""Tests for the planner node — AGENTS_SPEC.md §3/§4, FR-5.

Written around one principle: a plan that cannot make progress must fail
LOUDLY in validation. At dispatch, a stalled plan is indistinguishable
from slow local inference — the user sees a spinner either way — so
every structural defect a local model actually produces is checked here,
where it can still be named.

The model is faked throughout. What is under test is the validation and
repair around it, not whether a 14B model plans well.
"""

import json

import pytest

from backend.orchestrator.planner import (
    MAX_PLAN_STEPS,
    PlanningError,
    plan_request,
    validate_plan,
)
from backend.orchestrator.state import AgentState


def _state(request="Draft a benzene safety note from the HSE manual."):
    return AgentState(session_id="s1", original_request=request)


def _fake_planner(payload):
    """A planner that returns exactly this payload, as a model would."""
    def call(prompt, model_name):
        return json.dumps(payload) if not isinstance(payload, str) else payload
    return call


# ---- the happy path -----------------------------------------------------


def test_a_well_formed_plan_is_accepted_with_its_dependencies(monkeypatch):
    state = plan_request(
        _state(),
        planner_fn=_fake_planner([
            {"step_id": "a", "description": "Retrieve the exposure limit.",
             "assigned_agent": "retrieval", "depends_on": []},
            {"step_id": "b", "description": "Draft the note.",
             "assigned_agent": "reasoning", "depends_on": ["a"]},
        ]),
    )

    assert [s.step_id for s in state.plan] == ["a", "b"]
    assert state.plan[1].depends_on == ["a"]
    assert all(s.status == "pending" for s in state.plan)


def test_independent_steps_are_all_ready_at_once(monkeypatch):
    """The point of depends_on: three independent retrievals should run
    together, not queue behind each other."""
    state = plan_request(
        _state(),
        planner_fn=_fake_planner([
            {"step_id": "a", "description": "x", "assigned_agent": "retrieval", "depends_on": []},
            {"step_id": "b", "description": "y", "assigned_agent": "retrieval", "depends_on": []},
            {"step_id": "c", "description": "z", "assigned_agent": "reasoning",
             "depends_on": ["a", "b"]},
        ]),
    )

    assert {s.step_id for s in state.ready_steps()} == {"a", "b"}

    for step in state.plan:
        if step.step_id in ("a", "b"):
            step.status = "done"
    assert [s.step_id for s in state.ready_steps()] == ["c"]


# ---- the defects a local model actually produces ------------------------


def test_a_dependency_on_a_step_that_does_not_exist_is_dropped():
    """Left in, this step waits forever on an id nobody will ever
    complete, and the plan hangs looking healthy."""
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "retrieval", "depends_on": []},
        {"step_id": "b", "description": "y", "assigned_agent": "reasoning",
         "depends_on": ["a", "ghost_step"]},
    ])

    assert plan[1].depends_on == ["a"]


def test_a_self_dependency_is_dropped():
    """A step waiting for itself to finish before it may start can never
    run."""
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "math", "depends_on": ["a"]},
    ])

    assert plan[0].depends_on == []


def test_a_dependency_cycle_is_broken_without_losing_steps():
    """Deadlock: each waits on the other. The edge that closes the cycle
    is dropped rather than a whole step, because the steps are usually
    sound and only the stated ordering is wrong."""
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "retrieval", "depends_on": ["b"]},
        {"step_id": "b", "description": "y", "assigned_agent": "reasoning", "depends_on": ["a"]},
    ])

    assert len(plan) == 2
    state = AgentState(session_id="s", original_request="r", plan=plan)
    assert state.ready_steps(), "a broken cycle must leave something able to start"


def test_duplicate_step_ids_are_made_unique():
    """A dependency on "step_2" is ambiguous when there are two of
    them — the dispatcher would treat whichever it found first as
    authoritative."""
    plan = validate_plan([
        {"step_id": "s", "description": "x", "assigned_agent": "math", "depends_on": []},
        {"step_id": "s", "description": "y", "assigned_agent": "math", "depends_on": []},
    ])

    assert len({s.step_id for s in plan}) == 2


def test_an_unknown_agent_is_repaired_not_dropped():
    """A model asked for "retrieval" sometimes answers "rag". Dropping
    the step loses work the request needed, and produces an answer
    missing a piece nobody knows is missing."""
    plan = validate_plan([
        {"step_id": "a", "description": "Search the corpus.",
         "assigned_agent": "rag", "depends_on": []},
    ])

    assert len(plan) == 1
    assert plan[0].assigned_agent == "reasoning"


def test_a_plan_where_every_step_depends_on_another_is_repaired_into_a_runnable_one():
    """This test originally asserted that such a plan RAISES. It does
    not, and should not: the cycle-breaker repairs it, which is strictly
    better than refusing work the user asked for.

    The stronger property, asserted here instead: whatever tangle the
    model emits, validate_plan returns something that can actually start.
    A hang is the worst failure mode in this whole node, because at
    dispatch it is indistinguishable from slow local inference."""
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "math", "depends_on": ["b"]},
        {"step_id": "b", "description": "y", "assigned_agent": "math", "depends_on": ["c"]},
        {"step_id": "c", "description": "z", "assigned_agent": "math", "depends_on": ["b"]},
    ])

    assert len(plan) == 3, "repair must not discard requested work"
    state = AgentState(session_id="s", original_request="r", plan=plan)
    assert state.ready_steps(), "every returned plan must have something able to start"


def test_an_empty_plan_is_refused():
    with pytest.raises(PlanningError):
        validate_plan([])


def test_a_runaway_plan_is_capped():
    """Each step is tens of seconds of local inference. A 40-step plan is
    half an hour before the user sees anything, and in practice a
    runaway plan is repetitive rather than thorough."""
    plan = validate_plan([
        {"step_id": f"s{i}", "description": "x", "assigned_agent": "reasoning", "depends_on": []}
        for i in range(40)
    ])

    assert len(plan) == MAX_PLAN_STEPS


# ---- the model's output shape -------------------------------------------


def test_a_plan_wrapped_in_an_object_is_unwrapped():
    """Models wrap the list about as often as they return it bare, and
    both are reasonable readings of "produce a JSON list"."""
    state = plan_request(
        _state(),
        planner_fn=_fake_planner(
            {"steps": [{"step_id": "a", "description": "x",
                        "assigned_agent": "retrieval", "depends_on": []}]}
        ),
    )

    assert len(state.plan) == 1


def test_a_plan_in_a_code_fence_is_parsed():
    state = plan_request(
        _state(),
        planner_fn=_fake_planner(
            '```json\n[{"step_id": "a", "description": "x", '
            '"assigned_agent": "math", "depends_on": []}]\n```'
        ),
    )

    assert state.plan[0].assigned_agent == "math"


def test_non_json_output_raises_rather_than_returning_an_empty_plan():
    """An empty plan would be executed as "nothing to do" and reported as
    success."""
    with pytest.raises(PlanningError, match="did not return JSON"):
        plan_request(_state(), planner_fn=_fake_planner("I'll help you with that!"))


def test_the_prompt_is_the_spec_text_verbatim():
    """AGENTS_SPEC §4 is locked. Unlike GRAPH_SPEC §5's extraction prompt
    — changed this session with measurement because it offered three
    structurally impossible options — this one has no such defect."""
    from backend.orchestrator.planner import _PLANNER_PROMPT_PREFIX

    assert "You are a task planner for an industrial AI assistant." in _PLANNER_PROMPT_PREFIX
    assert "Only include steps that are actually necessary." in _PLANNER_PROMPT_PREFIX
    assert "Do not add speculative steps" in _PLANNER_PROMPT_PREFIX


# ---- state helpers the dispatcher relies on -----------------------------


def test_blocked_is_not_confused_with_complete():
    """A plan stuck on a failed dependency would otherwise look finished
    and be reported as success."""
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "math", "depends_on": []},
        {"step_id": "b", "description": "y", "assigned_agent": "math", "depends_on": ["a"]},
    ])
    state = AgentState(session_id="s", original_request="r", plan=plan)
    state.plan[0].status = "failed"

    assert state.is_blocked() is True
    assert state.is_complete() is False


def test_a_finished_plan_is_complete_and_not_blocked():
    plan = validate_plan([
        {"step_id": "a", "description": "x", "assigned_agent": "math", "depends_on": []},
    ])
    state = AgentState(session_id="s", original_request="r", plan=plan)
    state.plan[0].status = "done"

    assert state.is_complete() is True
    assert state.is_blocked() is False
