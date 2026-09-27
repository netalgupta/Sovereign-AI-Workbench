"""Questions about the corpus itself, answered from the index.

THE GAP THIS FILLS. "Summarise the data that you have", "what documents
do you have", "what can you help me with" are among the first things
anyone types into a tool like this. They went through chunk retrieval,
which cannot answer them: no chunk is semantically similar to "summarise
what you have", because the answer is not written down in any document
-- it is a property of the collection.

The observed outcomes were both wrong in different ways. Before the
hybrid gate, "Summarise the data that u have" was REFUSED at cosine
0.5228, which reads as the product not knowing what it holds. After it,
the query scrapes in on the single generic term "data" and produces a
summary of five arbitrary chunks, which is worse -- it looks like an
answer and is not one.

So these are answered deterministically from the document registry:
real filenames, real counts, real types, real sizes. Nothing is
generated, so nothing can be fabricated, and every figure is checkable
against the Sources panel.

WHAT THIS IS NOT. It is not a shortcut around grounding. It answers
only questions ABOUT the collection, never questions about the CONTENT
of documents in it. "What does the inspection report say" is a content
question and goes to retrieval, where it is subject to the confidence
gate like everything else. The patterns below are deliberately narrow
for that reason: a false positive here would bypass grounding entirely.
"""

from __future__ import annotations

import re
from collections import Counter

# Narrow by design. Each requires BOTH a "what do you have" shape AND a
# collection-level object ("documents", "sources", "corpus", "data").
# "Summarise the inspection report" must NOT match -- it names a
# specific document and belongs to retrieval.
_PATTERNS = [
    r"\b(what|which)\b.{0,30}\b(documents?|sources?|files?|data|corpus|knowledge\s*base)\b"
    r".{0,30}\b(do you have|have you got|are (there|loaded|indexed|available)|is loaded|"
    r"can you (see|access|read))\b",
    r"\b(summari[sz]e|list|show|describe|tell me about)\b.{0,25}"
    r"\b(the\s+|your\s+|all\s+|every\s+|available\s+)?"
    r"(documents?|sources?|files?|data|corpus|knowledge\s*base)\b"
    r"(?!\s+(in|from|about|for|on)\s+\S)",
    r"\bwhat (can|do) you (help|do|know|answer)\b",
    r"\bhow many (documents?|sources?|files?|chunks?)\b",
    r"\bwhat('s| is) (in|inside) (the |your )?(corpus|knowledge\s*base|sources?)\b",
]
_COMPILED = [re.compile(p, re.I) for p in _PATTERNS]

# Phrases that look collection-level but name a specific subject. These
# veto a match, because answering them from the index would skip
# grounding on a question that has a real, citable answer.
_SPECIFIC_SUBJECT = re.compile(
    r"\b(inspection|incident|batch|catalyst|sulphur|hydrogen|psa|mfi|sop|"
    r"maintenance|pipeline|reactor|column|depot|correspondence|qa|report)\b",
    re.I,
)


# The header the chat writes above the text of a file attached to one
# message (ChatPane.handleSend). Such a message is about THAT file.
_ATTACHED_FILE = re.compile(r"^ATTACHED FILE: ", re.M)


def carries_attached_file(text: str) -> bool:
    """Does this message carry the text of a file attached to it?

    Measured 27 Sep: "List all houses from the document" with a spreadsheet
    attached was answered with the corpus inventory ("69 documents are
    indexed") -- "list ... document" matched the pattern below, and the
    attached text itself says "attached file(s)". A message with a file
    is about that file, never about the collection, never a greeting.
    """
    return bool(text) and bool(_ATTACHED_FILE.search(text))


def is_corpus_question(query: str) -> bool:
    """Is this a question about the collection rather than its contents?"""
    if not query or not query.strip():
        return False
    if carries_attached_file(query):
        return False
    text = query.strip()
    if _SPECIFIC_SUBJECT.search(text):
        # Names a domain subject -> there may be a real, citable answer.
        # Retrieval must get the chance to find it.
        return False
    return any(p.search(text) for p in _COMPILED)


def _human_size(num_bytes: int) -> str:
    if num_bytes >= 1_000_000_000:
        return f"{num_bytes / 1e9:.2f} GB"
    if num_bytes >= 1_000_000:
        return f"{num_bytes / 1e6:.1f} MB"
    return f"{num_bytes / 1024:.0f} KB"


def answer_corpus_question(query: str) -> str:
    """A factual inventory of what is loaded, as markdown.

    Reads the same corpus endpoint the Sources panel renders, so the
    chat and the sidebar cannot disagree about what is indexed -- two
    independent views of the corpus that can drift is how a user ends up
    trusting the wrong one.
    """
    from backend.api.routes import _get_corpus_data

    try:
        data = _get_corpus_data()
    except Exception as exc:  # noqa: BLE001
        return (
            "I could not read the source index to answer that.\n\n"
            f"`{type(exc).__name__}: {exc}`"
        )

    sources = data.get("sources") or []
    if not sources:
        return (
            "**No documents are currently indexed.**\n\n"
            "Add a file or folder under Sources, and I will be able to answer "
            "questions grounded in it."
        )

    by_corpus = Counter(s.get("corpus") or "(ungrouped)" for s in sources)
    by_type = Counter((s.get("type") or "?").upper() for s in sources)
    by_category = Counter(s.get("category") or "other" for s in sources)
    total_bytes = sum(int(s.get("sizeBytes") or 0) for s in sources)

    lines = [
        f"**{len(sources)} documents are indexed**, {_human_size(total_bytes)} in total.",
        "",
        "| Collection | Documents |",
        "|---|---:|",
    ]
    lines += [f"| `{name}` | {count} |" for name, count in by_corpus.most_common()]

    lines += [
        "",
        "**By kind** — "
        + ", ".join(f"{count} {cat}" for cat, count in by_category.most_common()),
        "",
        "**By format** — "
        + ", ".join(f"{count} {ext}" for ext, count in by_type.most_common()),
        "",
        "### Documents",
        "",
    ]

    # Grouped by collection, so the list mirrors the Sources tree rather
    # than presenting a flat wall of filenames.
    for collection, _ in by_corpus.most_common():
        members = [s for s in sources if (s.get("corpus") or "(ungrouped)") == collection]
        lines.append(f"**{collection}**")
        lines.append("")
        for s in sorted(members, key=lambda x: (x.get("name") or "").lower())[:40]:
            size = s.get("size") or _human_size(int(s.get("sizeBytes") or 0))
            lines.append(f"- `{s.get('name')}` — {size}")
        if len(members) > 40:
            lines.append(f"- …and {len(members) - 40} more")
        lines.append("")

    lines += [
        "---",
        "",
        "This inventory is read directly from the source index, not generated, "
        "so every name and figure above is exact.",
        "",
        "Ask about the **contents** of any of these and the answer will be "
        "grounded in the document with a citation.",
    ]
    return "\n".join(lines)
