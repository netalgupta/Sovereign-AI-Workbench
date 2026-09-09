"""Corpus ingestion harness — walks a directory, ingests every file
through the real pipeline (RAG_SPEC.md §2), embeds every chunk, and
returns a populated VectorStore. Reusable across any accuracy-test
corpus, not specific to MRPL_RAG_Test_Corpus — this is Day 9 "end-to-end
rehearsal" tooling per Aryan.md's own plan, not a one-off script.
"""

import json
import sys
from pathlib import Path

from backend.ingestion.document_ingestion import IngestedChunk, ingest_document
from backend.ingestion.embeddings import embed_texts
from backend.retrieval.vector_store import VectorStore
from backend.tools.vision.ocr_printed import extract_printed_text

# Files this pipeline doesn't ingest as knowledge-base content (ground
# truth/documentation about the corpus, not part of it).
_SKIP_FILENAMES = {"readme.md"}


def _ocr_fn(image_path: str) -> str:
    return extract_printed_text(image_path).full_text


def discover_files(corpus_dir: str) -> list[Path]:
    root = Path(corpus_dir)
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.name.lower() not in _SKIP_FILENAMES
    )


def ingest_corpus(corpus_dir: str, verbose: bool = True) -> tuple[VectorStore, list[IngestedChunk], dict]:
    """Ingest every file in `corpus_dir` into a fresh VectorStore.

    Returns (store, all_chunks, stats). `all_chunks` is the flat list of
    every IngestedChunk across the whole corpus — exposed (not just
    buried inside the store) because graph construction (entity
    extraction per chunk, per-document linking) needs the chunks
    themselves, not just their embeddings. `stats` records per-file
    chunk counts and any file that failed to ingest, so one bad file
    doesn't silently swallow the rest of the corpus.
    """
    store = VectorStore(dim=1024)
    all_chunks: list[IngestedChunk] = []
    stats = {"files": {}, "total_chunks": 0, "errors": {}}

    for file_path in discover_files(corpus_dir):
        rel = str(file_path.relative_to(corpus_dir))
        try:
            chunks = ingest_document(str(file_path), ocr_fn=_ocr_fn)
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole corpus run
            stats["errors"][rel] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[ERROR] {rel}: {exc}", file=sys.stderr)
            continue

        if chunks:
            embeddings = embed_texts([c.text for c in chunks])
            store.add_chunks(chunks, embeddings)
            all_chunks.extend(chunks)

        stats["files"][rel] = len(chunks)
        stats["total_chunks"] += len(chunks)
        if verbose:
            print(f"[OK] {rel}: {len(chunks)} chunks")

    return store, all_chunks, stats


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    store, all_chunks, stats = ingest_corpus(corpus_dir)
    print(json.dumps(stats, indent=2))
    print(f"\nTotal chunks in store: {len(store)}")
