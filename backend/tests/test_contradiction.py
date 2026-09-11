"""Tests for contradiction detection — TOOLS.md row 15.

Most of these are FALSE-POSITIVE tests, deliberately. Finding two
different numbers for the same phrase is easy; doing it without crying
wolf is the whole job, because a detector that flags legitimate
variation gets switched off within a day and then catches nothing.
"""

from backend.retrieval.contradiction import (
    Claim,
    extract_claims_by_pattern,
    find_contradictions,
    values_are_equivalent,
)


class _Chunk:
    """Minimal chunk shape — text plus its source document."""

    def __init__(self, text, source_document):
        self.text = text
        self.source_document = source_document


# ---- the real thing it must catch ---------------------------------------


def test_two_documents_stating_different_limits_is_a_high_severity_finding():
    """The dangerous case: someone operates to whichever one they read."""
    found = find_contradictions([
        _Chunk("The kero merox sulphur limit is 10 ppm.", "SOP-114.docx"),
        _Chunk("The kero merox sulphur limit is 15 ppm.", "Spec_Sheet.xlsx"),
    ])

    assert len(found) == 1
    assert found[0].severity == "high"
    assert found[0].kind == "limit"
    assert set(found[0].values_seen) == {"10 ppm", "15 ppm"}
    assert "safety risk" in found[0].explanation


def test_the_explanation_names_both_documents():
    """A finding a reader cannot act on is not a finding."""
    found = find_contradictions([
        _Chunk("Benzene exposure limit is 1 ppm.", "HSE_Manual.docx"),
        _Chunk("Benzene exposure limit is 5 ppm.", "Circular.docx"),
    ])

    assert "HSE_Manual.docx" in found[0].explanation
    assert "Circular.docx" in found[0].explanation


def test_limit_disagreements_sort_above_medium_findings():
    """A limit disagreement buried under a list of medium findings is a
    limit disagreement nobody reads."""
    found = find_contradictions([
        _Chunk("Recycle gas flow 1200 nm3/h.", "A.docx"),
        _Chunk("Recycle gas flow 1400 nm3/h.", "B.docx"),
        _Chunk("WABT end-of-run limit is 425 degC.", "A.docx"),
        _Chunk("WABT end-of-run limit is 430 degC.", "B.docx"),
    ])

    assert found, "expected at least one finding"
    assert found[0].severity == "high"


# ---- the four things that are NOT contradictions -------------------------


def test_the_same_limit_in_different_units_is_not_a_contradiction():
    """"1 bar" and "100 kpa" are the same pressure. Comparing numerals
    would flag it, and that false positive is what gets a detector
    switched off."""
    a = Claim(subject="header pressure", value=1.0, unit="bar", kind="limit",
              source_document="A.docx", sentence="x")
    b = Claim(subject="header pressure", value=100.0, unit="kpa", kind="limit",
              source_document="B.docx", sentence="y")

    assert values_are_equivalent(a, b) is True


def test_a_reading_does_not_contradict_a_limit():
    """"sulphur was 8.9 ppm" and "the limit is 10 ppm" are consistent —
    in fact one is evidence about the other."""
    found = find_contradictions([
        _Chunk("The sulphur limit is 10 ppm.", "SOP.docx"),
        _Chunk("Sulphur was measured at 8.9 ppm.", "LabSheet.xlsx"),
    ])

    assert found == []


def test_two_dated_readings_are_a_trend_not_a_disagreement():
    """A time series is not a contradiction, and treating it as one would
    flag every log file in the corpus."""
    found = find_contradictions([
        _Chunk("On 2026-08-12 sulphur was measured at 9.4 ppm.", "LabSheet.xlsx"),
        _Chunk("On 2026-08-19 sulphur was measured at 11.2 ppm.", "Trend_Log.xlsx"),
    ])

    assert found == []


def test_different_equipment_sharing_a_word_are_different_subjects():
    """HCU-2 and HCU-3 are different units. Substring subject matching
    would merge them — the same lesson as the single-letter entity
    fuzzy-merge bug in entity_extraction.py."""
    found = find_contradictions([
        _Chunk("HCU-2 WABT end-of-run limit is 425 degC.", "A.docx"),
        _Chunk("HCU-3 WABT end-of-run limit is 438 degC.", "B.docx"),
    ])

    assert found == []


def test_incompatible_quantities_cannot_contradict_each_other():
    """A temperature and a concentration are not competing claims about
    one thing, whatever their numerals."""
    a = Claim(subject="x", value=10.0, unit="ppm", kind="limit",
              source_document="A", sentence="s")
    b = Claim(subject="x", value=10.0, unit="degC", kind="limit",
              source_document="B", sentence="s")

    assert values_are_equivalent(a, b) is True  # treated as non-conflicting


def test_differing_values_inside_one_document_are_not_reported():
    """Usually a table of readings — and a document is free to
    contradict itself in ways only its author can resolve."""
    found = find_contradictions([
        _Chunk("Sulphur limit is 10 ppm. Sulphur limit is 15 ppm.", "OneDoc.docx"),
    ])

    assert found == []


def test_the_same_value_stated_twice_is_agreement_not_conflict():
    found = find_contradictions([
        _Chunk("The benzene limit is 1 ppm.", "A.docx"),
        _Chunk("The benzene limit is 1 ppm.", "B.docx"),
    ])

    assert found == []


def test_trailing_precision_is_not_a_disagreement():
    """0.9999 bar and 1.0 bar are the same pressure written to different
    precision."""
    a = Claim(subject="p", value=0.9999999, unit="bar", kind="limit",
              source_document="A", sentence="s")
    b = Claim(subject="p", value=1.0, unit="bar", kind="limit",
              source_document="B", sentence="s")

    assert values_are_equivalent(a, b) is True


# ---- extraction ----------------------------------------------------------


def test_bare_numbers_without_units_are_not_extracted_as_claims():
    """Matching every number would pull in revision numbers, page numbers
    and equipment tags, and a report full of those is noise."""
    claims = extract_claims_by_pattern(
        "See SOP-114 Rev 3, section 5, page 12 for details.", "A.docx"
    )

    assert claims == []


def test_limit_phrasings_are_classified_as_limits():
    for phrasing in (
        "Sulphur shall not exceed 10 ppm.",
        "Maximum sulphur is 10 ppm.",
        "The sulphur spec limit is 10 ppm.",
        "WABT end-of-run is 425 degC.",
    ):
        claims = extract_claims_by_pattern(phrasing, "A.docx")
        assert claims, f"nothing extracted from {phrasing!r}"
        assert claims[0].kind == "limit", phrasing


def test_reading_phrasings_are_classified_as_readings():
    claims = extract_claims_by_pattern("Sulphur was measured at 8.9 ppm.", "A.docx")

    assert claims[0].kind == "reading"


def test_a_dated_sentence_is_marked_temporal():
    claims = extract_claims_by_pattern("On 2026-08-19 sulphur reached 11.2 ppm.", "A.docx")

    assert claims[0].has_date is True


def test_extraction_is_deterministic():
    """A contradiction report is a safety artifact. One whose contents
    change between runs on identical input is not one anybody can act
    on."""
    text = "The kero merox sulphur limit is 10 ppm. WABT end-of-run is 425 degC."

    first = extract_claims_by_pattern(text, "A.docx")
    second = extract_claims_by_pattern(text, "A.docx")

    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]


def test_an_llm_extractor_can_be_substituted():
    """Better recall is available for callers who can pay for it, without
    making a model the default for a safety artifact."""
    def fake_llm_extractor(text, source_document):
        return [Claim(subject="benzene twa", value=1.0, unit="ppm", kind="limit",
                      source_document=source_document, sentence=text)]

    found = find_contradictions(
        [_Chunk("anything", "A.docx"), _Chunk("anything", "B.docx")],
        extract_fn=lambda t, s: (
            fake_llm_extractor(t, s)
            if s == "A.docx"
            else [Claim(subject="benzene twa", value=5.0, unit="ppm", kind="limit",
                        source_document=s, sentence=t)]
        ),
    )

    assert len(found) == 1
    assert found[0].subject == "benzene twa"


def test_chunks_with_ingestion_metadata_shape_are_supported():
    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

    def _chunk(text, source):
        return IngestedChunk(
            text=text,
            metadata=ChunkMetadata(
                source_document=source, document_type="docx", page_number=None,
                chunk_index=0, ingestion_date="2026-09-11",
            ),
        )

    found = find_contradictions([
        _chunk("The benzene limit is 1 ppm.", "A.docx"),
        _chunk("The benzene limit is 5 ppm.", "B.docx"),
    ])

    assert len(found) == 1
