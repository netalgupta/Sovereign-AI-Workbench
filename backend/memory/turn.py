"""One turn's memory, opened at the start and closed at the end.

WHY THIS MODULE EXISTS AT ALL.

Memory was wired into `synthesize_node` in graph.py -- and nowhere else.
`/api/chat` therefore remembered conversations and `/api/chat/stream`
did not: it never loaded working memory, never resolved a follow-up, and
never RECORDED the turn, so a conversation held on the streaming path
was both amnesiac itself and left holes in the session that later turns
on the other path would read.

That is the third time in this codebase a capability existed on one of
two paths (the intent triage, the source filter, and now this). The
pattern is always the same: two entry points, one implementation, and
nothing forcing them together. So memory is not "also wired into" the
second path here -- it is moved OUT of both and into one pair of
functions that both must call.

    open_turn()   persist the question, load what is remembered,
                  resolve the follow-up, build the context block
    close_turn()  persist the answer with what it actually looked at

Anything that answers a user message calls both. A path that skips them
has no memory, visibly and by construction, rather than silently.

WHAT MEMORY IS ALLOWED TO DO, IN ONE PLACE.

Every block this returns is labelled "context only - NOT a source", and
that labelling is load-bearing rather than decorative: the model is
being handed prior questions, document names and durable preferences,
and if it treats any of them as evidence it will produce an uncited
figure that is indistinguishable from a cited one. The resolver rewrites
the RETRIEVAL QUERY and never the answer. The digest records what was
asked and consulted, never what was answered.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnMemory:
    """What the system remembers, as this turn begins."""

    session_id: str
    # The query retrieval should actually run, which may differ from what
    # the user typed ("give all columns" -> "... Maintenance_Log Q3
    # equipment table"). None means "use the request unchanged".
    search_query: str | None = None
    # Everything memory contributes to the prompt, already labelled.
    context_block: str = ""
    focus_documents: list[str] = field(default_factory=list)
    focus_entities: list[str] = field(default_factory=list)
    added_terms: list[str] = field(default_factory=list)
    # The message row for the question, so the answer can be attached to
    # the right turn and the live window can exclude the question itself.
    user_message_id: str | None = None
    degraded: str | None = None

    @property
    def has_context(self) -> bool:
        return bool(self.context_block)


def open_turn(session_id: str, request: str, *, persist: bool = True) -> TurnMemory:
    """Record the question and assemble everything remembered about it.

    NEVER RAISES. A memory failure degrades the turn to a stateless but
    correct answer; it does not break it. Memory is an improvement, not
    a dependency, and an outage in it must not cost the user their
    question.
    """
    memory = TurnMemory(session_id=session_id)
    try:
        from backend.memory import resolver, working
        from backend.memory.digest import Digest
        from backend.memory.long_term import get_long_term
        from backend.memory.store import get_store

        store = get_store()

        # PERSIST FIRST, then exclude it from the window.
        #
        # Persisting first means a crash mid-turn still leaves the
        # question on record. Excluding it means the working set is
        # "what came BEFORE this", which is what a follow-up resolves
        # against -- without the exclusion the resolver would try to
        # resolve the current question against itself.
        if persist:
            row = store.append(session_id, "user", request)
            memory.user_message_id = row.message_id

        window = working.load(session_id, exclude_message_id=memory.user_message_id)

        blocks: list[str] = []

        # Older turns, condensed. Folded forward on every turn so the
        # cost is one pass over the messages that just fell out of the
        # window, not over the whole session.
        digest = Digest.from_dict(session_id, store.get_digest(session_id))
        fallen_out = store.messages_before(
            session_id, window.oldest_turn_index, after=digest.covers_upto
        )
        if fallen_out:
            digest.fold(fallen_out)
            store.set_digest(session_id, digest.to_dict())
        if not digest.is_empty:
            blocks.append(digest.context_block())

        if not window.is_empty:
            resolved = resolver.resolve(request, window)
            if resolved.changed:
                memory.search_query = resolved.search_query
                memory.added_terms = list(resolved.added_terms)
            blocks.append(window.context_block())
            memory.focus_documents = list(window.focus_documents)
            memory.focus_entities = list(window.focus_entities)

        durable = get_long_term().context_block()
        if durable:
            blocks.append(durable)

        # Offer the user's own message for durable storage. Most are not
        # facts and are rejected; nothing is inferred or guessed.
        try:
            get_long_term().remember(request, source_session=session_id)
        except Exception:  # noqa: BLE001
            pass

        memory.context_block = "".join(blocks)
    except Exception as exc:  # noqa: BLE001
        memory.degraded = f"{type(exc).__name__}: {exc}"

    return memory


def close_turn(
    session_id: str,
    reply: str,
    *,
    route: str | None = None,
    citations: list | None = None,
    documents: list | None = None,
    tool_calls: list | None = None,
    entities: list | None = None,
) -> None:
    """Record the answer and what produced it. Never raises.

    `documents` is kept separate from `citations` on purpose: a
    follow-up like "give all columns" refers to the TABLE the last turn
    READ, which may live in a chunk the answer never explicitly cited.
    `entities` is kept separately again, because the thing a follow-up
    names is often an equipment tag or a pipeline segment rather than a
    filename.
    """
    try:
        from backend.memory.store import get_store

        get_store().append(
            session_id,
            "assistant",
            reply or "",
            route=route,
            citations=(citations or [])[:20],
            documents=documents or [],
            tool_calls=tool_calls or [],
            entities=entities or [],
        )
    except Exception:  # noqa: BLE001 - memory must never break a turn
        pass


def documents_from_chunks(chunks) -> list[str]:
    """The distinct source documents behind a set of retrieved chunks."""
    seen: list[str] = []
    for chunk in chunks or []:
        name = None
        if isinstance(chunk, dict):
            name = chunk.get("source_document")
        else:
            name = getattr(chunk, "source_document", None)
        if name and name not in seen:
            seen.append(name)
    return seen
