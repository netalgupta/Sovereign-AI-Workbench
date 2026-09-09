"""Tests for extract_pages.

test_mixed_pdf_only_ocrs_the_blank_page is the important one here: it's
a regression test for a real bug (not hypothetical) — an earlier version
of this function checked "does ANY page have text?" and, if so, silently
returned every page as-is, including blank ones. That would have been
silent data loss on exactly the kind of mixed document (printed cover
page + scanned signature page) real refinery correspondence produces.
"""

import os

import pytest

from backend.ingestion.text_extraction import extract_pages

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _path(name: str) -> str:
    return os.path.join(FIXTURES, name)


def test_native_pdf_extracts_both_pages_with_correct_page_numbers():
    pages = extract_pages(_path("sample_native.pdf"), "pdf")

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert "hydrocracker catalyst deactivation" in pages[0].text
    assert pages[1].page_number == 2
    assert "Mangalore-Hassan" in pages[1].text


def test_fully_scanned_pdf_without_ocr_fn_raises_naming_the_blank_page():
    with pytest.raises(NotImplementedError) as exc_info:
        extract_pages(_path("sample_scanned_no_text.pdf"), "pdf")

    assert "page(s) [1]" in str(exc_info.value)


def test_mixed_pdf_only_ocrs_the_blank_page():
    """The regression test — see module docstring."""
    ocr_calls: list[str] = []

    def fake_ocr(image_path: str) -> str:
        ocr_calls.append(image_path)
        return "OCR'd: hand-signed approval page"

    pages = extract_pages(_path("sample_mixed_pdf.pdf"), "pdf", ocr_fn=fake_ocr)

    assert len(pages) == 2
    # Page 1 had real extractable text — must be untouched, OCR must
    # NEVER have been called for it.
    assert "Cover letter" in pages[0].text
    # Page 2 had no text layer — must have gone through OCR.
    assert pages[1].text == "OCR'd: hand-signed approval page"
    assert len(ocr_calls) == 1  # exactly one page needed OCR, not both


def test_mixed_pdf_without_ocr_fn_raises_naming_only_the_actually_blank_page():
    with pytest.raises(NotImplementedError) as exc_info:
        extract_pages(_path("sample_mixed_pdf.pdf"), "pdf")

    # Must name page 2 specifically, not "the whole document" — page 1
    # is fine and doesn't need OCR at all.
    assert "page(s) [2]" in str(exc_info.value)


def test_pdf_with_embedded_image_calls_chart_image_fn_when_provided():
    """sample_native.pdf has no embedded images, so this needs a fixture
    that does -- reuse the corpus's real inspection-report PDF, which
    has both real text AND an embedded chart image on page 1, exactly
    the "additive, not a replacement" case chart_image_fn exists for.
    """
    corpus_pdf = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "MRPL_RAG_Test_Corpus", "02_Inspection_and_Maintenance",
        "Inspection_Report_CCR1_Regeneration_Cycle.pdf",
    )
    if not os.path.exists(corpus_pdf):
        pytest.skip("test corpus not present")

    calls = []

    def fake_chart_fn(image_path: str) -> str:
        calls.append(image_path)
        return "[Chart: fake description]"

    pages = extract_pages(corpus_pdf, "pdf", chart_image_fn=fake_chart_fn)

    assert len(calls) == 1  # exactly the one page with an embedded image
    # Additive: the page's real extracted text must still be there too.
    assert "[Chart: fake description]" in pages[0].text
    assert len(pages[0].text) > len("[Chart: fake description]")  # real text wasn't replaced


def test_pdf_without_chart_image_fn_extracts_normally():
    """No chart_image_fn passed -- must behave exactly as before this
    seam existed, not raise or change behavior for callers that don't
    care about chart images."""
    pages = extract_pages(_path("sample_native.pdf"), "pdf")

    assert len(pages) == 2
    assert "hydrocracker catalyst deactivation" in pages[0].text


def test_docx_extraction_includes_paragraph_and_table_text():
    pages = extract_pages(_path("sample_doc.docx"), "docx")

    assert len(pages) == 1
    assert pages[0].page_number is None
    assert "Valve V-204" in pages[0].text
    assert "Field" in pages[0].text  # from the table


def test_docx_extraction_preserves_document_order_of_tables_and_paragraphs(tmp_path):
    """Regression test for a real bug found on a real fixture (the
    corpus's SOP-114 document): python-docx's .paragraphs and .tables
    are two separate flat lists with no positional relationship to each
    other. An earlier version of _extract_docx did all paragraphs, then
    all tables -- which put a paragraph introducing a table nowhere
    near that table's actual data, and put a SECOND table's data
    immediately after the first table's data instead of after ITS OWN
    introducing paragraph. This builds a document with two
    paragraph-then-table pairs and asserts each table's data lands
    right after its own paragraph, not grouped with the other table's.
    """
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("Intro to table Alpha:")
    table_a = doc.add_table(rows=1, cols=1)
    table_a.rows[0].cells[0].text = "AlphaValue"
    doc.add_paragraph("Intro to table Beta:")
    table_b = doc.add_table(rows=1, cols=1)
    table_b.rows[0].cells[0].text = "BetaValue"

    docx_path = tmp_path / "ordering_test.docx"
    doc.save(str(docx_path))

    pages = extract_pages(str(docx_path), "docx")
    text = pages[0].text

    # "AlphaValue" must come after "Alpha" and before "Beta" (its own
    # intro, not the other table's) -- the old bug would have put both
    # tables' data back-to-back, after both paragraphs.
    alpha_intro_pos = text.index("Intro to table Alpha")
    alpha_value_pos = text.index("AlphaValue")
    beta_intro_pos = text.index("Intro to table Beta")
    beta_value_pos = text.index("BetaValue")

    assert alpha_intro_pos < alpha_value_pos < beta_intro_pos < beta_value_pos


def test_txt_extraction():
    pages = extract_pages(_path("sample_note.txt"), "txt")

    assert len(pages) == 1
    assert pages[0].page_number is None
    assert "catalyst bed temperature" in pages[0].text


def test_csv_extraction_is_readable_as_text():
    pages = extract_pages(_path("sample_lab_results.csv"), "csv")

    assert len(pages) == 1
    assert "sulphur_ppm" in pages[0].text


def test_eml_extraction_gets_the_plain_text_body():
    pages = extract_pages(_path("sample_email.eml"), "email")

    assert len(pages) == 1
    assert "Kasargod depot" in pages[0].text


def test_xlsx_extraction_treats_each_sheet_as_a_numbered_page():
    pages = extract_pages(_path("sample_spec_sheet.xlsx"), "xlsx")

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "QA_Results" in pages[0].text
    assert "sulphur_ppm" in pages[0].text
    assert "7.9" in pages[0].text


def test_legacy_xls_extraction():
    pages = extract_pages(_path("sample_spec_sheet_legacy.xls"), "xls")

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "sulphur_ppm" in pages[0].text
    assert "8.5" in pages[0].text


def test_image_without_ocr_fn_raises():
    with pytest.raises(NotImplementedError):
        extract_pages("some_photo.jpg", "image")


def test_audio_without_transcribe_fn_raises():
    with pytest.raises(NotImplementedError):
        extract_pages("some_voice_note.wav", "audio")


def test_audio_with_transcribe_fn_returns_single_unpaginated_page():
    pages = extract_pages(
        "some_voice_note.wav",
        "audio",
        audio_transcribe_fn=lambda path: "Transcribed: schedule the turnaround for next week",
    )

    assert len(pages) == 1
    assert pages[0].page_number is None
    assert "turnaround" in pages[0].text


def test_unsupported_type_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported document type"):
        extract_pages("some_file.zip", "unknown")
