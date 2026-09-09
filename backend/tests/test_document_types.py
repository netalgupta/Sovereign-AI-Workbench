"""Tests for detect_document_type.

Every assertion here is checked against what this machine's real
`python-magic` build actually reports (verified by hand before writing
these — see the module docstring in document_types.py for why). Two of
these are not hypothetical edge cases: on this exact libmagic build,
.docx reports as "application/octet-stream" and .xlsx as "application/zip"
— without the extension-fallback logic this file tests, both would
silently misclassify as "unknown".
"""

import os

import pytest

from backend.ingestion.document_types import detect_document_type

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _path(name: str) -> str:
    return os.path.join(FIXTURES, name)


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        ("sample_native.pdf", "pdf"),
        ("sample_doc.docx", "docx"),  # real MIME: application/octet-stream on this build
        ("sample_note.txt", "txt"),
        ("sample_lab_results.csv", "csv"),  # real MIME: text/plain — ambiguous with .txt
        ("sample_spec_sheet.xlsx", "xlsx"),  # real MIME: application/zip on this build
        ("sample_spec_sheet_legacy.xls", "xls"),  # real MIME: application/vnd.ms-excel
        ("sample_email.eml", "email"),
    ],
)
def test_detects_expected_type_from_real_fixture(filename, expected_type):
    result = detect_document_type(_path(filename))
    assert result.detected_type == expected_type


def test_docx_mime_is_actually_octet_stream_on_this_build():
    # Documents the exact real-world case the extension fallback exists
    # for — if a future libmagic upgrade starts parsing OOXML correctly,
    # this assertion (not the detected_type one above) is what breaks,
    # and that's useful information, not a false failure.
    result = detect_document_type(_path("sample_doc.docx"))
    assert result.mime_type in ("application/octet-stream", "application/zip")
    assert result.detected_type == "docx"  # extension correctly overrides either way


def test_missing_file_raises_exact_message():
    missing_path = _path("does_not_exist.pdf")
    with pytest.raises(FileNotFoundError) as exc_info:
        detect_document_type(missing_path)
    assert str(exc_info.value) == f"Document not found at {missing_path}"


def test_mislabeled_file_is_caught_by_mime_not_extension(tmp_path):
    # The other direction: a file actually containing PDF bytes but
    # named .txt. MIME must win here — this is precisely what "don't
    # trust extension alone" is FOR (a renamed/mislabeled file).
    mislabeled = tmp_path / "actually_a_pdf.txt"
    mislabeled.write_bytes(b"%PDF-1.4\n%mislabeled but real PDF bytes\n")

    result = detect_document_type(str(mislabeled))

    assert result.detected_type == "pdf"
    assert result.file_extension == ".txt"


def test_csv_vs_txt_disambiguation_relies_on_extension(tmp_path):
    # Both are legitimately "text/plain" in MIME terms — there is no
    # byte signature that tells them apart. This is the other concrete
    # case (alongside OOXML) that justifies letting extension win when
    # MIME is genuinely ambiguous rather than always "trusting MIME more".
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("just some notes\n", encoding="utf-8")

    assert detect_document_type(str(csv_file)).detected_type == "csv"
    assert detect_document_type(str(txt_file)).detected_type == "txt"
