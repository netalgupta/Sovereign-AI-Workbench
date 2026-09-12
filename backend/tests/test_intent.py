"""Intent triage, and the guard that keeps it away from plant questions."""

import pytest

from backend.orchestrator.intent import classify
from backend.orchestrator.path_router import decide_path


def test_a_greeting_does_not_run_the_pipeline():
    """"HolA aMIGO" took 46.56 seconds and returned a refusal.

    The trace showed the LLM planner (10.5s, which then failed to
    parse), a three-step fallback plan about "operational parameters and
    safety envelopes", a corpus search, and a grounding refusal naming
    the three documents closest to a Spanish greeting.

    Every stage did its job. The mistake was that nothing looked at the
    message first.
    """
    for greeting in ("HolA aMIGO", "hi", "hey there", "good morning!", "hello"):
        intent = classify(greeting)
        assert intent.kind == "greeting", greeting
        assert intent.needs_corpus is False


def test_domain_words_veto_every_fast_path():
    """The guard that makes this safe.

    A plant question must reach retrieval even when it looks
    conversational or contains a calculation. Over-triaging costs a
    citation; under-triaging costs a few seconds.
    """
    for request in (
        "hi, what is the reactor temperature limit?",
        "convert the MFI spec to metric",
        "thanks, now show me the SOP",
        "what is 22 + 16 batches for the Novolen report",
    ):
        assert classify(request).needs_corpus is True, request


def test_capability_is_answered_from_the_live_registry():
    """Not from a written-out list, which drifts the moment a tool changes.

    This codebase already shipped a UI listing two plant connectors that
    did not exist.
    """
    from backend.orchestrator.intent import capability_reply

    assert classify("what can you do?").kind == "capability"
    reply = capability_reply()
    assert "search_documents" in reply, "should name real registered tools"
    assert "approval" in reply.lower(), "must mention the approval rule"


def test_document_questions_are_untouched():
    for request in (
        "What is the average MFI for Homopolymer H030SG?",
        "What is the SOP for catalyst changeout?",
        "Summarise the maintenance log",
    ):
        assert decide_path(request).path in ("direct", "agentic", "corpus"), request


def test_planner_survives_trailing_prose_after_valid_json():
    """Observed live: a correct plan discarded because the model kept talking.

        ```json
        [ {...} ]
        ```

        Explanation: The request i...

    Same failure the verifier had. A 10.5-second call thrown away over a
    trailing sentence.
    """
    from backend.orchestrator.planner import _first_json_array

    raw = (
        '```json\n[{"step_id": "greet", "description": "Greet the user.", '
        '"assigned_agent": "reasoning", "depends_on": []}]\n```\n\n'
        "Explanation: The request is a greeting, so one step suffices."
    )
    parsed = _first_json_array(raw)
    assert parsed is not None, "a valid plan must survive trailing prose"
    assert parsed[0]["step_id"] == "greet"

    # A bracket inside a description must not truncate the array.
    tricky = '[{"step_id": "a", "description": "check [Bed 1] limits", "assigned_agent": "reasoning", "depends_on": []}]'
    assert _first_json_array(tricky)[0]["description"] == "check [Bed 1] limits"

    assert _first_json_array("no json here at all") is None


# ---------------------------------------------------------------------
# THE TRIAGE HAS TO RUN ON THE PATH THE PRODUCT ACTUALLY TAKES.
#
# Everything above this line passed while "Hola Amigo" still took 50.80
# seconds in the running app, because all of it tested classify() and
# decide_path() -- and the frontend posts to /api/chat, which enters the
# LangGraph orchestrator and consults neither. The triage was real, the
# tests were real, and the product was unchanged.
#
# So these tests go through router_node, the graph's own entry point.
# ---------------------------------------------------------------------


def _route(message: str):
    from backend.orchestrator.graph import router_node
    from backend.orchestrator.state import AgentState

    return router_node(AgentState(session_id="t", original_request=message))


def test_the_graph_answers_a_greeting_without_planning_or_retrieving():
    for greeting in ("Hola Amigo", "hi", "hey there", "good morning!", "hello"):
        out = _route(greeting)
        assert out.get("draft_output"), f"{greeting!r} produced no reply"
        assert "Sources" in out["draft_output"]
        # One step, already done. Not a three-step plan about safety
        # envelopes.
        assert [s.step_id for s in out["plan"]] == ["greeting"]
        assert out["plan"][0].status == "done"


def test_the_graph_ends_the_turn_when_the_router_has_already_answered():
    """The branch that makes the short-circuit real.

    Without it the planner runs anyway and overwrites a finished answer
    with a plan for work that is already done.
    """
    from backend.orchestrator.state import AgentState
    from langgraph.graph import END

    import backend.orchestrator.graph as G

    # Rebuild the graph to get at the branch function it closes over by
    # exercising the compiled graph end to end instead: a greeting must
    # reach END with the router's own reply intact and no plan beyond
    # the single step.
    state = G.run_agent_turn("Hola Amigo", "test-session")
    assert state.draft_output.startswith("Hello.")
    assert len(state.plan) == 1
    assert state.verification_result is None, "nothing to verify; nothing ran"
    assert state.retrieved_context == [], "a greeting must not retrieve"
    assert END is not None  # import kept meaningful


def test_a_closing_that_continues_past_the_first_word():
    """"thanks, that's all" matched neither branch and took the pipeline.

    The pattern anchored the end of the message immediately after the
    first acknowledgement, so a second one made it a document question.
    """
    for closing in (
        "thanks",
        "thanks, that's all",
        "ok thanks!",
        "great, thank you",
        "cheers, that's it for now",
    ):
        assert classify(closing).kind == "closing", closing


def test_a_calculation_is_computed_by_a_tool_not_asserted():
    """Hard constraint #3 does not have a small-sum exception.

    The fast path skips RETRIEVAL, never the calculation: the value in
    the reply has to come from an executed tool call that appears in the
    trace.
    """
    out = _route("what is 47 * 3.2")
    assert out is not None and out.get("draft_output")
    assert "150.4" in out["draft_output"]

    events = out["tool_call_log"]
    assert [e.tool_name for e in events] == ["evaluate_expression"]
    assert events[0].status == "done"
    assert "150.4" in str(events[0].output["result"])


def test_a_unit_conversion_reports_the_value_not_the_result_object():
    """Probing for the wrong attribute did not fail -- it printed a repr.

    CalcResult carries `result`; UnitCalcResult carries
    `result_magnitude` + `result_unit`. Reading the wrong one fell
    through to str(result) and rendered

        **5 bar = expression='5 bar' result_magnitude=500.0 ...**

    as an answer to an operator.
    """
    out = _route("convert 5 bar to kPa")
    assert out is not None and out.get("draft_output")
    reply = out["draft_output"]
    assert "500" in reply and "kilopascal" in reply
    assert "result_magnitude" not in reply, "a pydantic repr reached the user"
    assert "expression=" not in reply


def test_plant_questions_still_enter_the_full_pipeline():
    """The guard. Over-triaging costs a citation; that is the expensive way
    to be wrong, so anything with plant vocabulary must fall through."""
    for request in (
        "What is the SOP for Hydrocracker catalyst changeout?",
        "hi, what is the reactor temperature limit?",
        "convert the MFI spec to metric",
        "Summarise the maintenance log",
    ):
        out = _route(request)
        assert not out.get("draft_output"), f"{request!r} was short-circuited"
        assert not out.get("plan"), f"{request!r} was given a plan by the router"


def test_the_approval_gate_still_wins_over_triage():
    """Triage is checked AFTER the action gate, deliberately. A request
    that writes to the plant must never be answered by a fast path."""
    out = _route("Increase the HCU feed rate to 115%")
    assert out["awaiting_human_approval"] is True
    assert out["final_output_path"], "no approval request id"


def test_an_instant_path_does_not_call_the_planner():
    """The 3.5s greeting from HANDOFF.md 3a, as an assertion.

    Routing was never the cost. _emit_plan ran three lines above the
    instant-path check, and a greeting is not a "simple lookup" (no
    question opener), so it fell through to the LLM planner and spent
    10.5s planning a turn that was about to be answered from a constant.

    This test fails if the planner is reachable from an instant path,
    which is the only way that regression can come back.
    """
    import backend.orchestrator.planner as planner
    from backend.orchestrator.agent_loop import run_turn

    calls = []

    def _explode(*args, **kwargs):
        calls.append(args)
        raise AssertionError("the planner must not run for an instant path")

    original = planner.plan_request
    planner.plan_request = _explode
    try:
        for message in ("Hola Amigo", "thanks", "what can you do"):
            events = list(run_turn(message, session_id="no-planner"))
            done = [e for e in events if e["type"] == "done"]
            assert done and done[0]["reply"], message
            plans = [e for e in events if e["type"] == "plan"]
            assert plans and len(plans[0]["steps"]) == 1, message
    finally:
        planner.plan_request = original

    assert calls == []


# ---------------------------------------------------------------------
# "Wassup buddy" -- 47.14s, because the greeting list had a hole in it.
# ---------------------------------------------------------------------


def test_greetings_are_matched_by_shape_not_by_a_word_list():
    """Every hole in a list of greetings is a 47-second turn.

    "Wassup buddy" was not in the enumerated openers, so it took the
    full pipeline: a failed LLM planner (9.69s), a fallback plan that
    made ANOTHER model call, a corpus search, and a refusal.

    The pattern now describes the structure -- an opener, then only
    forms of address and pleasantries, then nothing -- so the list of
    things it covers is not the list of things someone thought of.
    """
    for greeting in (
        "Wassup buddy", "wassup", "whatsup", "what's up", "sup", "yo",
        "yo yo", "heya", "hiya", "howdy", "hey there", "hello hello",
        "hey team", "hi all", "good morning", "morning!", "namaste",
        "namaskar", "kem cho", "hi, how are you?", "hey buddy how's it going",
        "hi again", "hey man", "hey guys", "hiii", "heyyy",
        "yo dude what's new", "good day sir", "hello, nice to meet you",
    ):
        assert classify(greeting).kind == "greeting", greeting


def test_a_loose_greeting_pattern_must_not_swallow_a_real_request():
    """The guard that pays for the looseness above.

    Each of these OPENS with a greeting token and then carries content.
    Matching any of them would answer a plant question from a constant,
    which is the expensive way to be wrong.
    """
    for request in (
        "morning shift handover report",
        "evening summary of the maintenance log",
        "hey can you check the HCU-2 limits",
        "yo what is the MFI for H030SG",
        "hi, what is the reactor temperature limit?",
        "afternoon inspection schedule",
        "good morning, please draft the incident report",
        "sup with the catalyst changeout",
        "hello world program in python",
        "hey, summarise the Hassan incident",
    ):
        assert classify(request).kind != "greeting", request


def test_the_fallback_plan_does_not_call_a_model():
    """The fallback cost more than the planner it replaces.

    On "Wassup buddy" the planner failed after 9.69s and the turn still
    took 47.14s. The missing ~37 seconds were classify_task() -- an LLM
    call, with a retry, forcing a model swap on an 8 GB card -- whose
    entire contribution was choosing between "math" and "reasoning" as
    the label on a step.
    """
    import backend.orchestrator.graph as G
    from backend.orchestrator.state import AgentState

    def _no_plan(*args, **kwargs):
        raise G.PlanningError("planner unavailable in this test")

    def _explode(*args, **kwargs):
        raise AssertionError("the fallback plan must not call a model")

    # THE REQUEST MUST REACH THE FALLBACK. A single-intent lookup is
    # answered by simple_plan() before the LLM planner is ever called,
    # so an earlier version of this test -- "tell me about the reactor"
    # -- passed against the very code it was written to catch. Anything
    # comparative goes to the real planner, which is stubbed to fail.
    request = "compare the reactor limits with the spec and summarise both"
    from backend.orchestrator.simple_intent import is_simple_lookup

    assert not is_simple_lookup(request), "this test needs the planner path"

    original_plan, original_classify = G.plan_request, G.classify_task
    G.plan_request, G.classify_task = _no_plan, _explode
    try:
        out = G.planner_node(AgentState(session_id="t", original_request=request))
    finally:
        G.plan_request, G.classify_task = original_plan, original_classify

    assert [s.step_id for s in out["plan"]] == ["retrieve"]


def test_the_fallback_plan_claims_only_the_work_that_runs():
    """It used to report steps that are no-ops in the dispatcher.

    "Verify engineering calculations and safety envelopes" and
    "Synthesize verified findings into grounded briefing" both dispatch
    to the `reasoning` agent, whose branch is `step.status = "done"`.
    So the trace showed

        step-2  reasoning  done  Verify engineering calculations...

    for a turn in which nothing was verified. Same defect as the
    fabricated approval payload: a record of work that did not happen,
    in the log an operator reads to find out what the system did.
    """
    import backend.orchestrator.graph as G
    from backend.orchestrator.state import AgentState

    def _no_plan(*args, **kwargs):
        raise G.PlanningError("planner unavailable in this test")

    def _no_model(*args, **kwargs):
        raise AssertionError("the fallback plan must not call a model")

    original, original_classify = G.plan_request, G.classify_task
    G.plan_request, G.classify_task = _no_plan, _no_model
    try:
        # Comparative, so it reaches the planner rather than being
        # answered by simple_plan().
        plain = G.planner_node(
            AgentState(
                session_id="t",
                original_request="compare the log entries with the spec and summarise",
            )
        )["plan"]
        with_math = G.planner_node(
            AgentState(session_id="t", original_request="from the log, what is 12 * 4")
        )["plan"]
    finally:
        G.plan_request, G.classify_task = original, original_classify

    assert [s.assigned_agent for s in plain] == ["retrieval"]
    assert all(s.status == "pending" for s in plain), "a plan step starts pending"
    # The math step appears only when there is arithmetic to evaluate,
    # decided by the same local matcher the math branch itself uses.
    assert [s.assigned_agent for s in with_math] == ["retrieval", "math"]
