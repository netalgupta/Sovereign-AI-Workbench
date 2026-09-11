"""Pull the actual embedded images out of documents, store them, and
build the text that stands in for each one inside a chunk.

This is the half of image handling that was missing. Previously a PDF
page containing a figure was RASTERISED WHOLE to a temp PNG, handed to
the vision model, described, and the temp file deleted. Three things
were lost by that:

  1. the image itself — so "show me that diagram" could not be answered;
  2. which image — a full-page raster of a page holding two figures and
     a table describes the page, not either figure;
  3. where it came from — no document/page/position, so a retrieved
     chunk could not point back at anything.

Here each embedded image is extracted individually at its own
resolution, stored by content hash (see image_store.py), and given BOTH
kinds of understanding the system has: OCR text (what is written IN the
image — equipment tags, axis labels, a scanned paragraph) and a vision
description (what the image DEPICTS). Both go into the chunk text, so
the image is reachable by retrieval, and the stored id travels in chunk
metadata, so the pixels are reachable from the answer.

WHY BOTH, always, rather than picking one by image type: the two answer
different questions and neither subsumes the other. OCR on a P&ID gives
you "V-204, E-201B, K-201" — exactly the tokens an engineer searches
for, and which a prose description usually paraphrases away. The
description gives you "hydrocracker reactor loop with recycle gas
compressor", which OCR can never produce. Choosing between them by
guessing the image type would drop whichever the guess got wrong.
"""

from pathlib import Path

import fitz  # PyMuPDF
from pydantic import BaseModel

from backend.ingestion.image_store import (
    ImageOccurrence,
    ImageRecord,
    ImageStore,
    render_image_block,
)

# Images smaller than this in either dimension are skipped: they are
# rules, bullets, spacers and single-pixel layout shims, not content.
# Measured against the test corpus, real figures are hundreds of pixels
# on a side, while layout artefacts are under 40. Describing those would
# spend tens of seconds of vision inference per document to learn that a
# horizontal line is a horizontal line.
MIN_IMAGE_DIMENSION_PX = 48


class ExtractedImage(BaseModel):
    record: ImageRecord
    occurrence: ImageOccurrence
    block_text: str  # what to inline into the chunk


def _understand(
    store: ImageStore,
    record: ImageRecord,
    image_path: Path,
    ocr_fn=None,
    describe_fn=None,
) -> ImageRecord:
    """Attach OCR text and a description, skipping work already done.

    The skip is what makes re-ingestion affordable and is only sound
    because the store is content-addressed: an image with the same bytes
    IS the same image, so an understanding computed for it once remains
    correct wherever else it turns up.
    """
    needs_ocr = ocr_fn is not None and record.ocr_text is None
    needs_description = describe_fn is not None and record.description is None
    if not (needs_ocr or needs_description):
        return record

    ocr_text = None
    description = None
    if needs_ocr:
        try:
            ocr_text = ocr_fn(str(image_path))
        except Exception:  # noqa: BLE001 — one unreadable image must not abort ingestion
            ocr_text = None
    if needs_description:
        try:
            description = describe_fn(str(image_path))
        except Exception:  # noqa: BLE001 — same: a vision failure is not a corpus failure
            description = None

    return store.attach_understanding(
        record.image_id, ocr_text=ocr_text, description=description
    ) or record


def extract_pdf_page_images(
    file_path: str,
    page_number: int,
    store: ImageStore,
    ocr_fn=None,
    describe_fn=None,
) -> list[ExtractedImage]:
    """Extract, store and understand every embedded image on one PDF page.

    Uses PyMuPDF's xref-level extraction rather than rasterising the
    page: that returns each image's ORIGINAL bytes at its own
    resolution, which both OCR and the vision model read far better than
    a downscaled crop of a page render, and which is what should be
    handed back to a user who asks to see it.
    """
    results: list[ExtractedImage] = []
    with fitz.open(file_path) as doc:
        page = doc[page_number - 1]
        for index, info in enumerate(page.get_images(full=True)):
            xref = info[0]
            try:
                extracted = doc.extract_image(xref)
            except Exception:  # noqa: BLE001 — a corrupt xref is not a reason to lose the page
                continue

            data = extracted["image"]
            suffix = f".{extracted.get('ext', 'png')}"
            if min(extracted.get("width", 0), extracted.get("height", 0)) < MIN_IMAGE_DIMENSION_PX:
                continue

            # Where it sits on the page, for provenance and for a future
            # viewer that wants to highlight it in place. May be absent
            # for images referenced in unusual ways.
            rects = page.get_image_rects(xref)
            bbox = (
                (float(rects[0].x0), float(rects[0].y0), float(rects[0].x1), float(rects[0].y1))
                if rects
                else None
            )

            occurrence = ImageOccurrence(
                source_document=Path(file_path).name,
                page_number=page_number,
                bbox=bbox,
                index_on_page=index,
            )
            record = store.add(
                data,
                occurrence,
                content_type=f"image/{extracted.get('ext', 'png')}",
                suffix=suffix,
            )
            record = _understand(
                store, record, store.root / record.file_name, ocr_fn, describe_fn
            )
            results.append(
                ExtractedImage(
                    record=record,
                    occurrence=occurrence,
                    block_text=render_image_block(record, occurrence),
                )
            )
    return results


def extract_docx_images(
    file_path: str,
    store: ImageStore,
    ocr_fn=None,
    describe_fn=None,
) -> list[ExtractedImage]:
    """Extract, store and understand every embedded image in a DOCX.

    DOCX has no page geometry — content is a flow, and where an image
    lands on a printed page depends on the renderer — so occurrences
    carry `page_number=None` and `bbox=None` rather than a fabricated
    position. That is a real property of the format, not missing data,
    and inventing a page number would make provenance look more precise
    than it is.
    """
    import docx

    results: list[ExtractedImage] = []
    document = docx.Document(file_path)
    for index, rel in enumerate(document.part.rels.values()):
        if "image" not in rel.reltype:
            continue
        try:
            data = rel.target_part.blob
        except Exception:  # noqa: BLE001
            continue

        suffix = Path(str(rel.target_part.partname)).suffix or ".png"
        occurrence = ImageOccurrence(
            source_document=Path(file_path).name,
            page_number=None,
            bbox=None,
            index_on_page=index,
        )
        record = store.add(
            data, occurrence, content_type=f"image/{suffix.lstrip('.')}", suffix=suffix
        )
        record = _understand(store, record, store.root / record.file_name, ocr_fn, describe_fn)
        results.append(
            ExtractedImage(
                record=record,
                occurrence=occurrence,
                block_text=render_image_block(record, occurrence),
            )
        )
    return results


def extract_standalone_image(
    file_path: str,
    store: ImageStore,
    ocr_fn=None,
    describe_fn=None,
) -> ExtractedImage:
    """Store and understand an image file that IS the document.

    A scanned checklist or a diagram PNG ingested directly still needs a
    stored, retrievable identity — otherwise the one document type made
    entirely of an image is the one whose image cannot be shown back.
    """
    data = Path(file_path).read_bytes()
    suffix = Path(file_path).suffix or ".png"
    occurrence = ImageOccurrence(
        source_document=Path(file_path).name,
        page_number=1,
        bbox=None,
        index_on_page=0,
    )
    record = store.add(
        data, occurrence, content_type=f"image/{suffix.lstrip('.')}", suffix=suffix
    )
    record = _understand(store, record, store.root / record.file_name, ocr_fn, describe_fn)
    return ExtractedImage(
        record=record,
        occurrence=occurrence,
        block_text=render_image_block(record, occurrence),
    )
