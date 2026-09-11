"""Tests for the image store and image extraction.

The property under test throughout: an image that appears in a document
must remain retrievable — as pixels, with its provenance, and with
everything the pipeline understood about it — long after the ingestion
run that found it has finished. Before this existed, embedded images
were rendered to a temp file, described, and deleted, so a user asking
to see one could not be shown it.
"""

import io

import pytest

from backend.ingestion.image_store import (
    ImageOccurrence,
    ImageStore,
    render_image_block,
)


def _png_bytes(color=(220, 40, 40), size=(64, 64)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _occurrence(doc="report.pdf", page=3, index=0) -> ImageOccurrence:
    return ImageOccurrence(source_document=doc, page_number=page, index_on_page=index)


def test_stored_image_round_trips_by_id(tmp_path):
    store = ImageStore(tmp_path)
    data = _png_bytes()

    record = store.add(data, _occurrence())

    assert store.read_bytes(record.image_id) == data
    assert store.get(record.image_id).occurrences[0].source_document == "report.pdf"


def test_same_image_in_two_documents_is_stored_once_with_two_occurrences(tmp_path):
    """Content-addressing is load-bearing, not tidiness: real corpora
    repeat letterheads and standard diagrams constantly, and describing
    each copy separately would spend tens of seconds of vision inference
    per duplicate."""
    store = ImageStore(tmp_path)
    data = _png_bytes()

    first = store.add(data, _occurrence(doc="a.pdf", page=1))
    second = store.add(data, _occurrence(doc="b.pdf", page=7))

    assert first.image_id == second.image_id
    assert len(store.all_records()) == 1
    docs = {o.source_document for o in store.get(first.image_id).occurrences}
    assert docs == {"a.pdf", "b.pdf"}


def test_reingesting_the_same_document_does_not_duplicate_occurrences(tmp_path):
    """Re-running ingestion over an unchanged corpus must be idempotent,
    or occurrence lists grow without bound across runs."""
    store = ImageStore(tmp_path)
    data = _png_bytes()

    store.add(data, _occurrence())
    record = store.add(data, _occurrence())

    assert len(record.occurrences) == 1


def test_understanding_is_attached_and_persists(tmp_path):
    store = ImageStore(tmp_path)
    record = store.add(_png_bytes(), _occurrence())

    store.attach_understanding(
        record.image_id, ocr_text="V-204 E-201B", description="A hydrocracker P&ID."
    )

    reloaded = ImageStore(tmp_path).get(record.image_id)
    assert reloaded.ocr_text == "V-204 E-201B"
    assert reloaded.description == "A hydrocracker P&ID."
    assert reloaded.description_is_estimate is True


def test_description_is_flagged_as_an_estimate_by_default(tmp_path):
    """CLAUDE.md hard constraint #3. A vision description is never a
    measurement, and a record read straight off disk must carry that
    flag — measured reason: on charts with no printed numbers at all,
    the model still emitted specific figures and called them values
    'printed as text on the chart'."""
    store = ImageStore(tmp_path)
    record = store.add(_png_bytes(), _occurrence())

    updated = store.attach_understanding(record.image_id, description="Bar chart, R-201 highest.")

    assert updated.description_is_estimate is True


def test_block_text_carries_the_estimate_caveat_inline_not_only_in_metadata(tmp_path):
    """The caveat has to survive being rendered as plain text. If a
    consumer drops metadata — a prompt, a log line, a copy-paste into a
    report — a description that reads like a measurement is exactly the
    failure hard constraint #3 exists to prevent."""
    store = ImageStore(tmp_path)
    record = store.add(_png_bytes(), _occurrence())
    record = store.attach_understanding(
        record.image_id, ocr_text="R-201 18.5", description="Bar chart of downtime."
    )

    block = render_image_block(record, _occurrence())

    assert "estimate" in block.lower()
    assert "R-201 18.5" in block
    assert "Bar chart of downtime." in block
    # The id is the mechanism by which a retrieved chunk gets back to the
    # pixels — without it, "show me that image" has nothing to resolve.
    assert record.image_id[:12] in block


def test_block_text_says_so_when_nothing_could_be_extracted(tmp_path):
    """Silence would be indistinguishable from 'there was no image
    here', which is a different and misleading claim."""
    store = ImageStore(tmp_path)
    record = store.add(_png_bytes(), _occurrence())

    block = render_image_block(record, _occurrence())

    assert "No text or description" in block


def test_docx_images_have_no_fabricated_page_number(tmp_path):
    """DOCX is a flow format with no page geometry. Recording page 1
    would make provenance look more precise than it is."""
    from backend.ingestion.image_extraction import extract_docx_images
    import os

    fixtures = os.path.join(os.path.dirname(__file__), "fixtures")
    docx_path = os.path.join(fixtures, "sample_doc.docx")
    if not os.path.exists(docx_path):
        pytest.skip("sample_doc.docx fixture not present")

    store = ImageStore(tmp_path)
    images = extract_docx_images(docx_path, store)

    for image in images:
        assert image.occurrence.page_number is None
        assert image.occurrence.bbox is None
