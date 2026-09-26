"""Presentation generation around the approval gate.

The design system and the content engine have their own file
(test_deck.py). This one covers the two phases either side of the gate:
what the operator is asked to approve, and what the approved call does.

The end-to-end test that really calls the model is live_model-marked,
because it takes minutes and is the only one that catches a prompt the
model has silently stopped answering in the shape we parse.
"""

from __future__ import annotations


import pytest
from pptx import Presentation

from backend.orchestrator.action_resolver import is_deck_request
from backend.orchestrator.graph import is_action_approval_request
from backend.orchestrator.slide_agent import generate_deck, prepare_deck

@pytest.fixture(autouse=True)
def _outputs_in_tmp(tmp_path, monkeypatch):
    """Approved writes may only land in OUTPUT_DIR (backend/paths.py); here that is the test's tmp dir."""
    import backend.paths

    monkeypatch.setattr(backend.paths, "OUTPUT_DIR", tmp_path)



SPEC = {
    "title": "CCR-1 regeneration cycle 18 ran six hours long",
    "subtitle": "Findings and actions",
    "sources": [{"id": "S1", "document": "Inspection_Report_CCR1.pdf", "pages": [1], "used_for": "durations"}],
    "sections": [{
        "title": "What happened",
        "summary": "Cycle 18 ran long",
        "slides": [{"type": "points", "title": "Cycle 18 ran 34 hours against a 28-hour target",
                    "bullets": ["Cycle 18 took 34 hours.", "The target is 28 hours."], "sources": ["S1"]}],
    }],
}


# ── the gate ────────────────────────────────────────────────────────────────


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
    from backend.tools import catalog  # noqa: F401 - registers the tools
    from backend.tools.registry import ApprovalRequired, call_tool

    out = tmp_path / "deck.pptx"
    with pytest.raises(ApprovalRequired):
        call_tool("generate_deck", {"deck_spec": SPEC, "output_path": str(out)})
    assert not out.exists()


def test_refinery_equipment_named_deck_or_slide_is_not_a_presentation():
    """"Tray deck" and "slide valve" are equipment. The planner used to
    route any request containing "deck" or "slide" to the slide agent."""
    assert not is_deck_request("Write a report on the slide valve inspection")
    assert not is_deck_request("Draft a note on tray deck corrosion in the CDU")
    assert is_deck_request("Create a presentation on slide valve inspection findings")
    assert is_deck_request("Make a PowerPoint on CCR-1 regeneration")


# ── the approved write ──────────────────────────────────────────────────────


def test_an_approved_spec_renders_exactly_that_deck(tmp_path):
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import call_tool

    out = tmp_path / "deck.pptx"
    result = call_tool("generate_deck", {"deck_spec": SPEC, "output_path": str(out)}, approved=True)

    assert out.exists()
    assert result["slide_count"] == len(Presentation(str(out)).slides)
    assert result["file_size"].endswith("KB")
    assert result["citations"] == ["Inspection_Report_CCR1.pdf"]


def test_generate_deck_rejects_an_empty_spec_and_a_wrong_extension(tmp_path):
    with pytest.raises(ValueError, match="no slides"):
        generate_deck({"sections": []}, str(tmp_path / "deck.pptx"))
    with pytest.raises(ValueError, match=r"\.pptx"):
        generate_deck(SPEC, str(tmp_path / "deck.docx"))


def test_prepare_deck_refuses_a_topic_the_corpus_does_not_cover(monkeypatch):
    """Before, invented figures meant every request produced a deck."""
    import backend.orchestrator.deck_agent as D

    monkeypatch.setattr(D, "anchor_documents",
                        lambda *a, **k: (_ for _ in ()).throw(D.NotInCorpus("No document in the corpus covers this.")))
    with pytest.raises(D.NotInCorpus):
        prepare_deck("The plot of Pride and Prejudice")


def test_deck_length_is_not_capped(monkeypatch):
    """max_slides is accepted and ignored: capping padded thin decks and
    dropped findings from rich ones."""
    import backend.orchestrator.slide_agent as S

    captured = {}

    def fake_build(request, store, chunks, **kw):
        captured["kw"] = kw
        return {"deck_spec": SPEC, "slide_titles": ["a", "b", "c", "d", "e", "f", "g"],
                "documents": ["Inspection_Report_CCR1.pdf"], "dropped_slides": []}

    monkeypatch.setattr(S, "build_deck_spec", fake_build)
    prepared = S.prepare_deck("CCR-1 findings", max_slides=2)

    assert len(prepared["slide_titles"]) == 7
    assert "max_slides" not in captured["kw"]


# ── the real thing ──────────────────────────────────────────────────────────


@pytest.mark.live_model
def test_prepare_and_generate_a_real_deck_from_the_corpus(tmp_path):
    """Calls the model. Catches what no stub can: a prompt the model has
    stopped answering in the shape the validator accepts."""
    from backend.api.state import get_state

    prepared = prepare_deck("Make a presentation on the CCR-1 regeneration cycle inspection findings")
    assert prepared["slide_titles"], "no slide survived validation"
    assert prepared["citations"]

    _store, chunks = get_state().ensure_corpus()
    corpus_docs = {c.metadata.source_document for c in chunks}
    for doc in prepared["citations"]:
        assert doc in corpus_docs, f"{doc!r} is not a document in the corpus"

    out = tmp_path / "real.pptx"
    result = generate_deck(prepared["deck_spec"], str(out))
    assert out.exists() and result["slide_count"] >= 3
