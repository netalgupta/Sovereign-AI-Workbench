"""The deck design system and the content engine.

THE GEOMETRY TEST IS THE POINT OF THIS FILE. The complaint that started
this rewrite was that decks looked bad, and the specific, checkable part
of "bad" was text sitting on top of other text and running off the page.
Both are now assertions over the rendered file, so neither can come back
quietly.

No model is called here. The content engine's model calls are stubbed;
what is tested is the validation around them -- which is what stops a
fabricated figure reaching a slide.
"""

from __future__ import annotations

import pytest
from pptx import Presentation
from pptx.util import Emu

from backend.orchestrator import deck_agent as D
from backend.tools.generation.deck import fit, render, theme


# ── text fitting ────────────────────────────────────────────────────────────


def test_longer_text_wraps_to_more_lines():
    short = fit.wrap_lines("Cycle 18 ran long.", 4.0, 18)
    long = fit.wrap_lines("Cycle 18 ran 34 hours against a 28-hour target, the second "
                          "consecutive extended cycle after three inside the normal range.", 4.0, 18)
    assert len(short) == 1
    assert len(long) > len(short)


def test_fit_size_shrinks_until_it_fits_and_gives_up_honestly():
    text = "Regeneration cycle 18 duration exceeded the target by six hours " * 6
    size = fit.fit_size(text, 4.0, 1.0, 28, 12)
    assert size is None or size <= 28
    tight = fit.fit_size(text, 1.0, 0.2, 28, 24)
    assert tight is None, "must report that it cannot fit rather than overflowing"


def test_measurement_uses_the_real_font_not_a_character_count():
    """'iiii' and 'WWWW' are the same length and nowhere near the same width."""
    narrow = fit.text_width_pt("iiii", 24)
    wide = fit.text_width_pt("WWWW", 24)
    assert wide > narrow * 1.8


# ── rendering ───────────────────────────────────────────────────────────────


def _spec(slides: list[dict], sections: int = 1) -> dict:
    return {
        "title": "CCR-1 regeneration cycle 18 ran six hours long",
        "subtitle": "Findings and the actions required before Cycle 19",
        "date": "18 September 2026",
        "sources": [{"id": "S1", "document": "Inspection_Report_CCR1.pdf", "pages": [1, 2],
                     "used_for": "durations and efficiencies"}],
        "sections": [{"title": f"Section {i + 1}", "summary": "why it matters", "slides": slides}
                     for i in range(sections)],
    }


ALL_LAYOUTS = [
    {"type": "points", "title": "Evidence points to the dryer, not the catalyst",
     "bullets": ["Coke burn rate held at 128 kg/hr, within design.",
                 "Chloride retention fell with chlorination efficiency."],
     "callout": {"value": "84", "unit": "%", "label": "Chlorination efficiency in Cycle 18"},
     "sources": ["S1"]},
    {"type": "big_stat", "title": "Cycle 18 ran 34 hours against a 28-hour target", "value": "34",
     "unit": "hours", "label": "Cycle 18 duration", "context": "Six hours over target.",
     "status": "exceeded", "compare": {"value": "28 h", "label": "Target"}, "sources": ["S1"]},
    {"type": "kpis", "title": "Three of four parameters sit outside normal range",
     "items": [{"value": "34", "unit": "h", "label": "Duration", "status": "exceeded"},
               {"value": "84", "unit": "%", "label": "Chlorination", "status": "high"},
               {"value": "128", "unit": "kg/hr", "label": "Coke burn", "status": "normal"}],
     "sources": ["S1"]},
    {"type": "chart", "title": "Duration climbed for two consecutive cycles", "chart_type": "column",
     "categories": ["Cycle 16", "Cycle 17", "Cycle 18"],
     "series": [{"name": "Duration", "values": [27, 31, 34]}], "unit": "hours",
     "highlight": "Cycle 18", "takeaways": ["Two consecutive excursions."], "sources": ["S1"]},
    {"type": "table", "title": "Parameters against their limits",
     "columns": ["Parameter", "Cycle 18", "Normal", "Status"],
     "rows": [["Duration", "34 h", "28 h", "Exceeded"], ["Chlorination", "84%", "90-96%", "High"]],
     "caption": "From IR-CCR1-2026-018.", "sources": ["S1"]},
    {"type": "process", "title": "The escalation path if Cycle 19 also runs long",
     "steps": [{"title": "Run Cycle 19", "detail": "Monitor duration."},
               {"title": "Compare to 30 h", "detail": "Above 30 hours escalates."},
               {"title": "Full review", "detail": "Process Engineering opens a review."}],
     "sources": ["S1"]},
    {"type": "timeline", "title": "Two cycles drifted before the excursion was raised",
     "events": [{"date": "2026-07-02", "title": "Cycle 17", "detail": "31 hours."},
                {"date": "2026-08-11", "title": "Cycle 18", "detail": "34 hours."}],
     "sources": ["S1"]},
    {"type": "alert", "title": "Moisture ingress is the probable cause", "severity": "high",
     "headline": "Chlorination efficiency fell to 84% against a 90-96% range",
     "what": "Moisture ingress in the regeneration gas circuit.",
     "impact": "Chloride retention fell to 0.85%.", "action": "Inspect D-102 before Cycle 19.",
     "sources": ["S1"]},
    {"type": "comparison", "title": "Cycle 17 and Cycle 18 compared",
     "columns": [{"title": "Cycle 17", "points": ["31 hours", "91% efficiency"], "status": "watch"},
                 {"title": "Cycle 18", "points": ["34 hours", "84% efficiency"], "status": "exceeded"}],
     "sources": ["S1"]},
    {"type": "actions", "title": "Three actions close this out before Cycle 19",
     "items": [{"action": "Inspect D-102 desiccant bed", "owner": "Maintenance", "due": "Before Cycle 19",
                "priority": "high"},
               {"action": "Verify AI-4471 calibration", "owner": "Instrumentation", "due": "Before Cycle 19",
                "priority": "medium"}],
     "sources": ["S1"]},
]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    out = tmp_path_factory.mktemp("deck") / "all_layouts.pptx"
    result = render.render_deck(_spec(ALL_LAYOUTS, sections=3), out)
    return Presentation(str(out)), result


def test_every_layout_renders(rendered):
    prs, result = rendered
    # cover + agenda + 3 dividers + 30 content slides + appendix
    assert result["slide_count"] == len(prs.slides) == 1 + 1 + 3 + 3 * len(ALL_LAYOUTS) + 1


def _text_boxes(slide):
    boxes = []
    for sh in slide.shapes:
        if not sh.has_text_frame or not sh.text_frame.text.strip():
            continue
        boxes.append((sh.left, sh.top, sh.width, sh.height, sh.text_frame.text.strip()))
    return boxes


def test_no_text_box_overlaps_another(rendered):
    """Overlapping text is what made the old decks unreadable: a title
    running over the bullets beneath it."""
    prs, _ = rendered
    for i, slide in enumerate(prs.slides, 1):
        boxes = _text_boxes(slide)
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                ax, ay, aw, ah, at = boxes[a]
                bx, by, bw, bh, bt = boxes[b]
                overlap_w = min(ax + aw, bx + bw) - max(ax, bx)
                overlap_h = min(ay + ah, by + bh) - max(ay, by)
                if overlap_w <= 0 or overlap_h <= 0:
                    continue
                area = overlap_w * overlap_h
                smaller = min(aw * ah, bw * bh)
                assert area < smaller * 0.5, (
                    f"slide {i}: {at[:30]!r} overlaps {bt[:30]!r}"
                )


def test_nothing_is_placed_outside_the_page(rendered):
    prs, _ = rendered
    page_w, page_h = Emu(int(theme.PAGE_W * 914400)), Emu(int(theme.PAGE_H * 914400))
    tolerance = 914400 * 0.02
    for i, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.left is None or sh.top is None:
                continue
            assert sh.left >= -tolerance, f"slide {i}: shape off the left edge"
            assert sh.top >= -tolerance, f"slide {i}: shape above the top edge"
            assert sh.left + (sh.width or 0) <= page_w + tolerance, f"slide {i}: shape past the right edge"
            assert sh.top + (sh.height or 0) <= page_h + tolerance, f"slide {i}: shape past the bottom edge"


def test_every_content_slide_carries_a_title_and_its_source(rendered):
    prs, _ = rendered
    for i, slide in enumerate(prs.slides, 1):
        texts = [t for *_x, t in _text_boxes(slide)]
        if any("Source:" in t for t in texts):
            assert any(len(t) > 20 and "Source:" not in t for t in texts), f"slide {i} has no title"


def test_a_long_list_paginates_instead_of_shrinking_or_dropping(tmp_path):
    bullets = [f"Finding number {i} recorded during the inspection of the regeneration circuit."
               for i in range(1, 13)]
    out = tmp_path / "long.pptx"
    result = render.render_deck(
        _spec([{"type": "points", "title": "Twelve findings", "bullets": bullets, "sources": ["S1"]}]), out)
    prs = Presentation(str(out))
    body = "\n".join(t for s in prs.slides for *_x, t in _text_boxes(s))
    for b in bullets:
        assert b in body, "a bullet was dropped instead of continued onto another slide"
    assert result["slide_count"] >= 4  # cover + 3 content pages + appendix
    assert "(continued)" in body


def test_pages_are_balanced_not_greedy():
    """Five cards split 3+2. Greedy splitting left one card stretched
    across a slide of its own."""
    pages = render._chunks(list(range(5)), render.MAX_KPIS)
    assert [len(p) for p in pages] == [3, 2]


def test_a_deck_with_one_section_has_no_divider_or_agenda(tmp_path):
    out = tmp_path / "one.pptx"
    result = render.render_deck(_spec([ALL_LAYOUTS[0]], sections=1), out)
    assert result["slide_count"] == 3  # cover + the slide + appendix


# ── content engine validation ───────────────────────────────────────────────

DOCS = [{"id": "S1", "document": "Inspection_Report_CCR1.pdf", "pages": [1],
         "text": "Cycle 18 took 34 hours against a target of 28 hours. "
                 "Chlorination Efficiency (%) 91 84 90 - 96. Coke burn rate 128 kg/hr.",
         "truncated": False}]


def test_the_deliverable_words_are_stripped_before_retrieval():
    """Searching the request verbatim retrieved documents ABOUT
    presentations -- including this project's own PPTX guide."""
    assert D.topic_of("Make a presentation on the CCR-1 regeneration cycle") == "the CCR-1 regeneration cycle"
    assert D.topic_of("Create a PowerPoint about hydrocracker catalyst changeout") == "hydrocracker catalyst changeout"
    assert D.topic_of("give me a deck covering the Hassan pipeline incident") == "the Hassan pipeline incident"
    assert D.topic_of("CCR-1 findings") == "CCR-1 findings"


def test_slide_type_synonyms_are_accepted():
    """A model names types in its own words, or copies them out of a
    source document. Every section using an unrecognised name produced
    no slides at all."""
    assert D.canonical_type("multi_stat_row") == "kpis"
    assert D.canonical_type("Chart Commentary") == "chart"
    assert D.canonical_type("table_data") == "table"
    assert D.canonical_type("points") == "points"
    assert D.canonical_type("something_else") is None


def test_a_figure_no_source_contains_is_rejected():
    bad = {"type": "big_stat", "title": "Cycle duration exceeded its target", "value": "47",
           "label": "Duration", "context": "Ran long."}
    slide, why = D.validate_slide(bad, DOCS)
    assert slide is None and "no source document" in why


def test_the_same_number_written_differently_is_accepted():
    """"84.0" against a source that says "84%" is the same measurement."""
    ok = {"type": "big_stat", "title": "Chlorination efficiency fell below range", "value": "84.0",
          "unit": "%", "label": "Chlorination efficiency", "context": "Below the 90 - 96 range."}
    slide, why = D.validate_slide(ok, DOCS)
    assert slide is not None, why


def test_a_unit_already_inside_the_value_is_not_printed_twice():
    """It returned {"value": "478°C", "unit": "°C"}, rendering "478°C °C"."""
    slide, why = D.validate_slide(
        {"type": "kpis", "title": "Bed outlet temperature held steady",
         "items": [{"value": "128 kg/hr", "unit": "kg/hr", "label": "Coke burn"}]}, DOCS)
    assert slide is not None, why
    assert slide["items"][0]["unit"] == ""


def test_field_and_row_shapes_are_normalised():
    slide, why = D.validate_slide(
        {"type": "kpis", "title": "Parameters at cycle completion",
         "stats": [{"val": "34", "name": "Duration", "detail": "hours"}]}, DOCS)
    assert slide is not None, why
    assert slide["items"][0]["value"] == "34" and slide["items"][0]["label"] == "Duration"

    slide, why = D.validate_slide(
        {"type": "table", "title": "Parameters against limits", "columns": ["Parameter", "Value"],
         "rows": [{"Parameter": "Duration", "Value": "34 hours"}]}, DOCS)
    assert slide is not None, why
    assert slide["rows"] == [["Duration", "34 hours"]]


def test_a_chart_missing_a_value_per_category_is_rejected():
    slide, why = D.validate_slide(
        {"type": "chart", "title": "Duration trend across cycles", "categories": ["C16", "C17", "C18"],
         "series": [{"name": "Duration", "values": [28, 34]}]}, DOCS)
    assert slide is None and "one value per category" in why


def test_an_empty_required_field_is_rejected():
    slide, why = D.validate_slide({"type": "points", "title": "Findings from the inspection", "bullets": []}, DOCS)
    assert slide is None and "bullets" in why


def test_only_documents_near_the_best_match_become_sources(monkeypatch):
    """A weakly-matching document is not what the request is about; one
    such document is how sandbox RAM limits reached a pipeline deck."""
    import backend.retrieval.grounded_retrieval as gr

    class _Chunk:
        def __init__(self, doc, score):
            self.text, self.source_document, self.page_number, self.score = f"text of {doc}", doc, 1, score

    class _Result:
        found = True
        reason = None
        chunks = [_Chunk("relevant.pdf", 0.90), _Chunk("also_relevant.pdf", 0.62),
                  _Chunk("unrelated_guide.md", 0.30)]

    monkeypatch.setattr(gr, "retrieve_with_grounding_check", lambda *a, **k: _Result())
    docs = D.anchor_documents(object(), [], "CCR-1 regeneration")

    assert [d["document"] for d in docs] == ["relevant.pdf", "also_relevant.pdf"]


def test_nothing_retrieved_is_a_refusal(monkeypatch):
    import backend.retrieval.grounded_retrieval as gr

    class _Nothing:
        found = False
        chunks = []
        reason = "not found in the provided corpus"

    monkeypatch.setattr(gr, "retrieve_with_grounding_check", lambda *a, **k: _Nothing())
    with pytest.raises(D.NotInCorpus):
        D.anchor_documents(object(), [], "the plot of Pride and Prejudice")


# ── refusing a request the corpus cannot answer ─────────────────────────────


def test_topic_coverage_catches_a_semantically_close_but_wrong_document():
    """MEASURED: "our retail fuel station marketing strategy for Diwali"
    cleared the cosine gate against a PDF about the Jan Dhan Yojana, and
    the deck was titled for Diwali and written about financial inclusion."""
    pmjdy = [{"text": "PMJDY financial inclusion scheme targets 7.5 crore households with bank accounts."}]
    coverage, missing = D.topic_coverage(
        "Create a presentation on our retail fuel station marketing strategy for Diwali", pmjdy)
    assert coverage < D.MIN_TOPIC_COVERAGE
    assert "diwali" in missing

    ccr = [{"text": "Inspection Report CCR-1 Regeneration Cycle 18 findings: duration 34 hours."}]
    coverage, _ = D.topic_coverage("Make a deck on CCR-1 regeneration cycle findings", ccr)
    assert coverage >= D.MIN_TOPIC_COVERAGE


def _no_model_calls(monkeypatch):
    def fail(*_a, **_k):
        raise AssertionError("no deck may be planned for a request the corpus cannot answer")
    monkeypatch.setattr(D, "plan_storyline", fail)
    monkeypatch.setattr(D, "fill_section", fail)


def test_a_request_the_sources_do_not_mention_is_refused_before_planning(monkeypatch):
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: [
        {"id": "S1", "document": "Dhruvil.pdf", "pages": [1], "truncated": False,
         "text": "PMJDY financial inclusion scheme targets 7.5 crore households."}])
    _no_model_calls(monkeypatch)
    with pytest.raises(D.NotInCorpus, match="do not cover"):
        D.build_deck_spec("Create a presentation on our retail fuel station marketing strategy for Diwali",
                          object(), [])


def test_the_relevance_verdict_can_refuse_what_the_word_check_let_through(monkeypatch):
    monkeypatch.setattr(D, "anchor_documents", lambda *a, **k: [
        {"id": "S1", "document": "x.pdf", "pages": [1], "truncated": False,
         "text": "The regeneration cycle of a laptop battery, over many charge cycles."}])
    monkeypatch.setattr(D, "_ask_json", lambda *a, **k: {"can_answer": False,
                                                          "reason": "about laptop batteries"})
    _no_model_calls(monkeypatch)
    with pytest.raises(D.NotInCorpus, match="laptop batteries"):
        D.build_deck_spec("Make a deck on CCR-1 regeneration cycle", object(), [])


def test_a_sequence_filed_under_another_key_is_still_a_sequence():
    """Seven process slides were dropped for an empty "steps" while the
    model had filed the sequence under another name."""
    slide, why = D.validate_slide({"type": "process", "title": "Shutdown and purge sequence for R-201",
                                   "sequence": ["Depressurise R-201", "Purge with nitrogen"]}, DOCS)
    assert slide is not None, why
    assert slide["steps"] == [{"title": "Depressurise R-201"}, {"title": "Purge with nitrogen"}]
