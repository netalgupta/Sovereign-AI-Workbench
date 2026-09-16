"""The archive corpus generator's deterministic parts.

NOT TESTED HERE: narrative_docs.generate_batch() actually calling a
model -- that is real Ollama work, live_model-marked territory, and
this suite already has the generation script itself as its own proof
(it ran, it produced readable DOCX/PDF content, it was checked by hand
against docx.Document() and text_extraction.extract_pages()). What is
tested here is everything that must be right BEFORE a single model call
happens: the plans a bad plan wastes real LLM minutes discovering.
"""

from __future__ import annotations

from pathlib import Path

from backend.evaluation.archive_corpus import bulk_tables, diagrams, narrative_docs, vocab


# ---------------------------------------------------------------------
# vocab: the shared entity set every generator draws from
# ---------------------------------------------------------------------


def test_vocab_has_no_duplicate_equipment_or_unit_tags():
    """A tag that appears twice under different spellings is two graph
    nodes for one thing, which is the exact failure this vocabulary
    exists to prevent."""
    assert len(vocab.UNITS) == len(set(vocab.UNITS))
    assert len(vocab.EQUIPMENT) == len(set(vocab.EQUIPMENT))
    assert len(vocab.DEPOTS) == len(set(vocab.DEPOTS))


def test_vocab_reuses_tags_already_present_elsewhere_in_this_repo():
    """The whole point is cross-document connectivity: these specific
    strings are asserted BY NAME in test_ocr_printed.py and appear in
    the existing MRPL_RAG_Test_Corpus. A generator free to invent its
    own tags would not connect to any of that."""
    assert "F-140-A" in vocab.EQUIPMENT
    assert "CCR-1" in vocab.UNITS
    assert "TK-K-01" in vocab.EQUIPMENT
    assert set(vocab.DEPOTS) == {"Kasargod", "Hindupur", "Hosur"}


def test_rng_for_is_reproducible():
    a = vocab.rng_for("same-key")
    b = vocab.rng_for("same-key")
    assert a.random() == b.random()


# ---------------------------------------------------------------------
# bulk_tables: no model calls, must be fast and correctly shaped
# ---------------------------------------------------------------------


def test_process_readings_covers_every_unit_and_the_full_date_span(tmp_path):
    from datetime import date

    stats = bulk_tables.generate_process_readings_log(
        tmp_path / "readings.xlsx", start=date(2024, 1, 1), end=date(2024, 1, 31)
    )
    assert set(stats) == set(vocab.UNITS)
    for unit_stats in stats.values():
        assert unit_stats["rows"] == 31


def test_process_readings_file_is_actually_readable(tmp_path):
    """Generated, not just claimed generated -- open it back up."""
    from datetime import date

    from openpyxl import load_workbook

    path = tmp_path / "readings.xlsx"
    bulk_tables.generate_process_readings_log(path, start=date(2024, 1, 1), end=date(2024, 1, 10))
    wb = load_workbook(str(path))
    assert set(wb.sheetnames) <= {u[:31] for u in vocab.UNITS}
    ws = wb[vocab.UNITS[0][:31]]
    assert ws.cell(row=1, column=1).value == "Date"
    assert ws.max_row == 11  # header + 10 days


def test_sap_material_master_line_items_reference_real_equipment(tmp_path):
    from openpyxl import load_workbook

    path = tmp_path / "sap.xlsx"
    bulk_tables.generate_sap_material_master(path, n_items=50)
    wb = load_workbook(str(path))
    ws = wb.active
    equip_col = [ws.cell(row=r, column=11).value for r in range(2, 12)]
    assert all(e in vocab.EQUIPMENT for e in equip_col)


def test_work_orders_have_consistent_status_and_dates(tmp_path):
    from datetime import date

    from openpyxl import load_workbook

    path = tmp_path / "wo.xlsx"
    bulk_tables.generate_maintenance_work_orders(path, n_orders=100)
    wb = load_workbook(str(path))
    ws = wb.active
    for r in range(2, 102):
        status = ws.cell(row=r, column=5).value
        closed = ws.cell(row=r, column=7).value
        if status == "Closed":
            assert closed, f"row {r} is Closed with no Closed Date"
        created = date.fromisoformat(ws.cell(row=r, column=6).value)
        assert date(2020, 1, 1) <= created <= date(2026, 9, 14)


# ---------------------------------------------------------------------
# narrative_docs: plans and formatting, no model calls
# ---------------------------------------------------------------------


def test_every_planner_produces_the_requested_count_up_to_its_ceiling():
    """sop/inspection/incident have year x unit = 77 combinations to
    draw from; correspondence and board_review are smaller and must
    cycle rather than silently under-produce."""
    assert len(narrative_docs.plan_sops(40)) == 40
    assert len(narrative_docs.plan_inspection_reports(50)) == 50
    assert len(narrative_docs.plan_incident_reports(40)) == 40
    assert len(narrative_docs.plan_correspondence(40)) == 40
    assert len(narrative_docs.plan_board_reviews(28)) == 28  # exactly 7 years x 4 quarters


def test_growing_a_plan_never_changes_an_earlier_doc_id():
    """The property that makes a later, larger run additive rather than
    a full regeneration: everything already in the manifest must still
    match by id."""
    for plan_fn, small, big in [
        (narrative_docs.plan_sops, 10, 40),
        (narrative_docs.plan_inspection_reports, 15, 50),
        (narrative_docs.plan_correspondence, 21, 40),
        (narrative_docs.plan_board_reviews, 10, 28),
    ]:
        small_ids = {s.doc_id for s in plan_fn(small)}
        big_ids = {s.doc_id for s in plan_fn(big)}
        assert small_ids.issubset(big_ids), plan_fn.__name__


def test_every_planned_filename_is_unique_and_ingestible():
    from backend.ingestion.document_types import _EXTENSION_TO_TYPE

    all_specs = (
        narrative_docs.plan_sops(20)
        + narrative_docs.plan_inspection_reports(20)
        + narrative_docs.plan_incident_reports(20)
        + narrative_docs.plan_correspondence(20)
        + narrative_docs.plan_board_reviews(20)
    )
    paths = [f"{s.subfolder}/{s.filename}" for s in all_specs]
    assert len(paths) == len(set(paths)), "two specs would write the same file"
    for spec in all_specs:
        ext = Path(spec.filename).suffix
        assert ext in _EXTENSION_TO_TYPE, f"{spec.filename} has an unsupported extension"


def test_split_bold_extracts_markdown_and_the_model_cannot_be_trusted_not_to_emit_it():
    """Asked for 'no markdown', the model uses **bold** anyway -- every
    model tested does. Literal asterisk pairs must not survive into the
    written document."""
    parts = narrative_docs._split_bold("**Scope and Purpose**")
    assert parts == [("Scope and Purpose", True)]

    parts = narrative_docs._split_bold("Normal text with **one bold word** in it.")
    texts = [t for t, _ in parts]
    bolds = [b for _, b in parts]
    assert "one bold word" in texts
    assert any(bolds)
    assert "".join(texts) == "Normal text with one bold word in it."


def test_split_bold_leaves_plain_text_alone():
    assert narrative_docs._split_bold("Plain sentence, nothing special.") == [
        ("Plain sentence, nothing special.", False)
    ]


def test_docx_writer_produces_bold_runs_not_literal_asterisks(tmp_path):
    import docx

    spec = narrative_docs.DocSpec("sop", "x", 2024, "Hydrocracker-1", "01", "t.docx")
    out = tmp_path / "t.docx"
    narrative_docs._write_docx("**Scope**\nThis is the body text.", spec, out)

    doc = docx.Document(str(out))
    body_text = "\n".join(p.text for p in doc.paragraphs)
    assert "**" not in body_text
    assert "Scope" in body_text


# ---------------------------------------------------------------------
# diagrams: images that must actually be OCR-legible, not just present
# ---------------------------------------------------------------------


def test_diagram_batch_alternates_pid_and_scanned_styles(tmp_path):
    result = diagrams.generate_batch(4, tmp_path)
    assert result["generated"] == 4
    files = sorted(tmp_path.glob("*.png"))
    assert len(files) == 4
    assert any("PID_Schematic" in f.name for f in files)
    assert any("Scanned_Inspection_Checklist" in f.name for f in files)


def test_scanned_checklist_is_actually_degraded_not_a_clean_render(tmp_path):
    """A crisp render tests nothing about OCR robustness that the
    existing printed-OCR test does not already cover. This asserts the
    degradation happened -- rotation and noise -- not just that a file
    exists."""
    import numpy as np
    from PIL import Image

    diagrams._scanned_checklist_style("CCR-1", 2023, cycle=3, out_path=tmp_path / "scan.png")
    img = np.array(Image.open(tmp_path / "scan.png").convert("L")).astype(float)

    # A perfectly clean vector render is near-binary (mostly pure black
    # or pure white) -- MEASURED at 0.0016 for an undegraded matplotlib
    # text render. Real degradation pushes real pixel mass into the
    # midtones: measured 0.0064-0.0125 across five different seeds of
    # this exact function. 0.005 sits above the clean baseline with
    # margin and below every degraded sample measured, so it discriminates
    # "was this actually blurred and noised" rather than "does this page
    # have any grey pixel at all."
    midtone_fraction = float(((img > 40) & (img < 215)).mean())
    assert midtone_fraction > 0.005, "the 'scanned' image looks like a clean render"
