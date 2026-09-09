"""Text extraction — RAG_SPEC.md §2 step 2.

WHY EVERYTHING RETURNS PER-PAGE, NOT ONE JOINED STRING: RAG_SPEC.md's
ChunkMetadata requires a `page_number` on every chunk, and NFR-4 requires
every claim traceable to a source passage — losing page boundaries at
extraction time makes accurate page citations impossible ever after, no
matter how careful chunking is later. So extraction keeps pages/sheets
separate; chunking (chunking.py) operates within each unit and tags every
resulting chunk with that unit's number.

WHY PDF OCR FALLBACK IS PER-PAGE, NOT PER-DOCUMENT: a real refinery
document is very often mixed — e.g. a printed cover letter followed by a
scanned, hand-signed approval page. An earlier version of this function
checked "does ANY page have text?" and, if so, returned every page
as-is — silently returning an empty string for any blank page inside an
otherwise text-native PDF. That's silent data loss on exactly the kind
of document this system exists to read correctly. Each page is now
checked and OCR'd independently, and if OCR isn't available, the error
names precisely which page numbers need it.

OCR/ASR are deliberately NOT implemented in this file. Scanned pages,
handwritten notes, and voice notes need CARD 05 (PaddleOCR)/its TrOCR
handwritten fallback, or CARD 12 (local ASR) — vision/audio-tool
territory, not ingestion-pipeline territory (SYSTEM.md keeps these as
separate sub-agents on purpose). This module takes `ocr_fn` as an
injected callable rather than importing a vision tool directly, so the
ingestion pipeline is fully testable today and plugs in the real tool
later with a one-line change, not a rewrite.

IMPORTANT for whoever wires `ocr_fn` in for real: do not wire in CARD 05's
extract_printed_text alone. That function only handles printed text —
handed a handwritten page, it will confidently produce garbage, not an
error. The printed-vs-handwritten decision is TOOLS.md tool #9's
document-type classifier's job; `ocr_fn` should be that router's
entrypoint (which picks CARD 05 or the TrOCR/VLM fallback internally),
not a direct alias for one specific OCR backend.
"""

import email
import os
import tempfile
from email import policy
from pathlib import Path
from typing import Callable

import openpyxl
import pdfplumber
import xlrd
from docx import Document as DocxDocument
from pydantic import BaseModel

# file_path -> extracted text. See module docstring for what the real
# implementation must actually be (a printed/handwritten router, not a
# single OCR backend).
OcrFn = Callable[[str], str]

# raw audio file path -> transcribed text. Real implementation: CARD 12.
AudioTranscribeFn = Callable[[str], str]


class PageText(BaseModel):
    page_number: int | None  # None only if genuinely unpaginated, per RAG_SPEC.md §2 step 4
    text: str


def _render_pdf_page_to_png(file_path: str, page_index: int) -> str:
    """Render one PDF page (0-indexed) to a temp PNG file, return its path.

    Caller owns deleting the temp file. Uses PyMuPDF purely for
    rasterizing a page to an image for OCR input — it does not do any
    text extraction itself here (pdfplumber already handled that).

    Real bug fixed here, not hypothetical: `tempfile.NamedTemporaryFile`
    keeps its own file handle open for the whole `with` block. On
    Windows, a second write to that same path (PyMuPDF's own
    `pixmap.save`) is refused while that handle is still open —
    "Permission denied", caught by actually running this on Windows, not
    by reading the code. `mkstemp` + closing the descriptor immediately
    avoids holding a handle at all, so PyMuPDF can open-and-write the
    path itself. This also happens to be the portable, correct pattern
    on Linux, where the original code would have worked by accident.
    """
    import fitz  # PyMuPDF

    fd, png_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)  # release our handle before any other library touches the path

    with fitz.open(file_path) as doc:
        pixmap = doc[page_index].get_pixmap(dpi=300)
        pixmap.save(png_path)
    return png_path


def _extract_native_pdf_pages(file_path: str, ocr_fn: OcrFn | None) -> list[PageText]:
    pages: list[PageText] = []
    blank_page_numbers: list[int] = []

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                blank_page_numbers.append(i)
            pages.append(PageText(page_number=i, text=text))

    if not blank_page_numbers:
        return pages

    if ocr_fn is None:
        raise NotImplementedError(
            f"{file_path} has no extractable text on page(s) {blank_page_numbers} "
            f"(scanned, handwritten, or image-only). Pass an ocr_fn — see this "
            f"module's docstring for what that function must actually do."
        )

    for page_number in blank_page_numbers:
        png_path = _render_pdf_page_to_png(file_path, page_number - 1)
        try:
            ocr_text = ocr_fn(png_path)
        finally:
            Path(png_path).unlink(missing_ok=True)
        pages[page_number - 1] = PageText(page_number=page_number, text=ocr_text)

    return pages


def _extract_docx(file_path: str) -> list[PageText]:
    # DOCX has no reliable page boundaries at the file-format level
    # (pagination depends on the renderer/font/margins) — per spec,
    # page_number is genuinely None here, not a missing value.
    doc = DocxDocument(file_path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return [PageText(page_number=None, text="\n".join(parts))]


def _extract_txt(file_path: str) -> list[PageText]:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return [PageText(page_number=None, text=text)]


def _extract_csv(file_path: str) -> list[PageText]:
    # CSV is already delimited text — no special parsing needed for
    # chunking purposes, just tagged distinctly for provenance (a fact
    # pulled from a CSV export should say so in ChunkMetadata.document_type).
    return _extract_txt(file_path)


def _extract_eml(file_path: str) -> list[PageText]:
    with open(file_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    return [PageText(page_number=None, text=text)]


def _sheet_to_text(sheet_name: str, rows: list[list[str]]) -> str:
    lines = [f"Sheet: {sheet_name}"]
    lines.extend("\t".join(cell for cell in row) for row in rows)
    return "\n".join(lines)


def _extract_xlsx(file_path: str) -> list[PageText]:
    # A spreadsheet's sheets are the natural analogue of a PDF's pages —
    # `page_number` here is the 1-indexed sheet position, deliberately,
    # so a citation can still say "which sheet this fact came from"
    # (NFR-4) rather than falling back to None just because it isn't a
    # printed page.
    workbook = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    pages: list[PageText] = []
    for i, sheet_name in enumerate(workbook.sheetnames, start=1):
        sheet = workbook[sheet_name]
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        pages.append(PageText(page_number=i, text=_sheet_to_text(sheet_name, rows)))
    workbook.close()
    return pages


def _extract_xls(file_path: str) -> list[PageText]:
    # Legacy binary .xls format — openpyxl cannot read this (it's an
    # OOXML-only library); xlrd 2.x dropped xlsx support specifically to
    # keep supporting only the legacy format, so the two libraries are a
    # deliberate matched pair covering both eras of Excel file, not a
    # redundant duplicate.
    workbook = xlrd.open_workbook(file_path)
    pages: list[PageText] = []
    for i in range(workbook.nsheets):
        sheet = workbook.sheet_by_index(i)
        rows = [
            [str(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
        pages.append(PageText(page_number=i + 1, text=_sheet_to_text(sheet.name, rows)))
    return pages


def extract_pages(
    file_path: str,
    detected_type: str,
    ocr_fn: OcrFn | None = None,
    audio_transcribe_fn: AudioTranscribeFn | None = None,
) -> list[PageText]:
    """Extract text per RAG_SPEC.md §2 step 2, preserving page/sheet boundaries.

    Raises:
        NotImplementedError: for a scanned/image page or an audio file
            when the matching extraction function isn't provided — never
            silently returns empty text for content that actually exists.
        ValueError: for a `detected_type` this pipeline doesn't handle.
    """
    if detected_type == "pdf":
        return _extract_native_pdf_pages(file_path, ocr_fn)
    if detected_type == "docx":
        return _extract_docx(file_path)
    if detected_type == "txt":
        return _extract_txt(file_path)
    if detected_type == "csv":
        return _extract_csv(file_path)
    if detected_type == "xlsx":
        return _extract_xlsx(file_path)
    if detected_type == "xls":
        return _extract_xls(file_path)
    if detected_type == "email":
        return _extract_eml(file_path)
    if detected_type == "image":
        if ocr_fn is None:
            raise NotImplementedError(
                f"{file_path} is an image and requires OCR, but no ocr_fn "
                f"was provided — see this module's docstring."
            )
        return [PageText(page_number=None, text=ocr_fn(file_path))]
    if detected_type == "audio":
        if audio_transcribe_fn is None:
            raise NotImplementedError(
                f"{file_path} is an audio file and requires transcription, "
                f"but no audio_transcribe_fn was provided. Pass CARD 12's "
                f"transcribe_voice_note as audio_transcribe_fn once the "
                f"audio tools land."
            )
        return [PageText(page_number=None, text=audio_transcribe_fn(file_path))]

    raise ValueError(f"Unsupported document type for extraction: {detected_type!r}")
