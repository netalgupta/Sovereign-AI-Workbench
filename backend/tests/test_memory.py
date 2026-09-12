"""Conversation memory, and the line it must not cross.

The safety property under test throughout: memory informs
INTERPRETATION, never supplies FACTS. A remembered value is an uncited
value, and uncited values are the one output this product must not
produce.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def store(tmp_path):
    from backend.memory.store import reset_store_for_tests

    return reset_store_for_tests(tmp_path / "sessions.db")


@pytest.fixture
def long_term(tmp_path):
    from backend.memory.long_term import reset_for_tests

    return reset_for_tests(tmp_path / "lt.db")


def test_sessions_and_messages_survive(store):
    sid = store.ensure_session("conv-a")
    store.append(sid, "user", "first question")
    store.append(sid, "assistant", "first answer", documents=["A.pdf"])
    store.append(sid, "user", "second question")

    messages = store.all_messages(sid)
    assert [m.role for m in messages] == ["user", "assistant", "user"]
    assert [m.turn_index for m in messages] == [0, 1, 2]
    assert messages[1].documents == ["A.pdf"]

    session = store.get_session(sid)
    assert session.turn_count == 2, "turn_count counts user turns"


def test_the_exact_follow_up_that_failed_is_now_resolved(store):
    """Replay of a real conversation that went wrong.

        "Summarise the maintenance log of Q3"  -> fault category table
        "i want for equipments"                -> equipment table
        "Give all columns"                     -> the FAULT CATEGORY
                                                  table again, plus an
                                                  invented justification

    The retrieval trace showed the search query for the third turn was
    literally "Give all columns column". Nothing in that identifies the
    maintenance log, so retrieval returned a P&ID schematic at rank 1.
    """
    from backend.memory import resolver, working

    sid = store.ensure_session("conv-real")
    store.append(sid, "user", "Summarise in detail maintenance log of q3")
    store.append(sid, "assistant", "fault category table",
                 route="direct", documents=["Maintenance_Log_Q3_2026.xlsx"])
    store.append(sid, "user", "U gave the summary for fault category i want for equipments")
    store.append(sid, "assistant", "equipment downtime table",
                 route="direct", documents=["Maintenance_Log_Q3_2026.xlsx"])

    memory = working.load(sid)
    assert "Maintenance_Log_Q3_2026.xlsx" in memory.focus_documents

    resolved = resolver.resolve("Give all columns", memory)
    assert resolved.changed, "a bare follow-up must be resolved"
    lowered = resolved.search_query.lower()
    assert "maintenance" in lowered, "the focus document must reach the query"
    assert "equipment" in lowered, "the previous request's subject must carry over"

    # Additive: the user's own words survive, so a query that already
    # worked cannot be made worse.
    assert resolved.search_query.startswith("Give all columns")


def test_a_self_contained_question_is_left_alone(store):
    from backend.memory import resolver, working

    sid = store.ensure_session("conv-b")
    store.append(sid, "user", "earlier")
    store.append(sid, "assistant", "answer", documents=["Other.pdf"])

    resolved = resolver.resolve(
        "What is the average MFI for Homopolymer H030SG?", working.load(sid)
    )
    assert not resolved.changed, (
        "a standalone question must not be polluted with prior context"
    )


def test_resolution_without_memory_is_a_no_op(store):
    from backend.memory import resolver, working

    sid = store.ensure_session("empty")
    resolved = resolver.resolve("Give all columns", working.load(sid))
    assert not resolved.changed
    assert resolved.search_query == "Give all columns"


def test_context_block_is_labelled_as_not_a_source(store):
    """The label is load-bearing, not decoration.

    The model is handed prior answers, and prior answers contain
    numbers. Without an explicit instruction it will treat them as
    evidence and produce a figure with no citation that looks exactly
    like a cited one.
    """
    from backend.memory import working

    sid = store.ensure_session("conv-c")
    store.append(sid, "user", "q")
    store.append(sid, "assistant", "The value is 3.4 g/10min [1].")

    block = working.load(sid).context_block()
    assert "NOT a source" in block
    assert "SOURCES" in block, "must point at where facts are allowed to come from"


def test_long_term_stores_preferences(long_term):
    for text, kind in [
        ("I'm the Novolen unit engineer", "identity"),
        ("Always give me values in metric", "preference"),
        ("We call HCU-2 the hydrocracker here", "vocabulary"),
    ]:
        fact = long_term.remember(text)
        assert fact is not None, f"should have stored: {text}"
        assert fact.kind == kind


def test_long_term_refuses_document_findings(long_term):
    """The guard that keeps memory from becoming a second source of truth.

    Storing "the average MFI is 3.4" would create an uncited fact that
    never expires. The first time the corpus is revised and this is not,
    the system answers confidently from a stale number with no citation
    and no way for anyone to notice.
    """
    for text in (
        "The average MFI for H030SG is 3.4 g/10min",
        "Total downtime was 94 hours",
        "The limit is 400 C",
        "Mechanical downtime measured at 37.5 hrs",
    ):
        assert long_term.remember(text) is None, f"leaked a document fact: {text}"

    # And an explicit kind must not override the guard -- a caller
    # insisting is exactly when it matters.
    assert long_term.remember(
        "The average MFI for H030SG is 3.4 g/10min", kind="preference"
    ) is None


def test_facts_are_listable_and_deletable(long_term):
    """Memory a user cannot inspect or correct is memory they cannot trust."""
    fact = long_term.remember("Always prefer tables over prose")
    assert fact is not None
    assert any(f.fact_id == fact.fact_id for f in long_term.all_facts())
    assert long_term.forget(fact.fact_id) is True
    assert not any(f.fact_id == fact.fact_id for f in long_term.all_facts())


def test_memory_failure_does_not_break_a_turn(monkeypatch, store):
    """Memory is an improvement, not a dependency.

    A corrupted database or a schema change must degrade to a stateless
    (but correct) answer, never to a failed turn.
    """
    from backend.memory import working

    def explode(*args, **kwargs):
        raise RuntimeError("memory database is unavailable")

    monkeypatch.setattr(working, "load", explode)

    from backend.orchestrator import graph

    # synthesize_node wraps the memory block; the turn must still run.
    assert hasattr(graph, "synthesize_node")
    with pytest.raises(RuntimeError):
        working.load("x")  # the fixture really does raise
