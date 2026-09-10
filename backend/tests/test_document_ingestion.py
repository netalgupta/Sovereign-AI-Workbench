"""Tests for ingest_document — the full pipeline tying detection,
extraction, chunking, and metadata together (RAG_SPEC.md §2, steps 1-4)."""

import os

import pytest

from backend.ingestion import model_cache
from backend.ingestion.document_ingestion import ingest_document

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _path(name: str) -> str:
    return os.path.join(FIXTURES, name)


def test_pages_to_chunks_strips_boilerplate_when_given():
    from backend.ingestion.document_ingestion import pages_to_chunks
    from backend.ingestion.text_extraction import PageText

    pages = [PageText(page_number=1, text="Real content about WABT triggers. Standard disclaimer text.")]

    chunks = pages_to_chunks(
        pages, "doc.pdf", "pdf", boilerplate_sentences={"standard disclaimer text."}
    )

    assert len(chunks) == 1
    assert "disclaimer" not in chunks[0].text.lower()
    assert "WABT triggers" in chunks[0].text


def test_pages_to_chunks_without_boilerplate_arg_behaves_exactly_like_ingest_document():
    """No boilerplate_sentences passed -- must be a pure passthrough,
    identical to the pre-refactor behavior (backward compatibility)."""
    from backend.ingestion.document_ingestion import pages_to_chunks
    from backend.ingestion.text_extraction import PageText

    pages = [PageText(page_number=1, text="Some real content here.")]
    chunks = pages_to_chunks(pages, "doc.pdf", "pdf")

    assert len(chunks) == 1
    assert chunks[0].text == "Some real content here."


def test_ingest_native_pdf_produces_chunks_with_correct_metadata():
    chunks = ingest_document(_path("sample_native.pdf"))

    assert len(chunks) >= 1
    first = chunks[0]
    assert first.metadata.source_document == "sample_native.pdf"
    assert first.metadata.document_type == "pdf"
    assert first.metadata.page_number == 1
    assert first.metadata.chunk_index == 0
    # ISO 8601 date, per RAG_SPEC.md §2 step 4 — sanity-check the shape.
    assert len(first.metadata.ingestion_date) == 10
    assert first.metadata.ingestion_date.count("-") == 2


def test_ingest_docx_has_no_page_number():
    chunks = ingest_document(_path("sample_doc.docx"))

    assert len(chunks) >= 1
    assert all(chunk.metadata.page_number is None for chunk in chunks)
    assert all(chunk.metadata.document_type == "docx" for chunk in chunks)


def test_chunk_index_increases_monotonically_across_pages():
    # sample_native.pdf has 2 pages — chunk_index must be a single
    # running count across the WHOLE document, not restarting per page,
    # so it can be used as a stable ordering key.
    chunks = ingest_document(_path("sample_native.pdf"))

    indices = [chunk.metadata.chunk_index for chunk in chunks]
    assert indices == list(range(len(chunks)))


def test_ingest_xlsx_tags_sheet_as_page_number():
    chunks = ingest_document(_path("sample_spec_sheet.xlsx"))

    assert len(chunks) >= 1
    assert chunks[0].metadata.page_number == 1
    assert chunks[0].metadata.document_type == "xlsx"
    assert "sulphur_ppm" in chunks[0].text


@pytest.mark.skipif(
    not model_cache.local_cache_dir("audio", "Systran/faster-whisper-base").exists(),
    reason="faster-whisper-base not cached — see test_voice_transcription.py",
)
def test_ingest_audio_uses_real_transcription_by_default():
    # No audio_transcribe_fn passed — this exercises the actual default
    # wired in document_ingestion.py (CARD 12), not an injected fake, to
    # prove the two modules are really connected end-to-end.
    chunks = ingest_document(_path("sample_voice_note.wav"))

    assert len(chunks) >= 1
    assert chunks[0].metadata.document_type == "audio"
    assert chunks[0].metadata.page_number is None
    assert "hydrocracker" in chunks[0].text.lower()
