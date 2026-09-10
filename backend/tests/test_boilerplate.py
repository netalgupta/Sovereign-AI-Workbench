"""Tests for cross-document boilerplate detection — RAG_SPEC.md §2.

Built directly from a real, measured finding: every document in
MRPL_RAG_Test_Corpus ends with a near-identical disclaimer sentence, and
fused retrieval scores across 9 unrelated questions clustered in a
suspiciously tight 0.029-0.033 band, with an unrelated document
appearing in 6 of 9 top-5 result sets.
"""

from backend.ingestion.boilerplate import detect_boilerplate_sentences, strip_boilerplate


def test_sentence_recurring_across_most_documents_is_flagged():
    docs = [
        "The hydrocracker catalyst is showing WABT creep. This is a synthetic test document.",
        "Sulphur exceeded the spec limit on 2026-08-19. This is a synthetic test document.",
        "PSA-3 purity dropped below target. This is a synthetic test document.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert "this is a synthetic test document." in report.boilerplate_sentences
    assert report.doc_fraction_by_sentence["this is a synthetic test document."] == 1.0


def test_sentence_appearing_in_only_one_document_is_not_flagged():
    docs = [
        "The hydrocracker catalyst is showing WABT creep.",
        "Sulphur exceeded the spec limit on 2026-08-19.",
        "PSA-3 purity dropped below target.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert report.boilerplate_sentences == []


def test_repeated_sentence_within_one_document_counts_once_not_many_times():
    """A sentence repeated 5 times within ONE document must not look
    like it recurred across 5 documents -- counting must be per-document
    presence, not raw occurrence count."""
    docs = [
        "Repeat this phrase please. Repeat this phrase please. Repeat this phrase please. Unique content A.",
        "Something else entirely. Unrelated content B.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    # "Repeat this phrase please." appears in only 1 of 2 documents (50%),
    # regardless of how many times it repeats WITHIN that one document.
    assert report.doc_fraction_by_sentence.get("repeat this phrase please.", 0) == 0.5


def test_strip_boilerplate_removes_flagged_sentences_keeps_the_rest():
    text = "Real content about WABT trigger values. This is a synthetic test document."

    result = strip_boilerplate(text, {"this is a synthetic test document."})

    assert "synthetic test document" not in result
    assert "Real content about WABT trigger values." in result


def test_strip_boilerplate_preserves_line_structure_of_what_it_keeps():
    """Real bug: the obvious implementation (split into sentences, drop
    the boilerplate, " ".join the rest) also collapses every newline in
    the document into a space — reformatting the whole document as a
    side effect of removing one sentence from the end of it. Measured:
    it changed the corpus's chunk count 21 -> 22, because chunking.py's
    recursive splitter prefers to break on newlines and there were
    suddenly none left. That would have contaminated the before/after
    precision comparison the boilerplate step exists to justify."""
    text = "Section 4.1 Purge procedure.\nSection 4.2 Entry permit.\nThis is a standard disclaimer sentence."

    result = strip_boilerplate(text, {"this is a standard disclaimer sentence."})

    assert result == "Section 4.1 Purge procedure.\nSection 4.2 Entry permit."


def test_strip_boilerplate_with_empty_set_is_a_noop():
    text = "Some text here."
    assert strip_boilerplate(text, set()) == text


def test_detect_on_empty_corpus_returns_nothing():
    report = detect_boilerplate_sentences([], min_doc_fraction=0.5)
    assert report.boilerplate_sentences == []


def test_sentence_is_recognized_even_when_it_follows_a_non_terminal_character_and_newline():
    """Real bug found running this against MRPL_RAG_Test_Corpus: a
    disclaimer sentence following a ')' + newline (end of a list item,
    not a '.', '!', or '?') never got split off from the preceding
    content -- it silently glued onto whatever came before it, which
    differs per document, so the same disclaimer measured as recurring
    in only 3/13 documents instead of the true 6/13. Reproduced here
    with two documents whose disclaimer follows a different
    non-terminal character each time -- correct detection requires
    normalizing away that difference, not string-matching around it."""
    docs = [
        "Some list item (see appendix)\nThis is a synthetic test document.",
        "A different list item (see Table 2)\nThis is a synthetic test document.",
        "Prose ending normally. This is a synthetic test document.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert "this is a synthetic test document." in report.boilerplate_sentences
    assert report.doc_fraction_by_sentence["this is a synthetic test document."] == 1.0


def test_mid_sentence_line_wrap_does_not_split_a_sentence_in_half():
    """pdfplumber inserts a literal newline at a rendered line WRAP,
    which lands mid-sentence, not just at paragraph boundaries. Real bug:
    treating every newline as a boundary split "...an actual MRPL\\ninternal
    document." into "it does not represent an actual mrpl" +
    "internal document.", so half the real disclaimer went undetected
    (the two-word half silently dropped by the length guard, the other
    half never matching across documents)."""
    docs = [
        "Content A.\nThis is a disclaimer sentence. It does not represent an actual\ninternal document.",
        "Content B.\nThis is a disclaimer sentence. It does not represent an actual\ninternal document.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert "it does not represent an actual internal document." in report.boilerplate_sentences
    assert "internal document." not in report.boilerplate_sentences


def test_short_numbering_fragments_are_never_flagged_as_boilerplate():
    """Real bug found running this against MRPL_RAG_Test_Corpus: a
    numbered revision-history table produces degenerate "sentences" like
    "1.", "2.", "3." (a digit + period, an artifact of splitting on
    newlines, not a real sentence) that recur across many documents'
    tables often enough to cross a lowered min_doc_fraction threshold.
    These must never be flagged regardless of how high their fraction
    is -- same shape of bug as the single-letter entity fuzzy-merge fix
    in entity_extraction.py (MIN_FUZZY_MATCH_LENGTH)."""
    docs = [
        "This is the standard revision history table.\n1.\nAdded section on WABT.\n2.\nUpdated form reference.",
        "This is the standard revision history table.\n1.\nInitial release.\n2.\nMinor edits.",
        "This is the standard revision history table.\n1.\nFirst version.\n2.\nSecond version.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert "1." not in report.boilerplate_sentences
    assert "2." not in report.boilerplate_sentences
    assert "this is the standard revision history table." in report.boilerplate_sentences


def test_matching_is_case_and_whitespace_insensitive():
    docs = [
        "Content one.   THIS IS A DISCLAIMER.  ",
        "Content two. this is a disclaimer.",
    ]

    report = detect_boilerplate_sentences(docs, min_doc_fraction=0.5)

    assert "this is a disclaimer." in report.boilerplate_sentences
