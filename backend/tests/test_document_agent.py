"""Documents and spreadsheets are grounded the way slides are.

The bug this engine exists to prevent, measured on the previous one:
"Draft a PDF report on the CCR-1 regeneration cycle 18 findings" produced
twelve sections from nine documents, among them VIBECODING_SPEC.md,
OWNERSHIP.md, TOOLS.md and Sahil.md -- this project's own paperwork,
pasted into a refinery report under generated headings.
"""

from __future__ import annotations

import pytest

from backend.orchestrator import document_agent as D
from backend.orchestrator.deck_agent import NotInCorpus

DOCS = [{"id": "S1", "document": "Inspection_Report_CCR1.pdf", "pages": [1], "truncated": False,
         "text": "Cycle 18 took 34 hours against a target of 28 hours. "
                 "Chlorination efficiency was 84% against a normal range of 90 - 96. "
                 "Coke burn rate 128 kg/hr."}]


def _section(**over):
    base = {"heading": "Cycle 18 ran six hours long",
            "body": "Cycle 18 took 34 hours against a target of 28 hours, six hours beyond plan. "
                    "Chlorination efficiency was 84% against a normal range of 90 - 96.",
            "sources": ["S1"], "contains_estimate": False}
    base.update(over)
    return base


# ── sections ────────────────────────────────────────────────────────────────


def test_a_figure_no_source_contains_is_rejected():
    """A number in a refinery report that no document gives is a fabricated measurement."""
    bad = _section(body="Cycle 18 took 34 hours and cost 4200 USD in lost throughput, "
                        "against a target of 28 hours and a normal range of 90 - 96.")
    section, why = D.validate_section(bad, DOCS)
    assert section is None and "4200" in why


def test_a_section_with_no_resolvable_source_is_dropped():
    section, why = D.validate_section(_section(sources=["S7"]), DOCS)
    assert section is None and "source" in why


def test_a_stub_section_is_rejected():
    section, why = D.validate_section(_section(body="Cycle 18 ran long."), DOCS)
    assert section is None and "at least" in why


def test_a_grounded_section_passes_and_is_normalised():
    section, why = D.validate_section(_section(body="  Cycle 18 took 34 hours\n\nagainst a target "
                                                    "of 28 hours, six hours beyond plan. Chlorination "
                                                    "efficiency was 84% against 90 - 96 normal.  "), DOCS)
    assert section is not None, why
    assert "\n" not in section["body"] and "  " not in section["body"]
    assert section["sources"] == ["S1"]


def test_single_digits_are_not_treated_as_measurements():
    """Counts and step numbers are not figures; the deck engine draws the same line."""
    assert D.validate_section(_section(body="Three of the 4 beds were inspected during the 34-hour "
                                            "cycle, against a 28-hour target, and 2 required a coke "
                                            "burn at 128 kg/hr before restart."), DOCS)[0] is not None


# ── the pipeline refuses rather than writing something plausible ────────────


def test_a_request_the_corpus_does_not_cover_is_refused(monkeypatch):
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: DOCS)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (0.0, ["diwali", "recipes"]))
    with pytest.raises(NotInCorpus, match="do not cover"):
        D.build_document_spec("Write a report on Diwali recipes", object(), [])


def test_sections_the_sources_cannot_support_are_dropped_not_shipped(monkeypatch):
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: DOCS)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (1.0, []))
    monkeypatch.setattr(D, "sources_can_answer", lambda *a, **k: (True, ""))
    monkeypatch.setattr(D, "plan_document", lambda *a, **k: {
        "title": "CCR-1 cycle 18", "subtitle": "Findings",
        "sections": [{"heading": "What happened"}, {"heading": "Costs"}]})
    costly = _section(heading="Costs", body="The overrun cost 4200 USD in lost throughput over the "
                                            "34 hour cycle, against a 28 hour target, with "
                                            "chlorination efficiency at 84%.")
    written = iter([_section(), costly, costly])
    monkeypatch.setattr(D, "write_section", lambda *a, **k: next(written))
    spec = D.build_document_spec("Report on CCR-1 cycle 18", object(), [])
    assert [s["heading"] for s in spec["sections"]] == ["Cycle 18 ran six hours long"]
    assert spec["dropped_sections"] and "4200" in spec["dropped_sections"][0]
    assert spec["documents"] == ["Inspection_Report_CCR1.pdf"]


def test_a_report_with_nothing_left_is_a_refusal_not_an_empty_file(monkeypatch):
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: DOCS)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (1.0, []))
    monkeypatch.setattr(D, "sources_can_answer", lambda *a, **k: (True, ""))
    monkeypatch.setattr(D, "plan_document", lambda *a, **k: {
        "title": "t", "subtitle": "", "sections": [{"heading": "Costs"}]})
    monkeypatch.setattr(D, "write_section", lambda *a, **k: _section(
        body="Cost was 4200 USD across the 34 hour cycle against a 28 hour target, with "
             "chlorination efficiency measured at 84% of the normal 90 - 96 range."))
    with pytest.raises(NotInCorpus, match="could fill a section"):
        D.build_document_spec("Report on costs", object(), [])


# ── spreadsheets ────────────────────────────────────────────────────────────


def test_a_cell_no_source_supports_is_emptied_never_guessed():
    sheet, why = D.validate_sheet({
        "sheet_name": "Batches", "headers": ["Parameter", "Value"],
        "rows": [{"cells": ["Cycle time", "34 hours"], "sources": ["S1"]},
                 {"cells": ["Throughput loss", "4200 USD"], "sources": ["S1"]}]}, DOCS)
    assert sheet is not None, why
    assert sheet["rows"][0]["cells"] == ["Cycle time", "34 hours"]
    assert sheet["rows"][1]["cells"] == ["Throughput loss", ""], "an invented figure must not be printed"
    assert sheet["emptied_cells"] == 1


def test_a_sheet_needs_headers_and_rows():
    assert D.validate_sheet({"headers": ["only one"], "rows": [{"cells": ["a"]}]}, DOCS)[0] is None
    assert D.validate_sheet({"headers": ["a", "b"], "rows": []}, DOCS)[0] is None


def test_rows_are_padded_to_the_header_count():
    sheet, _ = D.validate_sheet({"sheet_name": "S", "headers": ["A", "B", "C"],
                                 "rows": [{"cells": ["x"], "sources": ["S1"]}]}, DOCS)
    assert sheet["rows"][0]["cells"] == ["x", "", ""]


def test_a_row_with_no_source_is_marked_unsourced():
    sheet, _ = D.validate_sheet({"sheet_name": "S", "headers": ["A", "B"],
                                 "rows": [{"cells": ["x", "y"], "sources": []}]}, DOCS)
    assert sheet["rows"][0]["is_unsourced"] is True
