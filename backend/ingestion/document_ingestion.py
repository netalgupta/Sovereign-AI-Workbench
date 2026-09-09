"""Full per-document ingestion pipeline — RAG_SPEC.md §2, steps 1-4 tied together.

This is the single function the rest of the system calls to turn one
file into a list of chunks ready for embedding — detection, extraction,
chunking, and metadata attachment, in the exact order RAG_SPEC.md
specifies.
"""

import datetime
from pathlib import Path

from pydantic import BaseModel

from backend.ingestion.chunking import chunk_text
from backend.ingestion.document_types import detect_document_type
from backend.ingestion.text_extraction import AudioTranscribeFn, OcrFn, extract_pages


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
) -> list[IngestedChunk]:
    """Detect, extract, chunk, and tag one document with metadata.

    Args:
        file_path: path to the source document.
        ocr_fn: passed straight through to text_extraction.extract_pages
            for scanned PDFs/images — see that module's docstring for why
            OCR is injected rather than imported directly here. No
            default yet: CARD 05 (PaddleOCR)/its handwritten fallback
            isn't built in this repo yet, so omitting this for an
            image/scanned input still raises NotImplementedError.
        audio_transcribe_fn: same injection point, for voice notes — BUT
            this one has a real default (CARD 12 already exists), so
            audio files work out of the box unless you explicitly want
            to override it (e.g. in a test).
    """
    type_info = detect_document_type(file_path)
    if audio_transcribe_fn is None:
        audio_transcribe_fn = _default_audio_transcribe_fn
    pages = extract_pages(
        file_path,
        type_info.detected_type,
        ocr_fn=ocr_fn,
        audio_transcribe_fn=audio_transcribe_fn,
    )

    source_document = Path(file_path).name
    ingestion_date = datetime.date.today().isoformat()

    chunks: list[IngestedChunk] = []
    chunk_index = 0
    for page in pages:
        for piece in chunk_text(page.text):
            chunks.append(
                IngestedChunk(
                    text=piece,
                    metadata=ChunkMetadata(
                        source_document=source_document,
                        document_type=type_info.detected_type,
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        ingestion_date=ingestion_date,
                    ),
                )
            )
            chunk_index += 1
    return chunks
