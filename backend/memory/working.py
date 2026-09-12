"""Short-term memory: what this conversation is currently about.

The recent turns, plus the two things a follow-up almost always refers
to — the documents in focus, and the shape of the last answer.

WHY "FOCUS DOCUMENTS" IS A SEPARATE IDEA FROM "RECENT MESSAGES".

Feeding the last few turns to the model as chat history is the obvious
move and it is not enough, because the failure is in RETRIEVAL, not in
generation. "Give all columns" retrieves against the literal words "give
all columns", which match nothing in particular, so the model receives
the wrong chunks no matter how much history it is shown. Measured: that
exact follow-up re-retrieved the fault-category table when the user
meant the equipment table from the turn before.

So the documents a conversation is working in are tracked explicitly and
used to steer retrieval, not just to pad the prompt.

THE LINE THIS FILE MUST NOT CROSS.

`context_block()` is labelled as CONVERSATION CONTEXT and says in the
text that it is not a source. That labelling is load-bearing: the model
is being handed prior answers, and prior answers contain numbers. If it
treats them as evidence it will produce an uncited figure that looks
exactly like a cited one. Facts come from retrieval, every turn, or the
grounding claim is worthless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# How many prior messages to carry. Small on purpose: the working set is
# for resolving references like "it", "those", "all columns", and those
# almost always point at the immediately preceding exchange. A longer
# window costs context tokens -- which measurably matters, since the
# generation prompt already ran into its window once -- and increases
# the chance the model answers from history instead of from sources.
DEFAULT_WINDOW = 6

# A document stops being "in focus" after this many turns without being
# retrieved again. Without decay, a conversation that moves from the
# maintenance log to the incident report keeps steering retrieval back
# towards the maintenance log.
FOCUS_DECAY_TURNS = 3


@dataclass
class WorkingMemory:
    session_id: str
    messages: list = field(default_factory=list)
    focus_documents: list[str] = field(default_factory=list)
    last_user_request: str | None = None
    last_answer: str | None = None
    last_route: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.messages

    def context_block(self, max_chars: int = 1800) -> str:
        """Prior turns, formatted for a prompt and labelled as context.

        Returns "" when there is nothing, so callers can concatenate
        unconditionally without producing an empty labelled section that
        implies context exists.
        """
        if not self.messages:
            return ""

        lines: list[str] = [
            "",
            "CONVERSATION SO FAR (context only — NOT a source):",
            "Use this to understand what the current question refers to. "
            "Do NOT state facts from it. Every factual claim in your answer "
            "must come from the SOURCES section and carry its citation, "
            "including facts you can see in your own previous answers.",
            "",
        ]
        budget = max_chars
        rendered: list[str] = []
        # Newest first while spending the budget, then reversed, so the
        # most relevant turn survives truncation rather than the oldest.
        for message in reversed(self.messages):
            who = "User" if message.role == "user" else "You"
            text = re.sub(r"\s+", " ", message.content).strip()
            if len(text) > 600:
                text = text[:600] + " …"
            entry = f"{who}: {text}"
            if len(entry) > budget:
                break
            budget -= len(entry)
            rendered.append(entry)
        lines.extend(reversed(rendered))
        lines.append("")
        return "\n".join(lines)


def load(session_id: str, window: int = DEFAULT_WINDOW) -> WorkingMemory:
    """Build the working set for this session."""
    from backend.memory.store import get_store

    store = get_store()
    messages = store.recent(session_id, limit=window)

    memory = WorkingMemory(session_id=session_id, messages=messages)

    for message in reversed(messages):
        if message.role == "user" and memory.last_user_request is None:
            memory.last_user_request = message.content
        if message.role == "assistant" and memory.last_answer is None:
            memory.last_answer = message.content
            memory.last_route = message.route

    # Focus = documents seen in the recent window, most recent first,
    # deduplicated. Recency decay is implicit in the window size.
    seen: set[str] = set()
    focus: list[str] = []
    recent_assistant = [m for m in messages if m.role == "assistant"]
    for message in reversed(recent_assistant[-FOCUS_DECAY_TURNS:]):
        for name in message.documents or []:
            if name and name not in seen:
                seen.add(name)
                focus.append(name)
    memory.focus_documents = focus

    return memory
