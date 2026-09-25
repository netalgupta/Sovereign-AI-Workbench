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
    # The leading article goes too: the subject is also the TITLE of the file
    # this produces, and "the CCR-1 regeneration cycle" reads as a fragment.
    assert D.topic_of("Make a presentation on the CCR-1 regeneration cycle") == "CCR-1 regeneration cycle"
    assert D.topic_of("Create a PowerPoint about hydrocracker catalyst changeout") == "hydrocracker catalyst changeout"
    assert D.topic_of("give me a deck covering the Hassan pipeline incident") == "Hassan pipeline incident"
    # The deliverable words stack in real requests, and every one goes.
    assert D.topic_of("Build an Excel comparison table of the batch QA results") == "batch QA results"
    assert D.topic_of("Draft an approval note on the inspection findings and save it") == "inspection findings"
    # A question is not a deliverable request and is left alone.
    assert D.topic_of("Summarise the maintenance log") == "Summarise the maintenance log"
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
        def __init__(self, doc, score, text):
            self.text, self.source_document, self.page_number, self.score = text, doc, 1, score

    class _Result:
        found = True
        reason = None
        # The second document has to BE about the subject as well as score
        # near the first: a relative cosine score is a similarity, not a
        # subject (see the TOOLS.md contamination this rule was added for).
        chunks = [_Chunk("relevant.pdf", 0.90, "CCR-1 regeneration cycle 18 ran long."),
                  _Chunk("also_relevant.pdf", 0.62, "Annex: CCR-1 regeneration parameters."),
                  _Chunk("unrelated_guide.md", 0.30, "How to write a sandbox module guide.")]

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
    # No figures here on purpose: an equipment tag absent from the source
    # (R-201) is rejected like any other unsourced number.
    slide, why = D.validate_slide({"type": "process", "title": "Shutdown and purge sequence for the reactor",
                                   "sequence": ["Depressurise the reactor", "Purge with nitrogen"]}, DOCS)
    assert slide is not None, why
    assert slide["steps"] == [{"title": "Depressurise the reactor"}, {"title": "Purge with nitrogen"}]


def test_a_statement_is_not_accepted_as_a_measurement():
    """The model put an action in a KPI card's value and a place name in a
    callout; both rendered as headline figures."""
    slide, why = D.validate_slide(
        {"type": "kpis", "title": "Corrective actions after the incident",
         "items": [{"value": "Replace P-HS-02 discharge flange gasket", "label": "Action taken"}]}, DOCS)
    assert slide is None and "measurements" in why

    slide, _ = D.validate_slide(
        {"type": "points", "title": "Pressure drop and shutdown at the station",
         "bullets": ["Cycle 18 took 34 hours."], "callout": {"value": "Hassan Pumping Station", "label": "Location"}},
        DOCS)
    assert slide is not None and "callout" not in slide

    for good in ("34", "84%", "128 kg/hr", "> 28 hours"):
        assert D._MEASUREMENT.match(good), good


def test_one_slide_sections_get_no_dividers(tmp_path):
    """Four one-slide sections produced four dividers around five slides."""
    spec = _spec([ALL_LAYOUTS[0]], sections=4)
    result = render.render_deck(spec, tmp_path / "d.pptx")
    assert result["slide_count"] == 1 + 1 + 4 + 1  # cover, agenda, 4 slides, appendix


def test_bar_charts_start_at_zero(tmp_path):
    """A 31-vs-34 column chart auto-scaled from 29.5 drew a 10% rise as a
    tripling."""
    slide = {"type": "chart", "title": "Duration rose in the second cycle", "chart_type": "column",
             "categories": ["Cycle 17", "Cycle 18"], "series": [{"name": "Hours", "values": [31, 34]}],
             "sources": ["S1"]}
    out = tmp_path / "c.pptx"
    render.render_deck(_spec([slide]), out)
    charts = [sh.chart for s in Presentation(str(out)).slides for sh in s.shapes if sh.has_chart]
    assert charts and charts[0].value_axis.minimum_scale == 0


# ── a list of labelled figures is a chart ───────────────────────────────────


def test_a_list_of_figures_in_one_unit_becomes_a_column_chart():
    """Measured: August's production mix shipped as four bullets; the page
    reviewer rated it plain. The values are the bullets' own."""
    from backend.orchestrator.deck_agent import _chart_from_list

    slide = {"type": "points", "title": "Production Mix for August 2026", "sources": ["S1"],
             "bullets": ["Homopolymer H030SG: 22 batches produced.", "Homopolymer H110F: 16 batches produced.",
                         "Random Copolymer RP340: 12 batches produced.", "Impact Copolymer HP500: 9 batches produced."]}
    chart = _chart_from_list(slide)
    assert chart["type"] == "chart"
    assert chart["categories"] == ["Homopolymer H030SG", "Homopolymer H110F",
                                   "Random Copolymer RP340", "Impact Copolymer HP500"]
    assert chart["series"][0]["values"] == [22.0, 16.0, 12.0, 9.0]
    assert chart["unit"] == "batches" and chart["highlight"] == "Homopolymer H030SG"
    assert chart["sources"] == ["S1"]


@pytest.mark.parametrize("bullets", [
    ["Flow: 12 m3/h", "Temp: 365 °C", "Pressure: 14 bar"],                     # mixed units
    ["Unloading must proceed under nitrogen.", "H2S: 10 ppm", "Other: 5 ppm"],  # a sentence
    ["A: 10 %", "B: 20 %"],                                                     # too few to chart
    ["A: 10 %", "A: 20 %", "B: 5 %"],                                           # duplicate labels
])
def test_anything_less_regular_stays_a_list(bullets):
    from backend.orchestrator.deck_agent import _chart_from_list

    slide = {"type": "points", "title": "t", "bullets": bullets, "sources": ["S1"]}
    assert _chart_from_list(slide) is slide


# ── the status pill agrees with its own note ────────────────────────────────


def _kpi(status: str, note: str) -> dict:
    return {"type": "kpis", "title": "Cycle 18 parameters", "sources": ["S1"],
            "items": [{"value": "84", "unit": "%", "label": "Chlorination efficiency",
                       "note": note, "status": status},
                      {"value": "34", "unit": "h", "label": "Cycle time", "note": "Target 28 h",
                       "status": "watch"}]}


def test_a_value_below_its_range_is_not_labelled_exceeded():
    """Measured: 84% against 90-96 shipped as 'Below normal range' with a red EXCEEDED pill."""
    slide, why = D.validate_slide(_kpi("exceeded", "Below normal range"), DOCS)
    assert slide is None and "below" in why


def test_the_below_status_is_accepted_and_shown_as_below_range():
    slide, why = D.validate_slide(_kpi("below", "Below normal range"), DOCS)
    assert slide is not None, why
    assert theme.status_label("below") == "below range"
    assert theme.status_colours("below") == theme.status_colours("exceeded")


def test_a_below_status_over_a_note_saying_exceeded_is_rejected():
    slide, why = D.validate_slide(_kpi("below", "Exceeds the upper limit"), DOCS)
    assert slide is None and "exceeded" in why


def test_a_big_stat_is_checked_the_same_way():
    stat = {"type": "big_stat", "title": "Chlorination fell short", "value": "84", "unit": "%",
            "label": "Chlorination efficiency", "status": "exceeded", "sources": ["S1"],
            "context": "Cycle 18 chlorination efficiency was below the 90-96 normal range."}
    assert D.validate_slide(stat, DOCS)[0] is None
    assert D.validate_slide({**stat, "status": "below"}, DOCS)[0] is not None


# ── every list item carries what its layout draws ───────────────────────────


def test_timeline_events_with_kpi_field_names_are_rejected():
    """Measured: these rendered as a bare axis on an otherwise blank page."""
    slide = {"type": "timeline", "title": "Corrective Actions Timeline", "sources": ["S1"],
             "events": [{"value": "Replace P-HS-02 discharge flange gasket", "label": "Action Taken",
                         "note": "Completed on 2026-07-24", "status": "normal"},
                        {"value": "Inspect all pump seals", "label": "Action Taken",
                         "note": "Scheduled for 2026-08-05", "status": "watch"}]}
    out, why = D.validate_slide(slide, DOCS)
    assert out is None and "'title'" in why and "date" in why, why


def test_timeline_events_with_titles_pass():
    slide = {"type": "timeline", "title": "Corrective Actions Timeline", "sources": ["S1"],
             "events": [{"date": "July", "title": "Gasket replaced", "detail": "P-HS-02 discharge flange"},
                        {"date": "August", "title": "Seal inspection", "detail": "All Hassan pumps"}]}
    assert D.validate_slide(slide, DOCS)[0] is not None


def test_a_kpi_without_a_label_is_rejected():
    slide = {"type": "kpis", "title": "Cycle 18 parameters", "sources": ["S1"],
             "items": [{"value": "34", "unit": "h", "label": "Cycle time"}, {"value": "84", "unit": "%"}]}
    out, why = D.validate_slide(slide, DOCS)
    assert out is None and "[2]" in why


def _powerpoint_available() -> bool:
    try:
        import win32com.client  # noqa: F401
        import winreg

        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "PowerPoint.Application").Close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _powerpoint_available(), reason="needs PowerPoint to lay out and measure")
def test_powerpoint_measures_an_empty_page_as_empty(tmp_path):
    """The renderer drew an axis and no events: nothing to overflow, so nothing measured."""
    from backend.tools.generation.deck import qa

    spec = {"title": "Pipeline incident", "sources": [], "sections": [{"title": "Actions", "slides": [
        {"type": "timeline", "title": "Corrective Actions Timeline", "sources": [],
         "events": [{"value": "no title here"}, {"value": "nor here"}]},
        {"type": "points", "title": "What happened on the segment", "sources": [],
         "bullets": ["A gasket failed at the discharge flange.", "The line was isolated in minutes."]},
    ]}]}
    result = render.render_deck(spec, tmp_path / "d.pptx")
    measured = qa.render_and_measure(result["path"], tmp_path / "png")
    timeline_page = result["page_map"].index((0, 0)) + 1
    points_page = result["page_map"].index((0, 1)) + 1
    assert "empty" in measured["defects"][timeline_page]
    assert measured["defects"][points_page] == []


# ── no layout may emit a box PowerPoint cannot open ─────────────────────────

_SHORT_ALERT = {  # the live-deck slide that shipped cy="-150266"
    "type": "alert", "title": "Chlorination Efficiency Trend Down", "sources": [], "severity": "high",
    "headline": "Cycle 18 chlorination efficiency at 84%",
    "what": "Trend shows decreasing efficiency for two consecutive cycles",
    "impact": "May affect catalyst performance and regeneration effectiveness",
    "action": "Dryer inspection before Cycle 19, moisture analyzer calibration"}


def _every_layout(long: bool) -> list[dict]:
    t = (lambda s: (s + " ") * 12) if long else (lambda s: s)
    return [
        {"type": "points", "title": "A finding worth a slide", "bullets": [t("One."), t("Two.")]},
        {"type": "big_stat", "title": "One number carries it", "value": "84", "unit": "%",
         "label": t("Efficiency"), "context": t("Below range."), "status": "below"},
        {"type": "kpis", "title": "Parameters side by side",
         "items": [{"value": "34", "unit": "h", "label": t("Cycle"), "note": t("Long")},
                   {"value": "84", "unit": "%", "label": t("Cl"), "note": t("Low"), "status": "below"}]},
        {"type": "chart", "title": "Batches by grade", "categories": ["A", "B", "C"],
         "series": [{"name": "n", "values": [22, 16, 12]}], "takeaways": [t("A leads.")]},
        {"type": "table", "title": "Against the limits", "columns": ["P", "V"], "rows": [[t("a"), "1"]]},
        {"type": "process", "title": "The changeout sequence", "steps": [{"title": "Purge", "detail": t("N2")},
                                                                        {"title": "Unload", "detail": t("x")}]},
        {"type": "timeline", "title": "What happened when", "events": [
            {"date": "Jul", "title": "Gasket", "detail": t("d")}, {"date": "Aug", "title": "Seals", "detail": t("d")}]},
        _SHORT_ALERT if not long else {**_SHORT_ALERT, "what": t(_SHORT_ALERT["what"])},
        {"type": "comparison", "title": "Two options set side by side",
         "columns": [{"title": "A", "points": [t("p")]}, {"title": "B", "points": [t("q")]}]},
        {"type": "actions", "title": "What must happen next",
         "items": [{"action": t("Inspect"), "owner": "Ops", "due": "Aug", "priority": "high"}]},
    ]


@pytest.mark.parametrize("long", [False, True], ids=["short", "long"])
def test_every_layout_renders_only_positive_boxes(tmp_path, long):
    import re
    import zipfile

    spec = {"title": "Layout sweep", "sources": [],
            "sections": [{"title": "All", "slides": [{**sl, "sources": []} for sl in _every_layout(long)]}]}
    out = render.render_deck(spec, tmp_path / "d.pptx")
    with zipfile.ZipFile(out["path"]) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8")
                bad = re.findall(r'c[xy]="-\d+"', xml)
                assert not bad, f"{name}: {bad[:3]}"


def test_a_primitive_refuses_a_negative_box():
    from pptx import Presentation as P_

    from backend.tools.generation.deck import primitives

    slide = P_().slides.add_slide(P_().slide_layouts[6])
    with pytest.raises(ValueError, match="non-positive"):
        primitives.text(slide, 1, 1, 3, -0.35, "x", size=12)


# ── the two newest layouts ──────────────────────────────────────────────────


def test_a_quote_must_be_one_sentence_from_a_source():
    short = {"type": "quote", "title": "The standing instruction", "text": "Too short.", "sources": ["S1"]}
    assert D.validate_slide(short, DOCS)[0] is None
    long = {"type": "quote", "title": "The standing instruction", "sources": ["S1"],
            "text": "Unloading must proceed under a continuous nitrogen blanket, and full-face "
                    "supplied-air respirators are mandatory for all vessel-entry personnel.",
            "attribution": "SOP-114-Rev3, p. 2"}
    out, why = D.validate_slide(long, DOCS)
    assert out is not None, why
    assert out["attribution"] == "SOP-114-Rev3, p. 2"


def test_a_matrix_needs_exactly_four_titled_cells():
    three = {"type": "matrix", "title": "Findings by likelihood", "sources": ["S1"],
             "cells": [{"title": "A"}, {"title": "B"}, {"title": "C"}]}
    out, why = D.validate_slide(three, DOCS)
    assert out is None and "exactly 4" in why

    four = {"type": "matrix", "title": "Findings by likelihood", "sources": ["S1"],
            "cells": [{"title": f"Cell {i}", "items": ["One thing", "Another"], "status": "watch"}
                      for i in range(4)]}
    assert D.validate_slide(four, DOCS)[0] is not None


@pytest.mark.parametrize("alias, canonical", [("pull_quote", "quote"), ("statement", "quote"),
                                              ("two_by_two", "matrix"), ("quadrant", "matrix")])
def test_the_names_a_model_reaches_for_resolve(alias, canonical):
    assert D.canonical_type(alias) == canonical


# ── a second source must be about the subject, not merely near it ───────────


class _Chunk:
    def __init__(self, doc, text, idx=0):
        self.text = text
        self.metadata = type("M", (), {"source_document": doc, "chunk_index": idx, "page_number": 1})()


def _anchor_with(monkeypatch, docs_and_text, scores):
    """Retrieval returns `scores`; the corpus holds `docs_and_text`."""
    import backend.retrieval.grounded_retrieval as GR

    class Res:
        found = True
        reason = ""
        chunks = [type("C", (), {"source_document": d, "score": s, "page_number": 1,
                                 "text": docs_and_text[d]})() for d, s in scores.items()]

    monkeypatch.setattr(D, "retrieve_with_grounding_check", lambda *a, **k: Res(), raising=False)
    monkeypatch.setattr(GR, "retrieve_with_grounding_check", lambda *a, **k: Res())
    chunks = [_Chunk(d, t) for d, t in docs_and_text.items()]
    return D.anchor_documents(object(), chunks, "Draft a report on the Novolen batch QA results for August 2026")


def test_a_near_scoring_document_that_never_says_the_subject_is_dropped(monkeypatch):
    """MEASURED: TOOLS.md and SYSTEM_DESIGN_QA_RESPONSES.md (7 kB each of this
    project's own paperwork) were anchored beside a 1 kB Novolen report,
    because a relative cosine score is a similarity, not a subject."""
    docs = _anchor_with(monkeypatch, {
        "Novolen_Batch_QA_Report_Aug2026.pdf": "Novolen batch QA results for August 2026: H030SG, 22 batches.",
        "TOOLS.md": "This table lists every tool, its owner and its QA status in the workbench.",
    }, {"Novolen_Batch_QA_Report_Aug2026.pdf": 0.9, "TOOLS.md": 0.7})
    assert [d["document"] for d in docs] == ["Novolen_Batch_QA_Report_Aug2026.pdf"]


def test_the_best_match_is_always_kept(monkeypatch):
    """Even a thin best match: dropping it would leave nothing to write from."""
    docs = _anchor_with(monkeypatch, {"Some_Report.pdf": "A short note with none of those words."},
                        {"Some_Report.pdf": 0.9})
    assert [d["document"] for d in docs] == ["Some_Report.pdf"]


def test_a_second_document_that_shares_the_subject_is_kept(monkeypatch):
    docs = _anchor_with(monkeypatch, {
        "Novolen_Batch_QA_Report_Aug2026.pdf": "Novolen batch QA results for August 2026: H030SG, 22 batches.",
        "Novolen_Batch_QA_Annex.pdf": "Annex to the Novolen batch QA results for August 2026, off-spec detail.",
    }, {"Novolen_Batch_QA_Report_Aug2026.pdf": 0.9, "Novolen_Batch_QA_Annex.pdf": 0.8})
    assert len(docs) == 2


def test_the_writer_is_the_fast_model_whatever_the_source_size(monkeypatch):
    """Measured on this card: the 14b takes 588 s to plan and 206 s a section,
    scoring the same as the 7b on the corpus QA set."""
    monkeypatch.delenv("WORKBENCH_DECK_WRITER", raising=False)
    assert D.choose_writer([{"text": "x" * 40000}]) == D.WRITER_SMALL
    monkeypatch.setenv("WORKBENCH_DECK_WRITER", D.WRITER_LARGE)
    assert D.choose_writer([{"text": "x"}]) == D.WRITER_LARGE
