"""TOOLS.md row 56 — lab readings against spec limits, computed not copied."""

from backend.tools.spec_compliance import (
    EXCEEDANCE,
    NEAR_LIMIT,
    OK,
    UNCOMPARABLE,
    check_spec_compliance,
)


def test_status_is_computed_not_read_from_the_document():
    """The corpus sheet carries a Status column, filled in by a person.

    A tool that reports what that column says adds nothing a reader
    could not see and inherits every mistake in it. Here the document
    says OK on a reading that exceeds its limit -- a compliance failure
    that has already passed somebody's review, and one that is invisible
    to everyone reading the status column.
    """
    report = check_spec_compliance([
        {
            "sample": "2026-09-02 Kero Merox SKO",
            "value": 12.6,
            "limit": 10,
            "units": "ppm",
            "stated_status": "OK",
        }
    ])

    verdict = report.verdicts[0]
    assert verdict.status == EXCEEDANCE, "the document's own status was trusted"
    assert verdict.disagrees_with_document is True
    assert verdict.stated_status == "OK"
    assert report.disagreements == [verdict]
    assert "disagrees" in report.summary()


def test_an_agreeing_document_is_not_reported_as_a_disagreement():
    report = check_spec_compliance([
        {"sample": "s", "value": 11.2, "limit": 10, "units": "ppm",
         "stated_status": "EXCEEDANCE"},
    ])
    assert report.verdicts[0].status == EXCEEDANCE
    assert report.disagreements == []


def test_unfamiliar_wording_is_not_called_a_disagreement():
    """Claiming the document is wrong because its vocabulary is
    unfamiliar is worse than saying nothing."""
    report = check_spec_compliance([
        {"sample": "s", "value": 11.2, "limit": 10, "units": "ppm",
         "stated_status": "REFER TO QA"},
    ])
    assert report.verdicts[0].status == EXCEEDANCE
    assert report.verdicts[0].disagrees_with_document is False


def test_units_are_reconciled_before_comparison():
    """The error class row 29 exists to prevent: 0.0008 % and 8 ppm are
    the same reading, and comparing 0.0008 against 10 says "comfortably
    within spec" for a number that is not."""
    report = check_spec_compliance([
        {"sample": "pct", "value": 0.0008, "limit": 10, "units": "percent",
         "limit_units": "ppm"},
    ])
    verdict = report.verdicts[0]
    assert verdict.status == OK
    # 0.0008 % is 8 ppm, so the margin to a 10 ppm limit is 2, not 9.9992.
    assert verdict.margin_to_limit == 2.0


def test_a_reading_that_cannot_be_converted_is_never_silently_compared():
    report = check_spec_compliance([
        {"sample": "wrong dimension", "value": 5, "limit": 10, "units": "bar",
         "limit_units": "ppm"},
    ])
    verdict = report.verdicts[0]
    assert verdict.status == UNCOMPARABLE
    assert "cannot convert" in verdict.note
    assert verdict.margin_to_limit is None
    assert report.uncomparable == [verdict]


def test_near_limit_is_a_stated_policy_not_a_hidden_judgement():
    readings = [{"sample": "s", "value": 9.4, "limit": 10, "units": "ppm"}]

    assert check_spec_compliance(readings).verdicts[0].status == NEAR_LIMIT
    # A plant that considers 6% the right margin gets a different answer,
    # and the answer says which margin it used.
    tighter = check_spec_compliance(readings, near_limit_fraction=0.05)
    assert tighter.verdicts[0].status == OK
    assert "5%" in tighter.summary()


def test_a_missing_or_unparseable_value_is_uncomparable_not_zero():
    report = check_spec_compliance([
        {"sample": "blank", "limit": 10, "units": "ppm"},
        {"sample": "text", "value": "pending", "limit": 10, "units": "ppm"},
    ])
    assert [v.status for v in report.verdicts] == [UNCOMPARABLE, UNCOMPARABLE]


def test_a_clean_sheet_says_so_plainly():
    report = check_spec_compliance([
        {"sample": "a", "value": 3.2, "limit": 10, "units": "ppm"},
        {"sample": "b", "value": 4.1, "limit": 10, "units": "ppm"},
    ])
    assert report.exceedances == []
    assert "No exceedances" in report.summary()


def test_the_same_input_gives_the_same_answer():
    """A safety artifact whose contents change between runs on identical
    input is not one anybody can act on. No model is involved."""
    readings = [
        {"sample": "a", "value": 9.4, "limit": 10, "units": "ppm"},
        {"sample": "b", "value": 11.2, "limit": 10, "units": "ppm"},
    ]
    first = check_spec_compliance(readings).summary()
    second = check_spec_compliance(readings).summary()
    assert first == second


def test_the_tool_is_reachable_through_the_registry():
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import all_tools

    registry = all_tools()
    names = set(registry) if isinstance(registry, dict) else {t.name for t in registry}
    assert "check_spec_compliance" in names
