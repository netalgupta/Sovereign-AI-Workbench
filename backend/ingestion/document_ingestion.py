"""Full per-document ingestion pipeline — RAG_SPEC.md §2, steps 1-4 tied together.

This is the single function the rest of the system calls to turn one
file into a list of chunks ready for embedding — detection, extraction,
chunking, and metadata attachment, in the exact order RAG_SPEC.md
specifies.
"""

import datetime
from pathlib import Path

from pydantic import BaseModel

from backend.ingestion.boilerplate import strip_boilerplate
from backend.ingestion.chunking import chunk_text
from backend.ingestion.document_types import detect_document_type
from backend.ingestion.text_extraction import (
    AudioTranscribeFn,
    ChartImageFn,
    OcrFn,
    PageText,
    extract_pages,
)


class ChunkMetadata(BaseModel):
    """RAG_SPEC.md §2 step 4 — every field mandatory, none optional.

    `page_number` is the one field allowed to be None, and only when the
    source format is genuinely unpaginated (DOCX/TXT/email) — never as a
    stand-in for "we didn't bother tracking it."
    """

    source_document: str
    document_type: str
    page_number: int | None
    chunk_index: int
    ingestion_date: str


class IngestedChunk(BaseModel):
    text: str
    metadata: ChunkMetadata


def _default_audio_transcribe_fn(audio_path: str) -> str:
    # Lazy import, deliberately: this pulls in faster-whisper (and loads
    # its model on first use) only when an actual audio file reaches
    # this function. A PDF/DOCX/TXT ingestion call must never pay that
    # cost just because this module is imported.
    from backend.tools.audio.voice_transcription import transcribe_voice_note

    return transcribe_voice_note(audio_path).full_text


def ingest_document(
    file_path: str,
    ocr_fn: OcrFn | None = None,
    audio_transcribe_fn: AudioTranscribeFn | None = None,
    chart_image_fn: ChartImageFn | None = None,
) -> list[IngestedChunk]:
    """Detect, extract, chunk, and tag one document with metadata.

    Args:
        file_path: path to the source document.
        ocr_fn: passed straight through to text_extraction.extract_pages
            for scanned PDFs/images. No default: CARD 05
            (extract_printed_text) now exists and works, but it only
            handles PRINTED text — defaulting to it directly would
            silently produce garbage on a handwritten page, exactly the
            anti-pattern text_extraction.py's own module docstring warns
            against. A real default needs the printed-vs-handwritten
            router (TOOLS.md tool #9) this repo doesn't have yet, not
            just CARD 05 alone.
        audio_transcribe_fn: same injection point, for voice notes — BUT
            this one has a real default (CARD 12 already exists, and
            there's no printed-vs-handwritten-shaped ambiguity for
            audio), so audio files work out of the box unless you
            explicitly want to override it (e.g. in a test).
        chart_image_fn: same injection point, for describing a PDF
            page's embedded chart picture (chart_understanding.py) — no
            default, since its output is always a vision-model estimate
            (see that module's docstring), never something to apply
            silently by default the way a verified extraction would be.
    """
    type_info = detect_document_type(file_path)
    if audio_transcribe_fn is None:
        audio_transcribe_fn = _default_audio_transcribe_fn
    pages = extract_pages(
        file_path,
        type_info.detected_type,
        ocr_fn=ocr_fn,
        audio_transcribe_fn=audio_transcribe_fn,
        chart_image_fn=chart_image_fn,
    )

    return pages_to_chunks(pages, Path(file_path).name, type_info.detected_type)


def pages_to_chunks(
    pages: list[PageText],
    source_document: str,
    document_type: str,
    boilerplate_sentences: set[str] | None = None,
) -> list[IngestedChunk]:
    """Chunk + tag already-extracted pages — the second half of
    ingest_document(), split out so a corpus-level caller can run a
    cross-document pass (boilerplate detection — RAG_SPEC.md §2; see
    ingest_corpus.py's `ingest_corpus_with_boilerplate_removal`) BETWEEN
    extraction and chunking, without paying for extraction (OCR/ASR
    calls included) a second time. `ingest_document` above is just this
    function preceded by detect+extract, for the common single-file case
    that doesn't need cross-document boilerplate awareness.

    `boilerplate_sentences`, if given, is stripped from every page's
    text (via backend.ingestion.boilerplate.strip_boilerplate) before
    chunking — sentences recurring near-verbatim across many documents
    (letterhead, footers, standard disclaimers) that would otherwise
    become shared noise in every chunk's embedding and BM25 tokens.
    """
    ingestion_date = datetime.date.today().isoformat()

    chunks: list[IngestedChunk] = []
    chunk_index = 0
    for page in pages:
        text = page.text
        if boilerplate_sentences:
            text = strip_boilerplate(text, boilerplate_sentences)
        for piece in chunk_text(text):
            chunks.append(
                IngestedChunk(
                    text=piece,
                    metadata=ChunkMetadata(
                        source_document=source_document,
                        document_type=document_type,
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        ingestion_date=ingestion_date,
                    ),
                )
            )
            chunk_index += 1
    return chunks
