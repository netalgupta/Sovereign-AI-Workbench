"""Turn what a user typed into what the retriever should search for.

WHY THIS EXISTS. People type imperatives and abbreviations, and the
retriever scores them literally. Measured on this corpus:

    "Give sops for Hydrocrackers"      -> SOP-114-Rev3 ranked 4th of 5
    "Tell me about the SOP for the
     hydrocracker catalyst changeout"  -> ranked 1st

Same question, same corpus, same retriever. The difference is entirely
in the wording: "sops" is a plural the documents never use, the
documents say "Standard Operating Procedure" and "SOP-114", and
"Hydrocrackers" is a plural of a unit that is always written singular
or as "HCU-2". Meanwhile "Give" and "for" contribute nothing but do
occupy the embedding.

Rank matters beyond ordering, because the top-k chunks become the
SOURCES block in prompt order. A document at rank 4 of 5 is buried near
the end of ~5000 characters of context, and the model answers from what
is nearest the question. The thin, metadata-only answer to "Give sops
for Hydrocrackers" -- document number, effective date, review cycle,
and none of the actual procedure -- is what late-ranked context looks
like.

WHAT THIS DELIBERATELY DOES NOT DO.

  - It does not rewrite the user's request as shown to the model. The
    REQUEST line in the prompt stays verbatim, so the answer addresses
    what was actually asked. Only the RETRIEVAL query is expanded.
  - It does not invent domain facts. Every expansion below is a surface
    form of a term that already appears in the corpus vocabulary, and
    expansions whose target is absent from the corpus are dropped at
    runtime. An expansion that adds unseen words would push retrieval
    towards documents that do not exist.
  - It does not drop the original terms. Expansion is additive, so a
    query that already worked cannot be made worse by it.
"""

from __future__ import annotations

import re

from backend.retrieval import lexical

# Domain surface forms. LEFT is what people type, RIGHT is the wording
# the documents actually use. Verified against this corpus's vocabulary
# -- an entry whose targets are absent is filtered out at runtime by
# _present(), so a stale entry degrades to a no-op rather than dragging
# retrieval towards documents that do not exist.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "sop": ("standard", "operating", "procedure"),
    "sops": ("sop", "standard", "operating", "procedure"),
    "procedure": ("sop", "procedure"),
    "procedures": ("sop", "procedure"),
    "hcu": ("hydrocracker",),
    "hydrocrackers": ("hydrocracker",),
    "ccr": ("regeneration", "catalytic"),
    "psa": ("hydrogen", "purity"),
    "mfi": ("melt", "flow", "index"),
    "pid": ("p&id", "schematic"),
    "p&id": ("schematic", "diagram"),
    "spec": ("specification",),
    "specs": ("specification",),
    "qa": ("quality",),
    "docs": ("document",),
    "maint": ("maintenance",),
    "temp": ("temperature",),
    "pressure": ("pressure",),
    "changeout": ("changeout", "catalyst"),
    "incident": ("incident", "report"),
    "inspection": ("inspection", "report"),
}

# Imperative framing that carries no retrieval signal. Removed from the
# SEARCH query only; the user's actual request is untouched.
_COMMAND_WORDS = frozenset("""
give show tell list get find fetch provide display summarise summarize
explain describe want need please me my us our you your
""".split())

# Naive de-pluralisation, applied only when the singular actually exists
# in the corpus. A real stemmer would also fold "operating"/"operate",
# which is not obviously desirable for identifier-heavy text, so this
# stays deliberately conservative.
_PLURAL = re.compile(r"^(.*?)(?:s|es)$")


def _present(term: str, vocabulary: frozenset[str]) -> bool:
    return term in vocabulary


def build_search_query(user_query: str, rows: list[tuple[int, str]]) -> str:
    """The string to hand the retriever, given what the user typed.

    Returns the original query plus expansion terms. Additive by design:
    the original wording is always preserved, so this can improve a
    query's ranking but cannot remove a match it already had.
    """
    if not user_query or not user_query.strip():
        return user_query

    index = lexical.get_index(rows)
    vocabulary = index.vocabulary
    if not vocabulary:
        return user_query

    original_tokens = lexical.tokenize(user_query)
    seen = set(original_tokens)
    additions: list[str] = []

    def add(term: str) -> None:
        if term and term not in seen and _present(term, vocabulary):
            seen.add(term)
            additions.append(term)

    for token in original_tokens:
        if token in _COMMAND_WORDS:
            continue

        for expansion in _SYNONYMS.get(token, ()):
            add(expansion)

        # Plural -> singular, only when the singular is a real corpus
        # term. "hydrocrackers" -> "hydrocracker" (present); "sops" ->
        # "sop" (present); "gas" -> "ga" (absent, so skipped).
        if token not in vocabulary:
            match = _PLURAL.match(token)
            if match and match.group(1):
                add(match.group(1))

    if not additions:
        return user_query
    return f"{user_query} {' '.join(additions)}"


def explain(user_query: str, rows: list[tuple[int, str]]) -> dict:
    """What the builder did, for the turn trace."""
    built = build_search_query(user_query, rows)
    added = built[len(user_query):].split() if built != user_query else []
    return {"original": user_query, "search_query": built, "added_terms": added}
