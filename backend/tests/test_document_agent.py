"""Documents and spreadsheets are grounded the way slides are.

The bug this engine exists to prevent, measured on the previous one:
"Draft a PDF report on the CCR-1 regeneration cycle 18 findings" produced
twelve sections from nine documents, among them VIBECODING_SPEC.md,
OWNERSHIP.md, TOOLS.md and Sahil.md -- this project's own paperwork,
pasted into a refinery report under generated headings.
"""

from __future__ import annotations

import time

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


def test_a_section_that_retells_an_earlier_one_is_dropped(monkeypatch):
    """MEASURED on a live PDF: two headings, one incident, told twice —
    which reads as two separate findings."""
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: DOCS)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (1.0, []))
    monkeypatch.setattr(D, "sources_can_answer", lambda *a, **k: (True, ""))
    monkeypatch.setattr(D, "plan_document", lambda *a, **k: {
        "title": "t", "subtitle": "", "sections": [{"heading": "What happened"}, {"heading": "Why it matters"}]})
    first = _section(heading="What happened")
    twin = _section(heading="Why it matters", body=_section()["body"] + " The cycle ran long.")
    written = iter([first, twin, twin])
    monkeypatch.setattr(D, "write_section", lambda *a, **k: next(written))

    spec = D.build_document_spec("Report on CCR-1 cycle 18", object(), [])
    assert [s["heading"] for s in spec["sections"]] == ["What happened"]
    assert "says the same as" in spec["dropped_sections"][0]


def test_sections_on_different_material_are_both_kept():
    different = _section(heading="Coke burn rate",
                         body="The coke burn rate held at 128 kg/hr throughout the regeneration, "
                              "within the range the procedure allows for a cycle of this length.")
    assert D.is_retelling(different["body"], _section()["body"]) is False


def test_shared_vocabulary_is_not_a_retelling_when_the_figures_differ():
    """Sections of a manual share their words; what tells them apart is their
    figures. Overlap alone dropped eight of nine sections of a book summary."""
    one = ("Procedure 12 covers valve isolation, a purge duration of 30 minutes, and the pressure "
           "check the manual requires at step 12 before release.")
    two = ("Procedure 47 covers valve isolation, a purge duration of 90 minutes, and the pressure "
           "check the manual requires at step 47 before release.")
    assert D._overlap(one, two) >= D.DUPLICATE_OVERLAP, "these do share their vocabulary"
    assert D.is_retelling(one, two) is False, "different procedures, different figures"


# ── a long source (a book) is read end to end, not just its opening ─────────


def _book(blocks: int = 120) -> list[dict]:
    """A source of `blocks` 1,000-character sections, each named, so both
    coverage across the document and per-section selection are checkable."""
    text = "".join(
        f"MARKER{i} Procedure {i} of the manual is carried out as follows. ".ljust(1000, "x")
        for i in range(blocks)
    )
    return [{"id": "S1", "document": "Manual.pdf", "pages": [1], "truncated": False, "text": text}]


def test_the_outline_is_planned_from_across_the_whole_document():
    """A 500-page book's first 16,000 characters is chapter one; a summary
    planned from it covers chapter one."""
    import re

    view = D.outline_view(_book())
    markers = set(re.findall(r"MARKER(\d+)", view))
    assert len(markers) >= 8, f"the outline saw only {sorted(markers)}"
    numbers = sorted(int(m) for m in markers)
    assert numbers[0] <= 5, "the opening is missing"
    assert numbers[-1] >= 100, "the end of the book is missing"


def test_a_section_is_written_from_the_passages_that_match_it():
    docs = _book()
    context = D.context_for({"heading": "Procedure 47", "must_cover": ["procedure 47"]}, docs)
    text = " ".join(d["text"] for d in context)
    assert "procedure 47" in text.lower(), "the section's own passage is missing"
    assert len(text) <= D.SECTION_CONTEXT_CHARS + 1200, "a section gets its passages, not the whole book"


def test_a_long_source_earns_more_sections_and_writes_them_in_parallel(monkeypatch):
    import threading

    docs = _book()
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: docs)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (1.0, []))
    monkeypatch.setattr(D, "sources_can_answer", lambda *a, **k: (True, ""))

    seen_max = {"n": 0}
    running = {"n": 0}
    lock = threading.Lock()

    def slow_write(request, planned, context, *, writer):
        with lock:
            running["n"] += 1
            seen_max["n"] = max(seen_max["n"], running["n"])
        time.sleep(0.05)
        with lock:
            running["n"] -= 1
        n = planned["heading"].split()[-1]
        # Distinct wording per section: near-identical bodies are dropped as
        # duplicates, which is the behaviour tested above.
        return {"heading": planned["heading"],
                "body": f"Procedure {n} covers {'valve' * (int(n) % 3 + 1)} isolation, purge duration "
                        f"{n}0 minutes, and the {'pressure' if int(n) % 2 else 'temperature'} check the "
                        f"manual requires at step {n} before release.",
                "sources": ["S1"], "contains_estimate": False}

    monkeypatch.setattr(D, "write_section", slow_write)
    monkeypatch.setattr(D, "plan_document", lambda *a, **k: {
        "title": "The manual", "subtitle": "",
        "sections": [{"heading": f"Procedure {i}"} for i in range(9)]})

    spec = D.build_document_spec("Summarise the manual", object(), [])
    assert len(spec["sections"]) == 9
    assert seen_max["n"] > 1, "sections of a long source are written concurrently"


def test_a_report_may_read_the_whole_book_not_four_pages_of_it(monkeypatch):
    """Anchoring caps a document at 7,000 characters because a deck shows
    whole documents to the model. A report reads passages, so it asks for
    the book — otherwise a 500-page source is summarised from chapter one."""
    seen = {}

    def fake_anchor(store, chunks, request, *, max_chars_per_doc, max_chars_total):
        seen.update(per_doc=max_chars_per_doc, total=max_chars_total)
        return DOCS

    monkeypatch.setattr(D, "anchor_documents", fake_anchor)
    monkeypatch.setattr(D, "topic_coverage", lambda *a, **k: (1.0, []))
    monkeypatch.setattr(D, "sources_can_answer", lambda *a, **k: (True, ""))
    monkeypatch.setattr(D, "plan_document", lambda *a, **k: None)
    with pytest.raises(NotInCorpus):
        D.build_document_spec("Summarise the manual", object(), [])
    assert seen["per_doc"] >= 1_000_000 and seen["total"] >= 1_000_000
