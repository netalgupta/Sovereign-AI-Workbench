"""Conversation memory, and the line it must not cross.

The safety property under test throughout: memory informs
INTERPRETATION, never supplies FACTS. A remembered value is an uncited
value, and uncited values are the one output this product must not
produce.
"""


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


# ---------------------------------------------------------------------
# MEMORY HAS TO EXIST ON BOTH PATHS.
#
# It was wired into graph.py's synthesize_node and nowhere else, so
# /api/chat remembered conversations and /api/chat/stream did not -- it
# never loaded working memory, never resolved a follow-up, and never
# RECORDED the turn, so it also left holes in sessions that the other
# endpoint would later read. Third instance of the same shape in this
# codebase (intent triage, source filter, this).
# ---------------------------------------------------------------------


def _fresh(tmp_path):
    from backend.memory import long_term, store

    store.reset_store_for_tests(tmp_path / "sessions.db")
    long_term.reset_for_tests(tmp_path / "long_term.db")
    return store.get_store()


def test_both_endpoints_record_into_the_same_session(tmp_path):
    from backend.orchestrator.agent_loop import run_turn
    from backend.orchestrator.graph import run_agent_turn

    store = _fresh(tmp_path)
    session = "cross-path"

    list(run_turn("Hi", session_id=session))          # streaming path
    run_agent_turn("thanks", session)                  # non-streaming path
    list(run_turn("what can you do", session_id=session))

    rows = store.all_messages(session)
    assert [r.role for r in rows] == [
        "user", "assistant", "user", "assistant", "user", "assistant"
    ], "a turn went unrecorded on one of the two paths"

    # The route each turn took is recorded, because "I refused for lack
    # of sources" and "I answered from a constant" read identically in
    # the text and mean opposite things to the turn that follows.
    assert [r.route for r in rows if r.role == "assistant"] == [
        "greeting", "closing", "capability"
    ]


def test_the_next_turn_sees_the_conversation_from_either_path(tmp_path):
    from backend.memory.turn import open_turn
    from backend.orchestrator.agent_loop import run_turn

    _fresh(tmp_path)
    list(run_turn("Hi", session_id="s"))

    peek = open_turn("s", "and the hydrocracker?", persist=False)
    assert peek.degraded is None
    assert "CONVERSATION SO FAR" in peek.context_block
    # Labelled, always. The model is being handed prior answers, and
    # prior answers contain numbers.
    assert "NOT a source" in peek.context_block


def test_the_question_being_answered_is_not_part_of_its_own_history(tmp_path):
    """It is persisted first so a crash still records it, and excluded
    from the window so the resolver does not resolve it against itself."""
    from backend.memory import working
    from backend.memory.turn import open_turn

    store = _fresh(tmp_path)
    store.append("s", "user", "What is the MFI for H030SG?")
    store.append("s", "assistant", "3.4 g/10min [1]", documents=["Novolen.pdf"])

    memory = open_turn("s", "and the density?")
    window = working.load("s", exclude_message_id=memory.user_message_id)

    assert "and the density?" not in [m.content for m in window.messages]
    assert store.all_messages("s")[-1].content == "and the density?"


# ---------------------------------------------------------------------
# Turns that fall out of the six-message window.
# ---------------------------------------------------------------------


def test_turns_that_fall_out_of_the_window_are_condensed_not_dropped(tmp_path):
    from backend.memory.turn import open_turn

    store = _fresh(tmp_path)
    for i in range(8):
        store.append("s", "user", f"question about topic {i}")
        store.append(
            "s", "assistant", f"answer {i}",
            documents=[f"doc{i}.pdf"],
            tool_calls=[{"tool_name": "search_documents"}],
        )

    memory = open_turn("s", "what did I ask you first?", persist=False)
    block = memory.context_block

    assert "EARLIER IN THIS CONVERSATION" in block
    # The oldest question is outside the live window and survives only
    # because the digest kept it.
    assert "question about topic 0" in block
    assert "doc0.pdf" in block


def test_the_digest_records_what_was_asked_never_what_was_answered(tmp_path):
    """The line this feature must not cross.

    A generated summary can state that an earlier answer said something
    it did not, and a fabricated "you already established the limit is
    380 C" is the uncited-number failure at its worst: it arrives with
    the authority of the system's own memory and carries no citation to
    check. So the digest is extractive, and it keeps questions and
    document names only.
    """
    from backend.memory.turn import open_turn

    store = _fresh(tmp_path)
    for i in range(8):
        store.append("s", "user", f"question {i}")
        store.append(
            "s", "assistant",
            f"The measured value is {400 + i} degrees C [1]",
            documents=["Spec.pdf"],
        )

    block = open_turn("s", "next", persist=False).context_block
    digest_part = block.split("CONVERSATION SO FAR")[0]

    assert "question 0" in digest_part
    for value in range(400, 404):
        assert str(value) not in digest_part, (
            f"{value} came from an ANSWER and must not survive condensation "
            "without its citation"
        )


def test_folding_the_digest_twice_does_not_double_count(tmp_path):
    """It folds on every turn while the window slides by one, so
    overlapping ranges are the normal case, not an edge case."""
    from backend.memory.digest import Digest

    store = _fresh(tmp_path)
    for i in range(10):
        store.append("s", "user", f"q{i}")
        store.append("s", "assistant", f"a{i}")

    digest = Digest.from_dict("s", {})
    first = store.messages_before("s", 14, after=digest.covers_upto)
    digest.fold(first)
    turns = digest.turns

    digest.fold(store.messages_before("s", 14, after=-1))
    assert digest.turns == turns, "a re-fold double-counted turns"


# ---------------------------------------------------------------------
# Entity memory.
# ---------------------------------------------------------------------


def test_entities_are_recorded_and_are_shape_anchored(tmp_path):
    """A follow-up names "HCU-2" far more often than it names a file.

    Matched on shape rather than inferred: an entity recorded here
    steers the NEXT turn's retrieval, so a model's guess would silently
    bias a later answer.
    """
    from backend.orchestrator.graph import _entities_in

    found = _entities_in([
        {"text": "Reactor HCU-2 tripped when FFC-201 exceeded its setpoint."},
        {"text": "See SOP-114-Rev3 for the changeout procedure."},
        {"text": "The Mangalore-Hassan pipeline segment was isolated."},
    ])
    assert "HCU-2" in found
    assert "FFC-201" in found
    assert "SOP-114-Rev3" in found
    assert any("Mangalore-Hassan" in f for f in found)

    # Ordinary prose is not an entity.
    assert _entities_in([
        {"text": "The operator checked the reactor and found nothing unusual."}
    ]) == []


def test_focus_entities_decay_like_focus_documents(tmp_path):
    from backend.memory import working

    store = _fresh(tmp_path)
    store.append("s", "assistant", "old", entities=["OLD-1"])
    for i in range(4):
        store.append("s", "user", f"q{i}")
        store.append("s", "assistant", f"a{i}", entities=[f"NEW-{i}"])

    memory = working.load("s")
    assert "OLD-1" not in memory.focus_entities, "an entity never decayed"
    assert "NEW-3" in memory.focus_entities


# ---------------------------------------------------------------------
# Schema migration.
# ---------------------------------------------------------------------


def test_a_database_from_an_earlier_build_gains_the_new_columns(tmp_path):
    """CREATE TABLE IF NOT EXISTS does nothing to a table that exists.

    Without a migration the schema change is invisible to everyone who
    already has the file, and surfaces later as "no such column" from a
    query, while somebody is using it.
    """
    import sqlite3

    from backend.memory import store as S

    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript(
        """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY, title TEXT,
            created_at REAL NOT NULL, updated_at REAL NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE messages (
            message_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, created_at REAL NOT NULL
        );
        """
    )
    old.execute(
        "INSERT INTO sessions VALUES ('s', NULL, 1.0, 1.0, 1)"
    )
    old.execute(
        "INSERT INTO messages VALUES ('m1', 's', 0, 'user', 'older turn', 1.0)"
    )
    old.commit()
    old.close()

    store = S.reset_store_for_tests(path)

    # The pre-existing row still reads, with the new fields empty rather
    # than raising.
    rows = store.all_messages("s")
    assert [r.content for r in rows] == ["older turn"]
    assert rows[0].entities == []
    assert store.get_digest("s") == {}

    # And the new columns are writable.
    store.append("s", "assistant", "new turn", entities=["HCU-2"])
    assert store.all_messages("s")[-1].entities == ["HCU-2"]


# ---------------------------------------------------------------------
# (d) Facts that never expire and never conflict.
# ---------------------------------------------------------------------


def test_a_new_statement_on_the_same_subject_replaces_the_old_one(tmp_path):
    """Dedup was exact-string only, which catches a repetition and
    misses every actual change. "I work on HCU" and "I moved to CCR"
    both persisted and both got injected, handing the model a
    contradiction about the user with no way to tell which is current."""
    from backend.memory import long_term as L

    memory = L.reset_for_tests(tmp_path / "lt.db")
    old = memory.remember("I work on the hydrocracker unit")
    new = memory.remember("I work in CCR now")

    active = [f.content for f in memory.all_facts()]
    assert new.content in active
    assert old.content not in active, "both sides of a contradiction are live"

    # Marked, not deleted: "I used to work on HCU" is part of the record,
    # and a memory that quietly rewrites itself cannot be audited.
    archived = {f.content: f for f in memory.all_facts(include_superseded=True)}
    assert archived[old.content].superseded_by == new.fact_id
    assert archived[old.content].superseded_at is not None


def test_facts_on_different_subjects_both_stand(tmp_path):
    """Two statements conflict when they answer the same question about
    the same thing. A unit and an output preference do not."""
    from backend.memory import long_term as L

    memory = L.reset_for_tests(tmp_path / "lt.db")
    memory.remember("I work on the hydrocracker unit")
    memory.remember("always answer in bullet points")

    contents = [f.content for f in memory.all_facts()]
    assert len(contents) == 2, contents


def test_an_unrecognised_statement_supersedes_nothing(tmp_path):
    """None means "cannot supersede and cannot be superseded", which is
    the safe direction: an unrecognised statement sits alongside what
    came before rather than silently replacing it."""
    from backend.memory.long_term import subject_of

    assert subject_of("I work on the hydrocracker") == "unit"
    assert subject_of("my name is Aryan") == "name"
    assert subject_of("please use metric units") is None


def test_a_fact_nothing_has_used_for_a_long_time_is_retired(tmp_path):
    """Never expiring means a stale preference shapes every answer
    forever with no signal that it is doing so."""
    import time

    from backend.memory import long_term as L

    memory = L.reset_for_tests(tmp_path / "lt.db")
    fact = memory.remember("always answer in bullet points")

    # Backdate it beyond the TTL.
    old_ts = time.time() - (L.DEFAULT_TTL_DAYS + 1) * 86400
    memory._conn.execute(
        "UPDATE facts SET created_at = ?, last_used = NULL WHERE fact_id = ?",
        (old_ts, fact.fact_id),
    )
    memory._conn.commit()

    retired = memory.expire_stale()
    assert [f.fact_id for f in retired] == [fact.fact_id]
    assert memory.all_facts() == []
    # Retired, not erased.
    assert len(memory.all_facts(include_superseded=True)) == 1


def test_staleness_is_measured_from_last_use_not_from_creation(tmp_path):
    """A preference that keeps being applied is evidently still wanted."""
    import time

    from backend.memory import long_term as L

    memory = L.reset_for_tests(tmp_path / "lt.db")
    fact = memory.remember("always answer in bullet points")
    memory._conn.execute(
        "UPDATE facts SET created_at = ?, last_used = ? WHERE fact_id = ?",
        (time.time() - 400 * 86400, time.time() - 86400, fact.fact_id),
    )
    memory._conn.commit()

    assert memory.expire_stale() == [], "a fact in active use was retired"


# ---------------------------------------------------------------------
# (e) The same question, asked again.
# ---------------------------------------------------------------------


def test_the_episodic_key_covers_every_input_that_changes_the_answer():
    """A cache is dangerous when the INPUTS changed, not when it is
    reused. This repo has five recorded instances of a cached view of
    something that had moved."""
    from backend.memory import episodic

    def key(**kwargs):
        base = dict(
            corpus_generation=1, top_k=5, model_id="m", active_documents=None
        )
        base.update(kwargs)
        return episodic.key_for(base.pop("query", "what is the MFI"), **base)

    same = key()
    assert key(query="What  is   the MFI") == same, "wording is normalised"
    assert key(corpus_generation=2) != same, "a re-ingest must invalidate"
    assert key(top_k=8) != same
    assert key(model_id="other") != same
    assert key(conversation_context="prior turn") != same
    # None (no filter) and [] (everything switched off) are different
    # instructions and must not collide.
    assert key(active_documents=[]) != same
    assert key(active_documents=["a.pdf"]) != key(active_documents=[])


def test_a_refusal_is_never_stored():
    """"Not found" is the answer most likely to change for reasons the
    key cannot see -- the user adds the missing document. A cached
    refusal keeps saying no after the gap is fixed."""
    from backend.memory import episodic

    episodic.clear()

    class Refusal:
        found = False

    class Answer:
        found = True

    episodic.remember("k-refusal", Refusal())
    episodic.remember("k-answer", Answer())

    assert episodic.recall("k-refusal") is None
    assert episodic.recall("k-answer") is not None


def test_the_episodic_store_is_bounded():
    from backend.memory import episodic

    episodic.clear()

    class Answer:
        found = True

    for i in range(episodic.MAX_ENTRIES + 20):
        episodic.remember(f"k{i}", Answer())
    assert episodic.stats()["entries"] == episodic.MAX_ENTRIES


def test_the_corpus_read_is_cached_and_invalidated_by_ingestion():
    """all_chunk_texts is a full read of the corpus and runs three times
    per query. At 52 documents that is invisible; at the 1000-page PDFs
    this is for, it is the dominant cost of a sub-second search."""
    import numpy as np

    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
    from backend.retrieval.vector_store import VectorStore

    def chunks(n, offset=0):
        made = [
            IngestedChunk(
                text=f"chunk {i + offset}",
                metadata=ChunkMetadata(
                    source_document="d.pdf",
                    document_type="pdf",
                    page_number=1,
                    chunk_index=i + offset,
                    ingestion_date="2026-01-01",
                ),
            )
            for i in range(n)
        ]
        return made, np.random.rand(n, 8).astype("float32")

    store = VectorStore(dim=8)
    store.add_chunks(*chunks(10))
    first = store.all_chunk_texts()
    assert store.all_chunk_texts() is first, "the corpus was re-read unchanged"

    generation = store.generation
    store.add_chunks(*chunks(3, offset=10))
    assert store.generation > generation, "ingestion did not move the generation"
    assert len(store.all_chunk_texts()) == 13, "a stale corpus view survived ingest"
