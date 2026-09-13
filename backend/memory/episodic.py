"""Answers this process has already produced, for questions asked again.

THE GAP. Asking the same question twice costs the same 17-25 seconds
twice. On a demo floor that is exactly what happens -- somebody asks,
somebody else asks the same thing, and the second person watches the
spinner. In a working session it happens whenever a user scrolls back,
rephrases identically, or reloads the page.

WHY THIS IS NOT SIMPLY A CACHE, AND WHY IT IS SAFE.

Generation runs at temperature 0. The same question, against the same
corpus, with the same context, produces the same answer -- so returning
the stored one is not an approximation of the work, it IS the work,
already done. What makes a cache dangerous is not reuse; it is reuse
after the inputs changed. This repository has been bitten by that five
times: a committed JSON artifact outliving the code that made it, a
resume path serving a cached score instead of the model's output, hash
embeddings that satisfied every shape assertion. Every one of them was
a cached view of something that had moved.

So the key is every input that can change the answer:

    the query, normalised          different wording, different answer
    the corpus generation          re-ingest invalidates everything
    the active document filter     the user switching sources off is a
                                   different question, not the same one
    the conversation context       a follow-up resolved against
                                   different history is different work
    top_k and the model id         different retrieval, different model

Miss any of those and the cache serves a confident answer to a question
nobody asked -- which is worse than being slow.

IN-PROCESS AND BOUNDED, DELIBERATELY.

Not persisted to disk. The corpus generation counter lives in the
VectorStore and resets when the process restarts, so a cache that
survived the process would be keyed on a number that no longer means
what it meant when the entry was written -- the exact stale-artifact
shape above. A restart clearing this is correct, not a limitation.

WHAT IS NEVER CACHED. Refusals. "Not found in the corpus" is the answer
most likely to change for reasons the key cannot see -- the user adds
the missing document, fixes a source toggle, or rephrases -- and a
cached refusal would keep saying no after the gap was fixed. A refusal
is cheap anyway: it never reaches the model.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

# Small on purpose. This exists to make a repeated question instant, not
# to accumulate a session's worth of answers in RAM alongside the models.
MAX_ENTRIES = 64

_lock = threading.Lock()
_entries: OrderedDict[str, object] = OrderedDict()
_hits = 0
_misses = 0


def key_for(
    query: str,
    *,
    corpus_generation: int,
    top_k: int,
    model_id: str,
    active_documents: list[str] | None,
    conversation_context: str = "",
) -> str:
    """A key covering every input that can change the answer."""
    # None (no filter) and [] (everything switched off) are different
    # instructions and must not collide.
    if active_documents is None:
        documents = "*"
    else:
        documents = "|".join(sorted(active_documents))

    material = "\x1f".join([
        " ".join((query or "").lower().split()),
        str(corpus_generation),
        str(top_k),
        model_id,
        documents,
        hashlib.sha256((conversation_context or "").encode("utf-8")).hexdigest(),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def recall(key: str):
    """The stored answer for `key`, or None."""
    global _hits, _misses
    with _lock:
        if key in _entries:
            _entries.move_to_end(key)
            _hits += 1
            return _entries[key]
        _misses += 1
    return None


def remember(key: str, answer) -> None:
    """Store an answer. Refusals are declined, not stored."""
    if getattr(answer, "found", True) is False:
        return
    with _lock:
        _entries[key] = answer
        _entries.move_to_end(key)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)


def stats() -> dict:
    with _lock:
        return {"entries": len(_entries), "hits": _hits, "misses": _misses}


def clear() -> None:
    global _hits, _misses
    with _lock:
        _entries.clear()
        _hits = 0
        _misses = 0
