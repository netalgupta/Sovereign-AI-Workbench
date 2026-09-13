"""TOOLS.md row 9 — the KIND of document, and the pipeline it implies.

Ground truth is MRPL_RAG_Test_Corpus's own folder names, which were
written before this classifier existed and therefore cannot have been
fitted to it.
"""

import pytest

from backend.ingestion.document_classifier import (
    PIPELINES,
    classify_document,
)


def test_format_and_kind_are_different_questions():
    """A P&ID and a scanned checklist are both PNGs and need opposite
    handling: one is a diagram whose value is the connections between
    tags, the other a table whose rows are findings. document_types.py
    cannot separate them, which is why this exists."""
    diagram = classify_document("", "Hydrocracker_PID_Schematic.png")
    form = classify_document("", "Scanned_Inspection_Checklist_CCR1.png")

    assert diagram.kind == "diagram_schematic"
    assert form.kind == "scanned_form"
    assert diagram.pipeline != form.pipeline
    assert "graph" in diagram.pipeline
    assert "table" in form.pipeline


def test_an_unocrd_image_is_classified_from_its_name_and_says_so():
    """The filename is not weak evidence here, it is the ONLY evidence,
    and the routing decision still has to be made. Saying where the
    answer came from is what keeps that honest."""
    result = classify_document("", "Pipeline_Segment_Map_Mangalore_Hassan.png")

    assert result.kind == "diagram_schematic"
    assert any("filename alone" in e for e in result.evidence)
    # Capped: it is a guess from a name, and must not read like a
    # reading of the document.
    assert result.confidence <= 0.4
    assert not result.is_confident


def test_unknown_is_a_real_answer():
    """Forcing a guess is how a P&ID ends up parsed as a spreadsheet:
    the system was never in doubt, so nothing downstream knew to be
    careful."""
    result = classify_document("The quick brown fox jumps over the lazy dog.", "notes.txt")
    assert result.kind == "unknown"
    assert result.pipeline == PIPELINES["unknown"]
    assert result.confidence == 0.0


def test_every_classification_names_the_evidence():
    """An unexplainable classification cannot be corrected by the person
    it is wrong for."""
    result = classify_document(
        "SOP-114 Rev 3 — Standard Operating Procedure for catalyst changeout. "
        "Step 1: isolate the reactor. Precautions apply.",
        "SOP-114-Rev3.docx",
    )
    assert result.kind == "sop_procedure"
    assert result.evidence, "no evidence recorded"
    assert any("SOP" in e.upper() for e in result.evidence)


def test_repeated_evidence_outweighs_a_single_mention():
    """MEASURED on PSA_Hydrogen_Purity_Trend_Log.xlsx: a purity trend
    table followed by a small downtime-cause table matched "purity" and
    "downtime" once each under binary scoring, tied, and came out
    UNKNOWN. "Purity (%)" is five column headers; "Downtime" is one row
    label."""
    text = (
        "PSA Hydrogen Purity Trend Log\n"
        "Week Ending\tPSA-1 Purity (%)\tPSA-2 Purity (%)\tPSA-3 Purity (%)\tTarget (%)\n"
        "2026-06-07\t99.914\t99.803\t99.853\t99.9\n"
        "PSA Downtime Cause\tHours\n"
    )
    result = classify_document(text, "PSA_Hydrogen_Purity_Trend_Log.xlsx")
    assert result.kind == "lab_quality_data", result.evidence


def test_confidence_is_a_margin_not_a_probability():
    """A document matching two classes almost equally is genuinely
    ambiguous, and saying so is more useful than a decisive-looking
    number."""
    clear = classify_document(
        "Correspondence thread. Thread ID: CORR-K-001. From: depot To: HQ. "
        "Subject: calibration. Regards.",
        "thread.docx",
    )
    assert clear.kind == "correspondence"
    assert 0.0 <= clear.confidence <= 1.0


# ---------------------------------------------------------------------
# The measured claim in TOOLS.md row 9.
# ---------------------------------------------------------------------


def test_classifier_accuracy_against_the_corpus_folder_labels():
    """13/13 when this was written. The folders are the labels."""
    from pathlib import Path

    from backend.evaluation.classifier_accuracy import CORPUS, FOLDER_TO_KIND, _text_of

    if not Path(CORPUS).exists():
        pytest.skip(f"corpus not present at {CORPUS}")

    total = correct = 0
    wrong = []
    for folder, expected in FOLDER_TO_KIND.items():
        directory = Path(CORPUS) / folder
        if not directory.exists():
            continue
        allowed = expected if isinstance(expected, set) else {expected}
        for path in sorted(directory.iterdir()):
            if path.is_dir() or path.name.startswith("."):
                continue
            result = classify_document(_text_of(path), path.name)
            total += 1
            if result.kind in allowed:
                correct += 1
            else:
                wrong.append(f"{path.name}: got {result.kind}, wanted {allowed}")

    assert total, "no corpus files were classified"
    # Held at the measured figure. A drop means a signal changed
    # behaviour, which is worth failing over rather than discovering in
    # a demo.
    assert correct == total, f"{correct}/{total}; misses: {wrong}"


def test_the_tool_is_reachable_through_the_registry():
    """CLAUDE.md: a tool the orchestrator cannot reach is not a tool."""
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import all_tools

    registry = all_tools()
    names = set(registry) if isinstance(registry, dict) else {t.name for t in registry}
    assert "classify_document" in names
