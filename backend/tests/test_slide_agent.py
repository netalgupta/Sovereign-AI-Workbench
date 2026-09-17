"""Tests for sovereign PPTX presentation generator (slide_agent, slide_kit, qa_render).

Verifies:
- slide_kit.py XML template cloning, placeholder replacement, and deck building.
- qa_render.py heuristic defect detection and rule checking.
- slide_agent.py planning, retrieval, filling, rendering, and bounded retry.
- orchestrator integration and safe deliverable approval gate exemption.
"""

from pathlib import Path
import tempfile
import pytest
from pptx import Presentation

from backend.tools.generation.slide_kit import (
    build_deck,
    resolve_template_path,
    MOLD_INDEX,
    ExecutiveSummarySlide,
    StatCalloutSlide,
    TitleBulletsSlide,
    TableDataSlide,
    RiskMatrixSlide,
)
from backend.tools.generation.qa_render import run_heuristic_qa
from backend.orchestrator.slide_agent import (
    plan_deck_outline,
    fetch_section_content,
    fill_slide_content,
    run_slide_pipeline,
    MAX_RETRIES,
)
from backend.orchestrator.graph import classify_action_request, is_action_approval_request


def test_template_exists():
    """Verify master MRPL template is present on disk and has 19 slides."""
    tmpl_path = resolve_template_path()
    assert Path(tmpl_path).exists(), f"Master template not found at {tmpl_path}"
    prs = Presentation(str(tmpl_path))
    assert len(prs.slides) == 19, f"Expected 19 template slides, found {len(prs.slides)}"


def test_slide_schemas():
    """Verify pydantic models validate structure properly."""
    stat = StatCalloutSlide(
        mold_id="stat_callout",
        title="Plant Throughput",
        big_number="15.0 MMTPA",
        label="Crude Processing Capacity",
        supporting_narrative="Operated at steady capacity.",
        source_citation="[MRPL-AR-2024 p.12]",
    )
    assert stat.mold_id == "stat_callout"
    assert stat.big_number == "15.0 MMTPA"

    bullets = TitleBulletsSlide(
        mold_id="title_bullets",
        title="Key Findings",
        bullets=["Primary fractionator column operational", "Desalter pressure in range"],
        citation_keys=["DOC-1"],
    )
    assert len(bullets.bullets) == 2


def test_build_deck_creates_valid_presentation():
    """Verify build_deck clones master slides, substitutes placeholders, and updates footers."""
    plan = {
        "deck_title": "Test Briefing Deck",
        "slides": [
            {
                "mold_id": "executive_summary",
                "title": "Executive Summary",
                "subtitle": "High Level Plant Status",
                "bullet_1": "Crude unit stable at 100% capacity",
                "bullet_2": "Sulphur recovery unit within emission limits",
                "bullet_3": "Hydrocracker revamp completed on time",
                "footnote": "Confidential // MRPL Technical Review",
            },
            {
                "mold_id": "stat_callout",
                "title": "Refining Capacity",
                "big_number": "16.2 MMTPA",
                "stat_label": "Annual Design Capacity",
                "supporting_narrative": "Refinery operating at full throughput.",
                "source_citation": "Source: MRPL Annual Report 2024",
            },
            {
                "mold_id": "table_data",
                "title": "Key Sensor Telemetry",
                "headers": ["Unit", "Parameter", "Value", "Status"],
                "rows": [
                    ["CDU-1", "Tower Top Temp", "112 °C", "Normal"],
                    ["VDU-2", "Vacuum Pressure", "38 mmHg", "Normal"],
                    ["HCU", "Reactor Temp", "395 °C", "Nominal"],
                ],
                "caption": "Sensor snapshot from DCS logger",
            },
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "output_test_deck.pptx"
        build_deck(plan, out_path=out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 15000, "Deck should be a non-trivial PPTX file"

        prs = Presentation(str(out_path))
        # Expected exact number of slides as in the plan
        assert len(prs.slides) == 3

        # Check that slide 1 contains executive summary text
        slide1_text = " ".join([shape.text for shape in prs.slides[0].shapes if shape.has_text_frame])
        assert "Crude unit stable" in slide1_text

        # Check that slide 2 contains stat callout
        slide2_text = " ".join([shape.text for shape in prs.slides[1].shapes if shape.has_text_frame])
        assert "16.2 MMTPA" in slide2_text

        # Verify QA passes on cleanly generated deck
        defects = run_heuristic_qa(out_path, plan)
        assert defects == [], f"Clean deck should have 0 defects, got: {defects}"


def test_heuristic_qa_defect_detection():
    """Verify run_heuristic_qa detects unreplaced tags and text overflows."""
    dirty_prs = Presentation()
    slide = dirty_prs.slides.add_slide(dirty_prs.slide_layouts[0])
    tx_box = slide.shapes.add_textbox(0, 0, 1000, 1000)
    tf = tx_box.text_frame
    tf.text = "Here is an unreplaced {{missing_placeholder}} in text."

    # Add an overflowing paragraph (>400 chars)
    p2 = tf.add_paragraph()
    p2.text = "A" * 450

    with tempfile.TemporaryDirectory() as tmpdir:
        dirty_path = Path(tmpdir) / "dirty_deck.pptx"
        dirty_prs.save(str(dirty_path))

        defects = run_heuristic_qa(dirty_path)
        defect_types = {d["type"] for d in defects}

        assert "UNREPLACED_PLACEHOLDER" in defect_types
        assert "TEXT_OVERFLOW" in defect_types


def test_plan_deck_outline():
    """Verify plan_deck_outline returns structured sections."""
    sections = plan_deck_outline("Crude Distillation Unit operating temperature limits")
    assert isinstance(sections, list)
    assert len(sections) >= 3
    for s in sections:
        assert "section_title" in s
        assert "provisional_mold" in s
        assert "content_need" in s


def test_fetch_and_fill_slide():
    """Verify deterministic retrieval bundle and slide filler."""
    section = {
        "section_title": "Hydrocracker Operating Parameters",
        "provisional_mold": "stat_callout",
        "content_need": "operating temperature and pressure limits",
    }
    bundle = fetch_section_content(section, "Hydrocracker limits")
    assert "section_title" in bundle
    assert "citations" in bundle

    slide_data = fill_slide_content(bundle)
    assert "mold_id" in slide_data
    assert "title" in slide_data


def test_slide_pipeline_end_to_end():
    """A deck on a topic the corpus covers: rendered, and every citation
    names a real document.

    This asserted `len(citations) > 0` and passed on any request --
    because the fallback cited a sentence the code wrote itself.
    Citations are now checked against the corpus.
    """
    from backend.api.state import get_state

    result = run_slide_pipeline(
        request="Hydrocracker catalyst changeout and inspection findings",
        session_id="test_e2e_session",
        max_slides=3,
    )

    assert Path(result["deck_path"]).exists()
    assert 1 <= result["slide_count"] <= 3
    assert result["defects"] == []
    assert result["citations"], "a grounded deck must name its sources"

    _store, chunks = get_state().ensure_corpus()
    corpus_docs = {c.metadata.source_document for c in chunks}
    for ref in result["citations"]:
        doc = ref.split(" p.")[0]
        assert doc in corpus_docs, f"citation {ref!r} is not a document in the corpus"


def test_slide_pipeline_refuses_a_topic_the_corpus_does_not_cover():
    """Before: a full, "grounded" deck on anything, from invented figures."""
    with pytest.raises(ValueError, match="No document in the corpus covers"):
        run_slide_pipeline(
            request="The plot of Pride and Prejudice",
            session_id="test_refusal_session",
            max_slides=3,
        )


def _bundle(snippet: str) -> dict:
    return {
        "section_title": "HYDROCRACKER LIMITS",
        "provisional_mold": "stat_callout",
        "text_snippets": [snippet],
        "citations": ["SOP-114-Rev3.docx p.2"],
        "grounded": True,
    }


def test_model_slide_with_a_number_no_source_contains_is_rejected():
    from backend.orchestrator.slide_agent import _validated_slide

    bundle = _bundle("Reactor inlet temperature must not exceed 400 °C during changeout.")
    invented = {"mold_id": "stat_callout", "big_number": "1,450 m³/h", "label": "Design flow"}
    sourced = {"mold_id": "stat_callout", "big_number": "400 °C", "label": "Inlet limit"}

    assert _validated_slide(invented, bundle) is None
    assert _validated_slide(sourced, bundle)["big_number"] == "400 °C"


def test_table_rows_returned_as_objects_are_normalised_to_lists():
    """The model returned rows keyed by header; rendering crashed KeyError: 0."""
    from backend.orchestrator.slide_agent import _validated_slide

    bundle = _bundle("TC-201A read 381 °C against a 400 °C limit.")
    data = {
        "mold_id": "table_data",
        "headers": ["Tag", "Reading", "Limit"],
        "rows": [{"Tag": "TC-201A", "Reading": "381 °C", "Limit": "400 °C"}],
    }
    slide = _validated_slide(data, bundle)
    assert slide["rows"] == [["TC-201A", "381 °C", "400 °C"]]


def test_fallback_slide_contains_only_source_sentences():
    from backend.orchestrator.slide_agent import _build_fallback_slide

    snippet = "Catalyst beds are purged with nitrogen before unloading. Oxygen must stay below 0.5 percent."
    slide = _build_fallback_slide(_bundle(snippet), "multi_stat_row", ["SOP-114-Rev3.docx p.2"])

    assert slide["mold_id"] == "title_bullets"
    assert slide["bullets"]
    for bullet in slide["bullets"]:
        assert bullet in snippet
    assert slide["citations"] == ["SOP-114-Rev3.docx p.2"]


def test_unretrieved_section_is_ungrounded_not_given_a_citation(monkeypatch):
    """This used to cite a sentence the function had just written."""
    import backend.retrieval.grounded_retrieval as gr

    class _Nothing:
        found = False
        chunks = []

    class _State:
        def ensure_corpus(self):
            return object(), []

    monkeypatch.setattr(gr, "retrieve_with_grounding_check", lambda *a, **k: _Nothing())
    bundle = fetch_section_content({"section_title": "X"}, "anything", _State())

    assert bundle["grounded"] is False
    assert bundle["text_snippets"] == []
    assert bundle["citations"] == []


def test_presentation_safe_deliverable_exemption():
    """Verify presentations are exempt from the hazardous action interlock."""
    # File writes or commands that should be gated:
    assert is_action_approval_request("write this report to disk") is True
    assert is_action_approval_request("save document to file") is True

    # Presentations should be safe deliverables exempt from the gate:
    assert classify_action_request("Generate a presentation on crude distillation unit limits") is None
    assert is_action_approval_request("Generate a presentation on crude distillation unit limits") is False
    assert is_action_approval_request("Create a slide deck for hydrocracker operations") is False
    assert is_action_approval_request("Make a pptx for board meeting") is False
