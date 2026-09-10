"""Cross-document boilerplate detection — RAG_SPEC.md §2.

Real, evidence-backed problem this solves: every document in the MRPL
test corpus ends with a near-identical disclaimer sentence. Left in,
that sentence becomes shared vocabulary BM25 sees in every chunk
(artificially inflating cross-document lexical similarity) and shared
semantic content dense embeddings pick up too (pulling every chunk's
vector measurably toward a shared "meta-document-about-testing" region
of embedding space) — regardless of the chunk's actual topic. Measured
directly: fused retrieval scores across 9 unrelated questions clustered
in a suspiciously tight 0.029-0.033 band, and an unrelated document
(depot correspondence) appeared in 6 of 9 top-5 result sets.

WHY THIS HAS TO BE CORPUS-LEVEL, NOT PER-DOCUMENT: "is this sentence
boilerplate" is fundamentally a cross-document question — a sentence
recurring near-verbatim across MANY documents is boilerplate (letterhead,
footer, standard disclaimer); the exact same sentence appearing once is
just... a sentence. Detection requires seeing every document's text
before deciding anything, which is why this needs a two-pass ingestion
flow (extract everything, detect, then chunk) rather than fitting inside
ingest_document()'s per-file signature. See ingest_corpus.py's
`ingest_corpus_with_boilerplate_removal` for that orchestration.

WHY THIS IS GENERAL, NOT SPECIFIC TO THIS TEST CORPUS'S DISCLAIMER TEXT:
real MRPL documents will have their own letterhead, footers, and
standard disclaimers with completely different wording. Detection here
is purely statistical (recurrence rate across documents), with zero
hardcoded phrases.
"""

import re

from pydantic import BaseModel

# Splits on a sentence-terminator + whitespace + capital/digit (normal
# prose), OR on a newline that is ITSELF followed by a capital/digit.
# The newline branch matters more than it looks: text_extraction.py
# joins paragraphs/table rows with "\n", so a newline is often already a
# real structural boundary regardless of what character precedes it --
# real bug found running this against the actual corpus: without any
# newline handling, a sentence like "This is a synthetic, illustrative
# document..." that happens to follow a ")" (end of a list item) rather
# than a "." + newline never gets split off, silently gluing onto
# whatever content precedes it (which differs per document), so the
# same disclaimer measured as recurring in only 3/13 documents instead
# of the true 6/13.
#
# BUT a bare, unconditional "\n+" is too aggressive: pdfplumber's PDF
# text extraction also inserts a literal "\n" at a rendered line WRAP,
# which can land mid-sentence, not just at paragraph boundaries -- e.g.
# "...an actual MRPL\ninternal document." is one sentence wrapped across
# a line, not two sentences. Splitting there produced "internal
# document." as its own two-word fragment (silently dropped by the
# MIN_BOILERPLATE_SENTENCE_WORDS guard below) and lost the other half
# ("it does not represent an actual mrpl") as an incomplete, never-
# recurring fragment -- so half of the real disclaimer went undetected.
# Requiring the newline to be followed by a capital/digit (the same
# lookahead the "." branch already uses) fixes both: a genuine new
# paragraph/list item starts with a capital letter, while a mid-sentence
# line-wrap continuation (like "internal document.") does not.
# Branch 1 (terminator) deliberately does NOT require a capital letter
# after the terminator, only some non-whitespace: this pipeline ingests
# OCR'd scans, where capitalization is unreliable, so requiring a
# capital would systematically under-split exactly the documents whose
# text is already the least trustworthy. Branch 2 (newline) DOES require
# a capital/digit — there it is load-bearing, distinguishing a genuine
# paragraph start from a mid-sentence PDF line-wrap continuation.
_SENTENCE_SPLIT_RULE = r"(?<=[.!?])\s+(?=\S)|\n+(?=[A-Z0-9])"
_SENTENCE_SPLIT_PATTERN = re.compile(_SENTENCE_SPLIT_RULE)
# Same rule, one capturing group around it, so re.split hands back the
# separators as well as the sentences — strip_boilerplate needs them to
# put the document back together without reformatting it. Derived from
# the same string deliberately: two hand-maintained copies of this
# regex would eventually disagree, and the failure would be silent.
_SENTENCE_SPLIT_CAPTURING_PATTERN = re.compile(f"({_SENTENCE_SPLIT_RULE})")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_PATTERN.split(text.strip()) if s.strip()]


def _normalize(sentence: str) -> str:
    return " ".join(sentence.lower().split())


# A "sentence" shorter than this many words is treated as a segmentation
# artifact (table cell, list-number marker, header fragment), never a
# real boilerplate candidate — see the comment at its use site in
# detect_boilerplate_sentences for the real bug this guards against.
MIN_BOILERPLATE_SENTENCE_WORDS = 4

# Boilerplate means "recurring ACROSS documents", so appearing in a
# single document disqualifies a sentence by definition, whatever
# fraction that single document represents. This guard is what makes the
# detector safe on a small corpus: with 2 documents, a sentence in just
# ONE of them scores 1/2 = 0.5 and clears any threshold at or below
# that, so without this rule a 2-document ingest would flag (and strip)
# essentially every sentence in both documents. Caught by
# test_ingest_corpus.py's single-document-sentence test, not by
# inspection — the fraction math hides it completely at corpus sizes
# where the real corpus (13 documents) behaves fine.
MIN_BOILERPLATE_DOCUMENT_COUNT = 2


class BoilerplateReport(BaseModel):
    boilerplate_sentences: list[str]  # normalized form, for matching
    doc_fraction_by_sentence: dict[str, float]  # normalized sentence -> fraction of docs it appeared in


def detect_boilerplate_sentences(
    document_texts: list[str], min_doc_fraction: float = 0.5
) -> BoilerplateReport:
    """Flag sentences recurring near-verbatim across a large fraction of
    the corpus's documents.

    Args:
        document_texts: one string per DOCUMENT (not per chunk/page) —
            counting must be per-document, not per-page/per-occurrence,
            or a sentence repeated many times within one long document
            would inflate its score without actually recurring across
            the corpus at all.
        min_doc_fraction: a sentence appearing in at least this fraction
            of documents is flagged as boilerplate. 0.5 is a starting
            point (matching RAG_SPEC.md's own "document any tuned
            threshold" precedent for the 0.35 confidence threshold),
            not a permanently fixed constant. IMPORTANT, learned from a
            real run: this fraction is measured over ALL documents
            passed in, but not every document TYPE is capable of
            carrying a textual footer/disclaimer at all (a chart-only
            XLSX or a diagram PNG has no prose paragraph to carry one).
            The true ceiling for any sentence's fraction is therefore
            (# prose-capable documents / # total documents), which can
            sit well under 0.5 in a corpus with a large non-prose
            fraction — in that case the caller must pass an explicit,
            lower, documented threshold rather than relying on this
            default. This is not a flaw in the counting logic; it's
            corpus composition the caller has to account for.

    Returns a BoilerplateReport — the sentence list AND the measured
    fraction for each, so a caller can see exactly why something was
    flagged rather than trusting a boolean.
    """
    doc_count = len(document_texts)
    if doc_count == 0:
        return BoilerplateReport(boilerplate_sentences=[], doc_fraction_by_sentence={})

    sentence_doc_counts: dict[str, int] = {}
    for text in document_texts:
        # set(): count each sentence AT MOST ONCE per document, even if
        # it appears multiple times within that one document — this is
        # what makes the fraction a genuine cross-document recurrence
        # rate rather than a raw occurrence count. Fragments shorter than
        # MIN_BOILERPLATE_SENTENCE_WORDS are dropped before counting at
        # all -- real bug found running this against the real corpus: a
        # numbered revision-history table produces degenerate "sentences"
        # like "1.", "2.", "3." (just a digit + period, an artifact of
        # the newline-based split rule above, not a real sentence), and
        # those recur across many documents' tables often enough to
        # cross a lowered min_doc_fraction threshold and get flagged as
        # boilerplate -- exactly the same shape of bug as the
        # single-letter entity fuzzy-merge fix in entity_extraction.py
        # (MIN_FUZZY_MATCH_LENGTH): a short fragment satisfies a matching
        # rule for a reason that has nothing to do with its content.
        seen_in_this_doc = {
            _normalize(s) for s in _split_sentences(text)
            if len(_normalize(s).split()) >= MIN_BOILERPLATE_SENTENCE_WORDS
        }
        for normalized in seen_in_this_doc:
            sentence_doc_counts[normalized] = sentence_doc_counts.get(normalized, 0) + 1

    fractions = {s: count / doc_count for s, count in sentence_doc_counts.items()}
    flagged = sorted(
        s
        for s, frac in fractions.items()
        if frac >= min_doc_fraction
        and sentence_doc_counts[s] >= MIN_BOILERPLATE_DOCUMENT_COUNT
    )

    return BoilerplateReport(
        boilerplate_sentences=flagged,
        doc_fraction_by_sentence={s: fractions[s] for s in flagged},
    )


def strip_boilerplate(text: str, boilerplate_sentences: set[str] | list[str]) -> str:
    """Remove every sentence in `text` whose normalized form is in
    `boilerplate_sentences`, preserving the rest EXACTLY as it was —
    including the original whitespace and line structure between the
    sentences that are kept.

    That preservation is the whole subtlety here. The obvious
    implementation (split into sentences, drop the boilerplate ones,
    `" ".join()` the rest) also silently collapses every newline in the
    document into a space — reformatting the entire document as a side
    effect of removing two sentences from the end of it. Measured
    directly: it changed the corpus's chunk count from 21 to 22, because
    chunking.py's recursive splitter prefers to break on newlines and
    there were suddenly none left to break on. That would have
    contaminated the before/after precision comparison this step exists
    to justify — the delta would have partly measured "document was
    reflowed", not "boilerplate was removed". So: split with the
    separators CAPTURED, and rebuild the text with them intact, dropping
    only a removed sentence and its own trailing separator.
    """
    boilerplate_set = set(boilerplate_sentences)
    if not boilerplate_set:
        return text

    # Capturing group => re.split interleaves [sentence, sep, sentence,
    # sep, ..., sentence], so the original separators survive the trip.
    parts = _SENTENCE_SPLIT_CAPTURING_PATTERN.split(text)
    rebuilt: list[str] = []
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        separator = parts[i + 1] if i + 1 < len(parts) else ""
        if _normalize(sentence) in boilerplate_set:
            continue
        rebuilt.append(sentence)
        rebuilt.append(separator)
    return "".join(rebuilt).strip()
