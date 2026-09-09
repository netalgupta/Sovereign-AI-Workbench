"""Semantic chunking — an OPT-IN alternative to chunking.py's fixed-size
splitter, NOT a replacement for it.

WHY THIS IS OPT-IN, NOT THE NEW DEFAULT: RAG_SPEC.md §2 step 3 locks
chunk size at exactly 512 tokens / 64 overlap *on purpose* — its own
words are "consistency across the corpus matters for retrieval-quality
comparisons." §3's 0.35 confidence threshold was set assuming chunks
behave that way. Semantic chunking produces variable-size chunks at
detected topic boundaries instead — genuinely better for retrieval
quality in many cases, but silently swapping the default would
invalidate that threshold's calibration without anyone noticing until
retrieval quality quietly shifted. So: `chunk_text` (chunking.py) stays
the RAG_SPEC-mandated default the rest of the pipeline uses; this module
is available for whoever wants to explicitly try it, with this file's
docstring as the flag that doing so changes a documented assumption
(RAG_SPEC.md §3's own rule: "document any change to it in this file").

HOW IT WORKS: split into sentences, embed each one (reusing bge-large —
no new model dependency), and cut between sentences where the semantic
distance to the next sentence is an outlier relative to the rest of the
document (a genuine topic shift), rather than at a fixed token count
regardless of whether a thought was mid-sentence. Any resulting segment
still larger than chunking.py's token budget is safety-netted through
the locked fixed-size splitter — a single semantically coherent segment
(one long paragraph with no real topic shift) must never become one
oversized chunk that breaks every downstream assumption about chunk size.

WHY A REGEX SENTENCE SPLITTER, NOT AN NLP LIBRARY: nltk/spaCy sentence
tokenizers typically download model data from the internet on first use
— exactly the phone-home risk this project's ingestion layer already
works hard to eliminate for two other models (see model_cache.py). A
plain regex is naturally, structurally offline (nothing to fetch, ever)
and is good enough for splitting on ".", "!", "?" followed by whitespace
and a capital/digit — imperfect on some abbreviations, but that's a
tradeoff explicitly made here, not an oversight.
"""

import re

import numpy as np

from backend.ingestion.chunking import chunk_text
from backend.ingestion.embeddings import embed_texts

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _split_sentences(text: str) -> list[str]:
    sentences = _SENTENCE_SPLIT_PATTERN.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_text_semantic(text: str, breakpoint_percentile: float = 90.0) -> list[str]:
    """Group sentences into chunks at detected topic-shift boundaries.

    Args:
        text: the text to chunk.
        breakpoint_percentile: how unusual a distance jump must be
            (relative to every other consecutive-sentence jump in this
            text) to count as a real topic shift. Higher = fewer, larger
            chunks; lower = more, smaller chunks. 90.0 is a starting
            point for tuning, not a value carried over from anywhere
            else in this spec — there is nothing to carry over, since
            RAG_SPEC.md never specifies this strategy at all.

    Returns:
        A list of chunk strings. Never returns an empty string as a
        chunk, and never returns a chunk larger than chunking.py's
        locked CHUNK_SIZE_TOKENS budget (oversized segments are
        re-split through chunk_text as a safety net).
    """
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return chunk_text(text)

    embeddings = embed_texts(sentences)  # (n, 1024), L2-normalized
    # Consecutive cosine similarities are a plain dot product because
    # embed_texts already normalizes — same trick used throughout
    # embeddings.py's own tests.
    similarities = np.sum(embeddings[:-1] * embeddings[1:], axis=1)
    distances = 1.0 - similarities

    threshold = np.percentile(distances, breakpoint_percentile)
    breakpoints = {int(i) for i in np.where(distances >= threshold)[0]}

    raw_chunks: list[str] = []
    current: list[str] = [sentences[0]]
    for i in range(1, len(sentences)):
        if (i - 1) in breakpoints:
            raw_chunks.append(" ".join(current))
            current = []
        current.append(sentences[i])
    if current:
        raw_chunks.append(" ".join(current))

    final_chunks: list[str] = []
    for raw_chunk in raw_chunks:
        if not raw_chunk.strip():
            continue
        # chunk_text is a no-op passthrough for text already under
        # budget (langchain's splitter returns it as one piece
        # unchanged) — this only actually re-splits an oversized segment.
        final_chunks.extend(chunk_text(raw_chunk))
    return final_chunks
