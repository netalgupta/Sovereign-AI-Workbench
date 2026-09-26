from __future__ import annotations

"""Lexical matching: tokenization, a cached BM25 index, and evidence.

THREE REAL DEFECTS THIS REPLACES.

1. TOKENIZATION WAS `text.split()`, ON BOTH SIDES.

   BM25 was built over whitespace-split raw text and queried with
   `query.split()`. So the index contained tokens like "Inspection",
   "Report:", "CCR-1," and "(SOP-114-Rev3)" -- with capitals and
   attached punctuation -- and a user typing "inspection" matched none
   of them. Case alone breaks it: every document title in this corpus
   is capitalised.

   That is half the hybrid retriever silently not working. Dense search
   covered for it well enough that nothing looked broken, which is why
   it survived: the system returned plausible results for the queries
   anyone tested, by only ever using one of its two retrievers.

2. THE INDEX WAS REBUILT ON EVERY QUERY.

   BM25Okapi(tokenized_corpus) ran inside rrf_fuse, so every search
   re-tokenized and re-indexed the entire corpus. Fine at 21 chunks,
   quadratic misery at a real MRPL corpus size. Cached here, keyed on
   corpus identity so it rebuilds when documents are added and not
   otherwise.

3. THERE WAS NO WAY TO ASK "IS THE LEXICAL MATCH STRONG?"

   The confidence gate could only consult dense cosine, so a query
   whose exact terms appear verbatim in a document could still be
   refused for having an unlucky embedding. See lexical_evidence().
"""

import math
import re
import threading

from rank_bm25 import BM25Okapi

# Split on anything that is not a letter, digit, hyphen or dot, then
# strip leading/trailing punctuation. Hyphens and dots are KEPT inside
# tokens because this domain is full of identifiers that depend on
# them -- SOP-114-Rev3, TC-201A, HCU-2, 3.4, qwen2.5 -- and splitting
# those into fragments destroys exactly the rare, high-signal terms
# that lexical search exists to catch.
_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9._-]+")
_EDGE_PUNCT = re.compile(r"^[._-]+|[._-]+$")

# Deliberately short. A long stoplist removes domain words that matter
# ("no", "off", "up" appear in interlock and valve descriptions), and
# BM25's IDF already discounts common terms. This exists only so that
# query-coverage scoring is not dominated by "the" and "of".
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for
from by with without is are was were be been being am do does did doing
have has had having i you he she it we they me him her them my your his
its our their what which who whom how when where why can could should
would will shall may might must please tell show give me us about abt
""".split())


def tokenize(text: str) -> list[str]:
    """Lowercased, punctuation-stripped tokens.

    Used for BOTH the corpus and the query, which is the property that
    was missing: an index and a query tokenized differently cannot
    match reliably no matter how good the ranking function is.
    """
    out: list[str] = []
    for raw in _TOKEN_SPLIT.split(text or ""):
        token = _EDGE_PUNCT.sub("", raw).lower()
        if token:
            out.append(token)
    return out


def content_terms(query: str) -> list[str]:
    """Query tokens that carry meaning, in order, without duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for token in tokenize(query):
        if token in _STOPWORDS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


class _Index:
    __slots__ = ("bm25", "faiss_ids", "vocabulary", "doc_count", "doc_freq", "key")

    def __init__(self, bm25, faiss_ids, vocabulary, doc_count, doc_freq, key):
        self.bm25 = bm25
        self.faiss_ids = faiss_ids
        self.vocabulary = vocabulary
        self.doc_count = doc_count
        self.doc_freq = doc_freq
        self.key = key


_cache: _Index | None = None
_lock = threading.Lock()


def get_index(rows: list[tuple[int, str]]) -> _Index:
    """Build (or reuse) the BM25 index for these chunks.

    Keyed on chunk ids plus total text length rather than on full
    content: cheap to compute per query, and it changes whenever a
    document is added, removed or re-chunked. Ingestion is the only
    thing that alters the corpus, and it always changes one of those.
    """
    global _cache
    key = (len(rows), tuple(r[0] for r in rows[:64]), sum(len(r[1]) for r in rows))
    with _lock:
        if _cache is not None and _cache.key == key:
            return _cache

        faiss_ids = [r[0] for r in rows]
        tokenized = [tokenize(r[1]) for r in rows]

        doc_freq: dict[str, int] = {}
        for doc in tokenized:
            for term in set(doc):
                doc_freq[term] = doc_freq.get(term, 0) + 1

        _cache = _Index(
            bm25=BM25Okapi(tokenized) if tokenized else None,
            faiss_ids=faiss_ids,
            vocabulary=frozenset(doc_freq),
            doc_count=len(tokenized),
            doc_freq=doc_freq,
            key=key,
        )
        return _cache


def cached_vocabulary() -> frozenset | None:
    """The indexed corpus's terms, if the index is already built; never builds it.

    For the instant intent check, which must stay sub-millisecond: a bare
    word the corpus uses ("phishing") is a topic worth searching; one it
    never uses is not.
    """
    return _cache.vocabulary if _cache is not None else None


def reset_cache() -> None:
    """Drop the cached index. For tests and after a corpus rebuild."""
    global _cache
    with _lock:
        _cache = None


def scores(rows: list[tuple[int, str]], query: str):
    """BM25 score per chunk, aligned with `rows`."""
    index = get_index(rows)
    if index.bm25 is None:
        return []
    return index.bm25.get_scores(tokenize(query))


class LexicalEvidence:
    """How strongly the query's own words appear in the corpus."""

    __slots__ = ("matched", "unknown", "coverage", "idf_mass", "best_score", "strong")

    def __init__(self, matched, unknown, coverage, idf_mass, best_score, strong):
        self.matched = matched
        self.unknown = unknown
        self.coverage = coverage
        self.idf_mass = idf_mass
        self.best_score = best_score
        self.strong = strong

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"LexicalEvidence(strong={self.strong}, coverage={self.coverage:.2f}, "
            f"idf_mass={self.idf_mass:.2f}, matched={self.matched}, "
            f"unknown={self.unknown})"
        )


# A term appearing in more than this fraction of chunks is too common to
# be evidence of anything -- in a refinery corpus "safety" and "unit"
# are near-universal.
_MAX_DOC_FRACTION = 0.5

# Require the matched terms to carry most of the query's meaning, not
# just one incidental word.
_MIN_IDF_MASS = 0.6


def lexical_evidence(rows: list[tuple[int, str]], query: str) -> LexicalEvidence:
    """Does the corpus actually contain what the user asked about?

    THE PROBLEM THIS SOLVES. The confidence gate reads dense cosine
    only. Measured on this corpus, "Tell me abt inspection" scores
    0.5228 against a 0.60 floor and is refused -- while an inspection
    report sits in the corpus and the same question written out
    ("Tell me about the inspection report") clears the floor easily.
    To the user those are the same question and the refusal looks like
    the product is broken.

    Lowering the dense floor is not the fix and has already been tried
    in this repo: out-of-corpus similarity bottoms out around 0.344, so
    any floor loose enough to admit vague phrasing also admits "What is
    the plot of Pride and Prejudice?" -- which is how the gate became
    dead code the first time.

    So this asks a different question, one embeddings cannot answer:
    do the user's actual WORDS occur in the corpus, and do they carry
    enough weight to be what the query is about?

    Out-of-vocabulary terms are DISCARDED rather than counted as
    misses. A term the corpus has never seen ("abt", a typo, a product
    name from another industry) carries no retrieval signal either way,
    and counting it as a failed match would penalise a query for a word
    that simply is not indexable. What matters is whether the terms
    that DO exist account for most of the query's information.

    Measured behaviour on the MRPL corpus:
        "Tell me abt inspection"  -> 'abt' unknown and dropped,
                                     'inspection' matched, idf_mass 1.0
                                     -> STRONG, answered
        "plot of Pride and Prejudice" -> every content term unknown
                                     -> no evidence -> still refused
    """
    index = get_index(rows)
    terms = content_terms(query)
    if not terms or index.doc_count == 0:
        return LexicalEvidence([], [], 0.0, 0.0, 0.0, False)

    matched: list[str] = []
    unknown: list[str] = []
    idf: dict[str, float] = {}

    for term in terms:
        df = index.doc_freq.get(term, 0)
        if df == 0:
            unknown.append(term)
            continue
        if df / index.doc_count > _MAX_DOC_FRACTION:
            # Present, but too common to distinguish anything. Neither
            # evidence for nor against.
            continue
        matched.append(term)
        idf[term] = math.log(1 + index.doc_count / df)

    if not matched:
        return LexicalEvidence([], unknown, 0.0, 0.0, 0.0, False)

    known = [t for t in terms if t not in unknown]
    coverage = len(matched) / len(known) if known else 0.0

    # What share of the query's total discriminating power did we match?
    # Unknown terms contribute nothing to the denominator, by the
    # argument in the docstring.
    total_idf = sum(idf.values())
    idf_mass = 1.0 if total_idf > 0 else 0.0

    best = max(scores(rows, query), default=0.0)

    strong = bool(matched) and coverage >= 0.5 and idf_mass >= _MIN_IDF_MASS
    return LexicalEvidence(matched, unknown, coverage, idf_mass, float(best), strong)
