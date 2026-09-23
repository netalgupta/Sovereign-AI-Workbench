from __future__ import annotations

"""Full per-document ingestion pipeline — RAG_SPEC.md §2, steps 1-4 tied together.

This is the single function the rest of the system calls to turn one
file into a list of chunks ready for embedding — detection, extraction,
chunking, and metadata attachment, in the exact order RAG_SPEC.md
specifies.
"""

import datetime
import os
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
    # Images embedded in the page this chunk came from, by content-hash
    # id (backend/ingestion/image_store.py). This is what lets an answer
    # built on this chunk hand back the actual picture rather than only
    # describing it. Every chunk from a page inherits that page's images:
    # a chunk is a slice of text, but the image belongs to the page, and
    # attributing it to only whichever slice happens to contain the
    # description block would make it unreachable from the others.
    image_ids: list[str] = []


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


# A single document larger than this is refused rather than ingested.
#
# Not arbitrary: the pipeline holds a whole document's extracted text in
# memory, chunks it, and embeds every chunk. A multi-gigabyte file does
# not fail fast -- it consumes the box, and on a workstation that is
# also running the models, it takes the demo with it. Refusing at the
# door is recoverable; an OOM three minutes into an ingest is not.
#
# Overridable, because a real MRPL P&ID set may legitimately exceed it
# and the person who knows that should be able to say so.
MAX_DOCUMENT_BYTES = int(os.environ.get("WORKBENCH_MAX_DOCUMENT_MB", "200")) * 1024 * 1024


def _check_ingestible(file_path: str) -> None:
    """Refuse a file that should not be read, before reading it.

    TWO CHECKS, BOTH CHEAP, BOTH BEFORE ANY I/O ON THE CONTENT.

    SIZE, for the reason above.

    SYMLINK ESCAPE, because the ingestion path is user-supplied: the
    Sources panel takes a folder, and a symlink inside it pointing at
    C:\\Users\\... or /etc would be followed and its contents embedded
    into a corpus that then answers questions from them. On a workbench
    whose premise is that confidential data stays where it is put, that
    is the wrong direction to be permissive in.

    Raises:
        ValueError: naming which check failed and what the limit is --
            "file too large" without the number sends someone looking
            through code to find it.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found at {file_path}")

    resolved = path.resolve()
    if path.is_symlink() and resolved != path.absolute():
        raise ValueError(
            f"{file_path} is a symlink pointing at {resolved}. Symlinks are not "
            f"followed during ingestion: a link inside a watched folder would "
            f"pull content from outside it into the corpus, and this workbench "
            f"exists to keep confidential data where it was put."
        )

    size = resolved.stat().st_size
    if size == 0:
        raise ValueError(
            f"{path.name} is empty (0 bytes). Empty documents cannot be chunked or embedded."
        )
    if size > MAX_DOCUMENT_BYTES:
        raise ValueError(
            f"{path.name} is {size / 1024 / 1024:.1f} MB, over the "
            f"{MAX_DOCUMENT_BYTES / 1024 / 1024:.0f} MB ingestion limit. "
            f"The pipeline holds a document's whole extracted text in memory "
            f"and embeds every chunk, so this would take the machine down "
            f"rather than fail. Raise WORKBENCH_MAX_DOCUMENT_MB if the file "
            f"is genuinely needed."
        )


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
    _check_ingestible(file_path)

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
                        image_ids=list(getattr(page, "image_ids", []) or []),
                    ),
                )
            )
            chunk_index += 1
    return chunks
