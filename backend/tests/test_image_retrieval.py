"""Tests for answering "show me that image".

The scenario these exist for: a page holds several images, so every
chunk from that page references all of them. Returning the chunk's
images returns all three and makes the user find theirs. The request
itself has to pick one.

Uses the real embedding model, not a fake: what is under test is whether
"the schematic" actually scores higher against a P&ID's description than
against a downtime chart's, which is a property of the embeddings and
cannot be demonstrated with mocked vectors.
"""

import io

import pytest

from backend.ingestion.image_store import ImageOccurrence, ImageStore
from backend.retrieval.image_retrieval import (
    images_referenced_by_chunks,
    resolve_image_bytes,
    select_images_for_request,
)


def _png(color=(10, 20, 30)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def store_with_three_images(tmp_path):
    """One page, three very different images — the real disambiguation case."""
    store = ImageStore(tmp_path)
    ids = {}

    specs = [
        ("pid", (10, 20, 30),
         "V-204 V-205 E-201B K-201 Reactor Stripper HP Separator",
         "A piping and instrumentation diagram of the hydrocracker reactor loop, "
         "showing vessels, the recycle gas compressor and heat exchangers."),
        ("downtime", (40, 50, 60),
         "Downtime by Equipment hrs Q3 2026 R-201 CCR-1",
         "A bar chart of equipment downtime in hours for the third quarter."),
        ("letterhead", (70, 80, 90),
         "Mangalore Refinery and Petrochemicals Limited",
         "A company letterhead logo at the top of the page."),
    ]
    for i, (name, color, ocr, description) in enumerate(specs):
        record = store.add(
            _png(color),
            ImageOccurrence(source_document="incident_report.pdf", page_number=3, index_on_page=i),
        )
        store.attach_understanding(record.image_id, ocr_text=ocr, description=description)
        ids[name] = record.image_id

    return store, ids


def test_request_for_the_schematic_returns_the_schematic_not_the_chart(store_with_three_images):
    store, ids = store_with_three_images

    matches = select_images_for_request(
        "show me the hydrocracker schematic", list(ids.values()), store, top_k=1
    )

    assert len(matches) == 1
    assert matches[0].image_id == ids["pid"]


def test_request_for_the_downtime_chart_returns_the_chart(store_with_three_images):
    store, ids = store_with_three_images

    matches = select_images_for_request(
        "show me the equipment downtime chart", list(ids.values()), store, top_k=1
    )

    assert matches[0].image_id == ids["downtime"]


def test_request_naming_an_equipment_tag_matches_via_ocr_text(store_with_three_images):
    """OCR and description answer different questions and neither
    subsumes the other. An engineer searching for "V-204" is searching
    text that exists only in the OCR, which a prose description would
    have paraphrased away."""
    store, ids = store_with_three_images

    matches = select_images_for_request(
        "the diagram showing V-204 and E-201B", list(ids.values()), store, top_k=1
    )

    assert matches[0].image_id == ids["pid"]


def test_returns_nothing_rather_than_a_weak_best_guess(store_with_three_images):
    """Always returning the top match means a question that referenced no
    image still produces one, which reads as a claim that the picture is
    relevant. Putting the wrong diagram in front of an engineer is worse
    than attaching none."""
    store, ids = store_with_three_images

    matches = select_images_for_request(
        "what is the capital of France", list(ids.values()), store,
        top_k=1, min_similarity=0.5,
    )

    assert matches == []


def test_the_actual_pixels_come_back(store_with_three_images):
    """The whole point: not a description of the image, the image."""
    store, ids = store_with_three_images

    matches = select_images_for_request(
        "the hydrocracker P&ID", list(ids.values()), store, top_k=1
    )
    data = resolve_image_bytes(matches[0], store)

    assert data is not None
    assert data.startswith(b"\x89PNG")


def test_match_carries_provenance_and_the_estimate_flag(store_with_three_images):
    store, ids = store_with_three_images

    match = select_images_for_request("the schematic", list(ids.values()), store, top_k=1)[0]

    assert match.source_document == "incident_report.pdf"
    assert match.page_number == 3
    # CLAUDE.md hard constraint #3: a vision description is never a
    # measurement, and the flag must survive to the point of display.
    assert match.description_is_estimate is True


def test_duplicate_ids_across_chunks_are_offered_once(store_with_three_images):
    """Every chunk from a page carries that page's images, so a
    multi-chunk answer naturally arrives with the same id repeated. The
    same picture must not be offered twice."""
    store, ids = store_with_three_images
    repeated = list(ids.values()) * 3

    matches = select_images_for_request("the schematic", repeated, store, top_k=3)

    assert len({m.image_id for m in matches}) == len(matches)


def test_images_referenced_by_chunks_reads_ingestion_shaped_chunks():
    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

    def _chunk(image_ids):
        return IngestedChunk(
            text="some text",
            metadata=ChunkMetadata(
                source_document="d.pdf", document_type="pdf", page_number=1,
                chunk_index=0, ingestion_date="2026-09-11", image_ids=image_ids,
            ),
        )

    ids = images_referenced_by_chunks([_chunk(["a", "b"]), _chunk(["b", "c"])])

    assert ids == ["a", "b", "c"]
