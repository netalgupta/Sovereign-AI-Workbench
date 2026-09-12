"""Turn a follow-up into a question that can be retrieved on its own.

THE BUG THIS FIXES, VERBATIM FROM A REAL CONVERSATION.

    user: "Summarise in detail maintenance log of q3 ..."
      ->  a table of downtime BY FAULT CATEGORY

    user: "U gave the summary for fault category i want for equipments"
      ->  a table of downtime BY EQUIPMENT     (correct, by luck)

    user: "Give all columns"
      ->  the FAULT CATEGORY table again, plus an invented justification:
          "the downtime for Mechanical and Catalyst-Related are
           highlighted in bold as they were specifically asked to be
           given in a single figure"

Nobody asked for that. The model was explaining a table it could not
remember producing.

The retrieval trace shows why. The search query for the third turn was
literally `Give all columns column` — the user's words, with one
synonym added. Nothing in that string identifies the maintenance log,
the equipment table, or anything else. Retrieval returned a P&ID
schematic at rank 1.

A follow-up is not a standalone question, and retrieval can only work on
standalone questions.

WHY REWRITING THE QUERY AND NOT JUST ADDING CHAT HISTORY.

Adding history to the generation prompt helps the model UNDERSTAND the
question. It does nothing for retrieval, which runs first and decides
what the model is allowed to see. If retrieval fetches the wrong table,
no amount of history recovers it — the right rows are simply absent.
So the fix has to happen before retrieval, on the query itself.

WHAT IT IS FORBIDDEN FROM DOING.

It rewrites the RETRIEVAL QUERY ONLY. The request shown to the model
stays verbatim, so the answer addresses what the user actually typed.
And it never injects an ANSWER — a resolver that pulled the previous
answer's numbers forward would produce uncited facts, which is the one
thing this product must not do. It adds subject nouns and document
names; it does not add values.

RULE-BASED, NOT A MODEL CALL.

A model call here costs as much as a short answer and adds a failure
mode where the rewrite itself hallucinates a subject. The signal is
structural — short queries, leading pronouns, comparative and
continuation markers — and the expansion material comes from the
session's own history rather than from a model's imagination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A query this short is almost never self-contained.
SHORT_QUERY_WORDS = 6

# Openers that point at something already said.
_REFERENTIAL = re.compile(
    r"^\s*(also|and|what about|how about|ok(ay)?\s|now\s|then\s|"
    r"give|show|list|display|include|add|expand|elaborate|continue|more|"
    r"that|those|these|this|it|its|them|their|same|again|instead)\b",
    re.I,
)

# Pronouns and deictics with no antecedent in the query itself.
_DANGLING = re.compile(
    r"\b(it|its|that|those|these|this|them|their|the same|the above|"
    r"the previous|the last|the other|the rest|all of (it|them))\b",
    re.I,
)

# Words that describe the SHAPE of a prior answer rather than a subject.
_SHAPE_ONLY = re.compile(
    r"\b(columns?|rows?|fields?|table|list|entries|items|details|"
    r"metrics?|numbers?|figures?|values?|breakdown|summary)\b",
    re.I,
)

# Content words worth carrying forward from the previous request. Long
# enough to be meaningful, not a stopword, not a shape word.
_STOPWORDS = frozenset("""
a an the and or but if of in on at to for from by with without is are was
were be been being do does did have has had i you we they me my your our
please give show tell list all some any what which who how when where why
also more can could should would will about abt detail detailed
gave give given want wants wanted need needs needed get gets got make makes
made using used use via per like just only very much many such other another
here there now then again back next previous last first thing things stuff
""".split())


@dataclass
class ResolvedQuery:
    original: str
    search_query: str
    added_terms: list[str]
    reason: str

    @property
    def changed(self) -> bool:
        return self.search_query != self.original


def _content_terms(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[^A-Za-z0-9._-]+", text or ""):
        token = raw.strip("._-")
        if len(token) < 3:
            continue
        low = token.lower()
        if low in _STOPWORDS or low in seen:
            continue
        if _SHAPE_ONLY.fullmatch(low):
            continue
        seen.add(low)
        out.append(token)
    return out


def _document_subject(filename: str) -> list[str]:
    """Turn a filename into searchable subject words.

    'Maintenance_Log_Q3_2026.xlsx' -> ['Maintenance', 'Log', 'Q3', '2026']

    The filename is a strong subject signal precisely because it was
    written by a human to describe the contents, and it is the one piece
    of context guaranteed to exist for every document in focus.
    """
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename or "")
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", stem) if len(p) > 1]
    return parts[:6]


def needs_resolution(query: str) -> bool:
    """Is this a follow-up that cannot be retrieved on its own?"""
    text = (query or "").strip()
    if not text:
        return False

    words = text.split()
    if len(words) <= SHORT_QUERY_WORDS:
        return True
    if _REFERENTIAL.match(text):
        return True
    if _DANGLING.search(text):
        return True

    # Contains only shape words and no subject: "give all the columns
    # and rows with their values".
    if not _content_terms(text):
        return True

    return False


def resolve(query: str, memory) -> ResolvedQuery:
    """Expand a follow-up using the session's working memory.

    Additive: the user's words are always preserved, so a query that
    already worked cannot be made worse.
    """
    original = (query or "").strip()

    if memory is None or memory.is_empty:
        return ResolvedQuery(original, original, [], "No prior turns in this session.")

    if not needs_resolution(original):
        return ResolvedQuery(
            original, original, [], "Self-contained — no resolution needed."
        )

    existing = {t.lower() for t in _content_terms(original)}
    additions: list[str] = []

    def add(term: str) -> None:
        low = (term or "").lower()
        if low and low not in existing and low not in _STOPWORDS:
            existing.add(low)
            additions.append(term)

    # 1. Documents the conversation is working in. Strongest signal:
    #    a human named the file after its contents.
    for filename in memory.focus_documents[:2]:
        for word in _document_subject(filename):
            add(word)

    # 2. Subject nouns from the previous user request, so "give all
    #    columns" inherits "equipments" from "i want for equipments".
    if memory.last_user_request:
        for term in _content_terms(memory.last_user_request)[:6]:
            add(term)

    if not additions:
        return ResolvedQuery(
            original, original, [], "Nothing in memory to resolve against."
        )

    search_query = f"{original} {' '.join(additions)}"
    return ResolvedQuery(
        original,
        search_query,
        additions,
        f"Follow-up resolved against {len(memory.focus_documents)} focus "
        f"document(s) and the previous request.",
    )
