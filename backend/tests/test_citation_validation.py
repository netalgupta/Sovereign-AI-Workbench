"""Tests for validate_citations — RAG_SPEC.md §4."""

from backend.retrieval.citation_validation import validate_citations


def test_all_citations_valid():
    text = "The catalyst is deactivating [1] and a change-out is due [2]."
    result = validate_citations(text, num_retrieved_chunks=2)

    assert result.valid_citation_numbers == [1, 2]
    assert result.invalid_citation_numbers == []
    assert result.cleaned_text == text  # nothing stripped


def test_invented_citation_number_is_caught_and_stripped():
    # Only 2 sources were actually retrieved, but the model cited [7] --
    # this is exactly the "LLM inventing a citation number that doesn't
    # exist" failure mode RAG_SPEC.md §4 exists to catch.
    text = "The plant is compliant [1] per the latest inspection [7]."
    result = validate_citations(text, num_retrieved_chunks=2)

    assert result.valid_citation_numbers == [1]
    assert result.invalid_citation_numbers == [7]
    assert "[7]" not in result.cleaned_text
    assert "[1]" in result.cleaned_text


def test_citation_zero_is_invalid_sources_are_1_indexed():
    result = validate_citations("Some claim [0].", num_retrieved_chunks=3)

    assert result.invalid_citation_numbers == [0]
    assert result.valid_citation_numbers == []


def test_no_citations_at_all():
    result = validate_citations("A plain sentence with no markers.", num_retrieved_chunks=3)

    assert result.valid_citation_numbers == []
    assert result.invalid_citation_numbers == []
    assert result.cleaned_text == "A plain sentence with no markers."


def test_zero_retrieved_chunks_makes_every_citation_invalid():
    result = validate_citations("A claim [1] with a citation.", num_retrieved_chunks=0)

    assert result.invalid_citation_numbers == [1]
    assert "[1]" not in result.cleaned_text


def test_duplicate_citation_numbers_are_deduplicated_in_the_report():
    result = validate_citations("[1] and again [1] and once more [1].", num_retrieved_chunks=2)

    assert result.valid_citation_numbers == [1]  # not [1, 1, 1]


def test_unresolved_placeholder_is_stripped_and_counted():
    """Regression test for a REAL case observed running this against the
    MRPL corpus test set (Q1): the model answered correctly and cited
    real sources elsewhere, but ended with a literal, unsubstituted
    "[N]" -- echoing RAG_SPEC.md §4's own prompt text (which describes
    the citation format AS "[N]") instead of writing a real digit.
    """
    text = (
        "The WABT end-of-run trigger temperature for HCU-2 is > 410 °C. [N] \n\n"
        "[N] Source: SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx"
    )

    result = validate_citations(text, num_retrieved_chunks=5)

    assert result.unresolved_placeholder_count == 2
    assert "[N]" not in result.cleaned_text
    # The real content around the stripped placeholder must survive --
    # this is a targeted strip of the bracket token, not a rewrite.
    assert "> 410" in result.cleaned_text
    assert "SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx" in result.cleaned_text


def test_unresolved_placeholder_does_not_false_positive_on_real_numeric_citations():
    result = validate_citations("A claim [1] and another [2].", num_retrieved_chunks=2)

    assert result.unresolved_placeholder_count == 0
    assert "[1]" in result.cleaned_text
    assert "[2]" in result.cleaned_text


def test_lowercase_bracket_letter_is_not_treated_as_a_placeholder():
    # Deliberately narrow pattern (uppercase only) -- must not strip
    # something like "[a]" that could legitimately appear in real text
    # (e.g. a list marker), only the specific unresolved-citation shape.
    result = validate_citations("See item [a] in the appendix.", num_retrieved_chunks=2)

    assert result.unresolved_placeholder_count == 0
    assert "[a]" in result.cleaned_text
