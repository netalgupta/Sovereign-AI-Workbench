"""What happened earlier in a conversation, once it falls out of the window.

THE GAP THIS CLOSES. `working.py` carries the last six messages -- three
exchanges. Everything before that was not condensed, it was simply
absent. Ask a question on turn nine that refers to something from turn
two and the system has no idea what you mean, with no signal that it has
forgotten.

WHY THIS IS EXTRACTIVE AND NOT A MODEL SUMMARY.

The obvious implementation is to ask the reasoning model to summarise
the older turns. It is also the one implementation this repo must not
ship. A generated summary of a conversation can state that an earlier
answer said something it did not -- and a fabricated "you already
established that the limit is 380 C" is the uncited-number failure in
its most dangerous form, because it arrives with the authority of the
system's own memory and carries no citation to check. This codebase has
already shipped a template that wrote "All parameters remain within
nominal design thresholds" from zero evidence. A summariser is the same
shape of mistake with a model behind it.

It would also cost a model call per turn on a box where the planner and
the verifier already fight over 8 GB of VRAM.

So the digest is built by extraction and it records two things only:

    what was ASKED        the user's own words, truncated, verbatim
    what was CONSULTED    document names and tool names

and deliberately NOT what was ANSWERED. Answers contain numbers.
A condensed number separated from its citation is exactly the artifact
that makes a grounded system ungrounded, and no amount of labelling
fixes it once the figure is in the prompt. If a later turn needs a value
from an earlier answer, it must retrieve it again -- which is cheap,
correct, and carries a citation.

WHAT THIS BUYS. "What was that SOP I asked about earlier?" resolves,
because the question is in the digest verbatim. "What did you say the
MFI was?" does not resolve from memory -- it retrieves again. Both of
those are the right outcome.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Older turns are condensed rather than carried. This is the number of
# QUESTIONS kept; documents and tools are kept as sets, which do not
# grow with conversation length.
MAX_QUESTIONS = 12
MAX_QUESTION_CHARS = 110
MAX_DOCUMENTS = 14


@dataclass
class Digest:
    """A condensed record of the turns that no longer fit in the window."""

    session_id: str
    turns: int = 0
    first_at: float | None = None
    last_at: float | None = None
    questions: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    # The highest turn_index already folded in, so the digest is built
    # incrementally rather than recomputed over the whole session.
    covers_upto: int = -1

    @property
    def is_empty(self) -> bool:
        return self.turns == 0

    def to_dict(self) -> dict:
        return {
            "turns": self.turns,
            "first_at": self.first_at,
            "last_at": self.last_at,
            "questions": self.questions,
            "documents": self.documents,
            "tools": self.tools,
            "covers_upto": self.covers_upto,
        }

    @classmethod
    def from_dict(cls, session_id: str, raw: dict | None) -> Digest:
        raw = raw or {}
        return cls(
            session_id=session_id,
            turns=int(raw.get("turns") or 0),
            first_at=raw.get("first_at"),
            last_at=raw.get("last_at"),
            questions=list(raw.get("questions") or []),
            documents=list(raw.get("documents") or []),
            tools=list(raw.get("tools") or []),
            covers_upto=int(raw.get("covers_upto", -1)),
        )

    def fold(self, messages: list) -> Digest:
        """Add `messages` to the digest. Only ever moves forward.

        Messages at or below `covers_upto` are ignored, so calling this
        repeatedly with overlapping ranges cannot double-count a turn --
        which matters because the caller folds on every turn and the
        window slides by one at a time.
        """
        for message in messages:
            if message.turn_index <= self.covers_upto:
                continue
            self.covers_upto = max(self.covers_upto, message.turn_index)

            if self.first_at is None or message.created_at < self.first_at:
                self.first_at = message.created_at
            self.last_at = max(self.last_at or 0.0, message.created_at)

            if message.role == "user":
                self.turns += 1
                text = " ".join((message.content or "").split())
                if text:
                    if len(text) > MAX_QUESTION_CHARS:
                        text = text[:MAX_QUESTION_CHARS].rstrip() + " ..."
                    # Newest questions are the ones a follow-up refers
                    # to, so the list is trimmed from the FRONT.
                    self.questions.append(text)
                    if len(self.questions) > MAX_QUESTIONS:
                        self.questions = self.questions[-MAX_QUESTIONS:]

            for name in message.documents or []:
                if name and name not in self.documents:
                    self.documents.append(name)
            if len(self.documents) > MAX_DOCUMENTS:
                self.documents = self.documents[-MAX_DOCUMENTS:]

            for call in message.tool_calls or []:
                name = call.get("tool_name") if isinstance(call, dict) else None
                if name and name not in self.tools:
                    self.tools.append(name)

        return self

    def context_block(self) -> str:
        """The digest as prompt text, labelled the same way as everything
        else memory contributes: context, never a source."""
        if self.is_empty:
            return ""

        when = ""
        if self.first_at and self.last_at:
            span = max(0.0, self.last_at - self.first_at)
            when = f", spanning {_humanise(span)}"

        lines = [
            "",
            "EARLIER IN THIS CONVERSATION (condensed, context only - NOT a source):",
            f"{self.turns} earlier question(s){when}, condensed because they no "
            "longer fit in the live window. This records what was ASKED and what "
            "was CONSULTED. It deliberately does NOT record what was answered: "
            "any figure you need must be retrieved again, with its citation.",
            "",
        ]
        if self.questions:
            lines.append("Questions asked earlier:")
            lines += [f"- {q}" for q in self.questions]
            lines.append("")
        if self.documents:
            lines.append("Documents already consulted: " + ", ".join(self.documents))
            lines.append("")
        if self.tools:
            lines.append("Tools already used: " + ", ".join(self.tools))
            lines.append("")
        return "\n".join(lines)


def _humanise(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{int(seconds // 60)} min"
    if seconds < 172800:
        return f"{int(seconds // 3600)} h"
    return f"{int(seconds // 86400)} days"


def now() -> float:
    return time.time()
