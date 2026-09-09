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
from backend.ingestion.xlsx_charts import chart_description_to_text, extract_chart_descriptions
from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from pydantic import BaseModel

# file_path -> extracted text. See module docstring for what the real
# implementation must actually be (a printed/handwritten router, not a
# single OCR backend).
OcrFn = Callable[[str], str]

# raw audio file path -> transcribed text. Real implementation: CARD 12.
AudioTranscribeFn = Callable[[str], str]

# rendered page image path -> chart/figure description text. Real
# implementation: chart_understanding.py's describe_chart_image (an
# ESTIMATE, never a verified fact — see that module's docstring).
ChartImageFn = Callable[[str], str]


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


def _extract_native_pdf_pages(
    file_path: str,
    ocr_fn: OcrFn | None,
    chart_image_fn: ChartImageFn | None = None,
) -> list[PageText]:
    pages: list[PageText] = []
    blank_page_numbers: list[int] = []
    pages_with_images: list[int] = []

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                blank_page_numbers.append(i)
            if page.images:
                pages_with_images.append(i)
            pages.append(PageText(page_number=i, text=text))

    if blank_page_numbers:
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

    # A page can have real extractable text AND an embedded chart image
    # at the same time (this corpus's own PDFs are exactly this shape:
    # real prose/table text plus an illustrative chart picture) — chart
    # description is additive to whatever text extraction already
    # found, never a replacement for it. No default wiring here (see
    # chart_understanding.py's module docstring on why its output is
    # always an estimate, never presented as a verified fact) — this is
    # purely an opt-in seam until a caller explicitly wants it.
    if chart_image_fn is not None:
        for page_number in pages_with_images:
            png_path = _render_pdf_page_to_png(file_path, page_number - 1)
            try:
                chart_text = chart_image_fn(png_path)
            finally:
                Path(png_path).unlink(missing_ok=True)
            if chart_text:
                idx = page_number - 1
                pages[idx] = PageText(
                    page_number=page_number,
                    text=f"{pages[idx].text}\n{chart_text}".strip(),
                )

    return pages


def _iter_block_items(doc):
    """Yield each paragraph/table in actual document order.

    Real bug this fixes, found by inspecting real extracted output, not
    by re-reading the code: python-docx's `.paragraphs` and `.tables`
    are two SEPARATE flat lists, each in their own internal order but
    with no relationship to each other's position in the document. The
    original version of this function did `[p.text for p in
    doc.paragraphs]` followed by `for table in doc.tables: ...` — i.e.
    every paragraph, THEN every table, regardless of where each table
    actually sits in the document. On a real SOP fixture, this put the
    sentence "The table below lists the normal operating envelope..."
    in one chunk and the table's actual data (including the exact value
    a real test question asks for) in a completely different chunk,
    separated by everything else in the document — a real retrieval-
    locality bug, not just a cosmetic one. Iterating the underlying XML
    body's children in order and dispatching each to the right wrapper
    is the standard python-docx idiom for "give me content in document
    order" — there's no higher-level API that does this directly.
    """
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield DocxParagraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield DocxTable(child, doc)


def _extract_docx(file_path: str) -> list[PageText]:
    # DOCX has no reliable page boundaries at the file-format level
    # (pagination depends on the renderer/font/margins) — per spec,
    # page_number is genuinely None here, not a missing value.
    doc = DocxDocument(file_path)
    parts = []
    for block in _iter_block_items(doc):
        if isinstance(block, DocxParagraph):
            if block.text:
                parts.append(block.text)
        else:  # DocxTable
            for row in block.rows:
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
    #
    # NOT read_only=True here, on purpose: read_only mode has no
    # `_charts` attribute at all (verified directly against a real
    # corpus file — `hasattr(ws, "_charts")` is False in read_only mode,
    # True otherwise), so a sheet's native charts are invisible in that
    # mode by construction. read_only exists purely for large-workbook
    # performance, which doesn't matter at this corpus's scale, and
    # correctness (seeing the charts at all) matters more here.
    workbook = openpyxl.load_workbook(file_path, data_only=True)
    pages: list[PageText] = []
    for i, sheet_name in enumerate(workbook.sheetnames, start=1):
        sheet = workbook[sheet_name]
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        text = _sheet_to_text(sheet_name, rows)

        charts = extract_chart_descriptions(sheet)
        if charts:
            chart_text = "\n".join(chart_description_to_text(c) for c in charts)
            text = f"{text}\n{chart_text}"

        pages.append(PageText(page_number=i, text=text))
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
    chart_image_fn: ChartImageFn | None = None,
) -> list[PageText]:
    """Extract text per RAG_SPEC.md §2 step 2, preserving page/sheet boundaries.

    `chart_image_fn` is purely opt-in (no default anywhere in this
    pipeline) — a PDF page's embedded chart PICTURE only ever gets
    described if a caller explicitly passes this in. Native XLSX charts
    need no such thing at all: their exact data is read directly,
    deterministically, by xlsx_charts.py inside _extract_xlsx, with zero
    vision model involved — see that module's docstring for why the two
    cases are handled by genuinely different tools, not one.

    Raises:
        NotImplementedError: for a scanned/image page or an audio file
            when the matching extraction function isn't provided — never
            silently returns empty text for content that actually exists.
        ValueError: for a `detected_type` this pipeline doesn't handle.
    """
    if detected_type == "pdf":
        return _extract_native_pdf_pages(file_path, ocr_fn, chart_image_fn)
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
