"""Experiment: does a smaller chunk size improve retrieval precision?

Deliberately NOT a change to chunking.py's production defaults —
RAG_SPEC.md §2 step 3 locks 512 tokens/64 overlap specifically so
retrieval-quality comparisons stay meaningful across the corpus,
and the same file says any change "requires... document any change to
it in this file", i.e. a deliberate spec update, not a silent swap.
This module builds a SEPARATE, parallel ingestion path with a
configurable chunk size purely to measure whether shrinking it would
help, before ever considering changing the locked default.

Overlap is scaled proportionally with chunk size (12.5% of chunk size,
matching 512's 64-token overlap ratio) since the request only specified
chunk size — stated explicitly here as the assumption it is.
"""

import sys

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.ingestion.chunking import TIKTOKEN_ENCODING
from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
from backend.ingestion.document_types import detect_document_type
from backend.ingestion.text_extraction import extract_pages
from backend.ingestion.embeddings import embed_texts
from backend.retrieval.vector_store import VectorStore
from backend.tools.vision.ocr_printed import extract_printed_text


def _ocr_fn(image_path: str) -> str:
    return extract_printed_text(image_path).full_text


def ingest_document_with_chunk_size(file_path: str, chunk_size_tokens: int) -> list[IngestedChunk]:
    import datetime
    from pathlib import Path

    overlap = max(1, round(chunk_size_tokens * 0.125))
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=TIKTOKEN_ENCODING, chunk_size=chunk_size_tokens, chunk_overlap=overlap,
    )

    type_info = detect_document_type(file_path)
    pages = extract_pages(file_path, type_info.detected_type, ocr_fn=_ocr_fn)

    source_document = Path(file_path).name
    ingestion_date = datetime.date.today().isoformat()

    chunks: list[IngestedChunk] = []
    chunk_index = 0
    for page in pages:
        if not page.text.strip():
            continue
        for piece in splitter.split_text(page.text):
            chunks.append(
                IngestedChunk(
                    text=piece,
                    metadata=ChunkMetadata(
                        source_document=source_document, document_type=type_info.detected_type,
                        page_number=page.page_number, chunk_index=chunk_index,
                        ingestion_date=ingestion_date,
                    ),
                )
            )
            chunk_index += 1
    return chunks


def ingest_corpus_with_chunk_size(corpus_dir: str, chunk_size_tokens: int) -> VectorStore:
    from backend.evaluation.ingest_corpus import discover_files

    store = VectorStore(dim=1024)
    for file_path in discover_files(corpus_dir):
        chunks = ingest_document_with_chunk_size(str(file_path), chunk_size_tokens)
        if chunks:
            embeddings = embed_texts([c.text for c in chunks])
            store.add_chunks(chunks, embeddings)
    return store


if __name__ == "__main__":
    import json

    from backend.evaluation.precision_at_k import run_precision_analysis

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"
    chunk_size = int(sys.argv[3]) if len(sys.argv) > 3 else 256

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"Ingesting corpus at chunk_size={chunk_size} tokens...")
    store = ingest_corpus_with_chunk_size(corpus_dir, chunk_size)
    print(f"{len(store)} chunks (vs. 21 at the default 512-token size).\n")

    analysis = run_precision_analysis(store, questions, k=5)
    print(json.dumps(analysis, indent=2))
