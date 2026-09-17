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
    prepare_deck,
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
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import call_tool

    prepared = prepare_deck(
        "Hydrocracker catalyst changeout and inspection findings",
        session_id="test_e2e_session",
        max_slides=3,
    )
    assert 1 <= len(prepared["slide_titles"]) <= 3
    assert prepared["defects"] == []
    assert prepared["citations"], "a grounded deck must name its sources"

    _store, chunks = get_state().ensure_corpus()
    corpus_docs = {c.metadata.source_document for c in chunks}
    for ref in prepared["citations"]:
        assert ref.split(" p.")[0] in corpus_docs, f"citation {ref!r} is not a document in the corpus"

    # The approved write renders exactly the prepared plan.
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "deck.pptx"
        result = call_tool(
            "generate_deck",
            {"deck_plan": prepared["deck_plan"], "output_path": str(out)},
            approved=True,
        )
        assert out.exists()
        assert result["slide_count"] == len(prepared["slide_titles"])
        assert len(Presentation(str(out)).slides) == result["slide_count"]


def test_slide_pipeline_refuses_a_topic_the_corpus_does_not_cover():
    """Before: a full, "grounded" deck on anything, from invented figures."""
    with pytest.raises(ValueError, match="No document in the corpus covers"):
        prepare_deck("The plot of Pride and Prejudice", session_id="test_refusal_session", max_slides=3)


def test_deck_slots_are_filled_and_no_template_sample_text_survives(tmp_path):
    """The template writes slots as {{key: sample}}. Only {{key}} was
    matched, so titles and bullets were never filled -- decks rendered as
    a logo and a footer -- and a table with fewer rows than the template
    kept the template's invented sample figures."""
    plan = {
        "slides": [
            {
                "mold_id": "title_bullets",
                "title": "CATALYST CHANGEOUT",
                "bullets": ["Beds purged with nitrogen before unloading.", "Oxygen held below 0.5 percent."],
                "citations": ["SOP-114-Rev3.docx p.2"],
            },
            {
                "mold_id": "table_data",
                "title": "INLET LIMITS",
                "headers": ["Tag", "Limit"],
                "rows": [["TC-201A", "400 C"]],
                "citations": ["SOP-114-Rev3.docx p.2"],
            },
        ]
    }
    out = tmp_path / "deck.pptx"
    build_deck(plan, out_path=str(out))

    prs = Presentation(str(out))
    all_text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                all_text.append(shape.text_frame.text)
            if getattr(shape, "has_table", False):
                all_text.extend(c.text for r in shape.table.rows for c in r.cells)
    text = "\n".join(all_text)

    assert "CATALYST CHANGEOUT" in text
    assert "Beds purged with nitrogen before unloading." in text
    assert "TC-201A" in text and "400 C" in text
    assert "{{" not in text
    # Sample text from MRPL_Template.pptx, which must never ship.
    for sample in ("Q3 FY26", "15.2 MMTPA", "Crude throughput", "EXECUTIVE BRIEFING", "DATA SUMMARY"):
        assert sample not in text, f"template sample text {sample!r} leaked into the deck"


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


def test_presentations_go_through_the_approval_gate():
    """Hard constraint #4: no file write without approval. Decks were
    exempted as "safe deliverables"; a .pptx carrying refinery figures
    that leaves the building is exactly what the gate is for."""
    assert is_action_approval_request("Generate a presentation on crude distillation unit limits") is True
    assert is_action_approval_request("Create a slide deck for hydrocracker operations") is True
    assert is_action_approval_request("Make a pptx for board meeting") is True
    # Questions about a deck are reads, not writes.
    assert is_action_approval_request("What does the board presentation say about CCR-1?") is False


def test_generate_deck_refuses_to_write_without_approval(tmp_path):
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import ApprovalRequired, call_tool

    out = tmp_path / "deck.pptx"
    plan = {"slides": [{"mold_id": "title_bullets", "title": "X", "bullets": ["A sourced line."]}]}
    with pytest.raises(ApprovalRequired):
        call_tool("generate_deck", {"deck_plan": plan, "output_path": str(out)})
    assert not out.exists()


def test_refinery_equipment_named_deck_or_slide_is_not_a_presentation():
    """"Tray deck" and "slide valve" are equipment. The planner used to send
    any request containing "deck" or "slide" to the slide agent."""
    from backend.orchestrator.action_resolver import is_deck_request

    assert not is_deck_request("Write a report on the slide valve inspection")
    assert not is_deck_request("Draft a note on tray deck corrosion in the CDU")
    assert is_deck_request("Create a presentation on slide valve inspection findings")
    assert is_deck_request("Make a PowerPoint on CCR-1 regeneration")
