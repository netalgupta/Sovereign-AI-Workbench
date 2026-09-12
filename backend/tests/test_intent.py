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
