"""Corpus ingestion harness — walks a directory, ingests every file
through the real pipeline (RAG_SPEC.md §2), embeds every chunk, and
returns a populated VectorStore. Reusable across any accuracy-test
corpus, not specific to MRPL_RAG_Test_Corpus — this is Day 9 "end-to-end
rehearsal" tooling per Aryan.md's own plan, not a one-off script.
"""

import json
import sys
from pathlib import Path

from backend.ingestion.boilerplate import detect_boilerplate_sentences
from backend.ingestion.document_ingestion import IngestedChunk, ingest_document, pages_to_chunks
from backend.ingestion.document_types import detect_document_type
from backend.ingestion.embeddings import embed_texts
from backend.ingestion.text_extraction import extract_pages
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


def ingest_corpus_with_boilerplate_removal(
    corpus_dir: str, min_doc_fraction: float = 0.4, verbose: bool = True
) -> tuple[VectorStore, list[IngestedChunk], dict]:
    """Two-pass version of ingest_corpus(): extract every document FIRST
    (pass 1), detect sentences recurring near-verbatim across many
    documents (RAG_SPEC.md §2 boilerplate detection — see
    backend/ingestion/boilerplate.py), then chunk with those sentences
    stripped (pass 2) — never re-extracting (no second OCR/ASR call per
    file; pass 2 reuses pass 1's already-extracted pages).

    Built directly from a measured finding: every PROSE document in this
    corpus ends with a near-identical disclaimer, and fused retrieval
    scores across 9 unrelated questions clustered in a suspiciously
    tight band as a result.

    `min_doc_fraction` defaults to 0.4, not detect_boilerplate_sentences'
    own 0.5 default -- deliberately, and documented here rather than
    silently overridden. Measured directly against this corpus: only 6
    of its 13 files (the DOCX/PDF ones) are prose documents capable of
    carrying a textual disclaimer at all; the XLSX/PNG files have none.
    That caps any real boilerplate sentence's achievable fraction at
    6/13 ~= 0.462, permanently below detect_boilerplate_sentences' 0.5
    default regardless of how clean the sentence-splitting is. 0.4 is
    set below that measured ceiling with headroom, not tuned to hit an
    exact number.
    """
    stats = {"files": {}, "total_chunks": 0, "errors": {}, "boilerplate_sentences": []}

    # Pass 1: extract only, no chunking yet -- every OCR/ASR call happens
    # exactly once, here.
    file_pages: dict[Path, tuple] = {}
    all_document_texts: list[str] = []
    for file_path in discover_files(corpus_dir):
        rel = str(file_path.relative_to(corpus_dir))
        try:
            type_info = detect_document_type(str(file_path))
            pages = extract_pages(
                str(file_path), type_info.detected_type, ocr_fn=_ocr_fn
            )
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole corpus run
            stats["errors"][rel] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[ERROR] {rel}: {exc}", file=sys.stderr)
            continue
        file_pages[file_path] = (type_info, pages)
        # ONE string per DOCUMENT, not per page -- detect_boilerplate_
        # sentences' own contract (see its docstring). Real bug found
        # running this for real: passing page-level texts here (16
        # pages across 13 documents) undercounted a disclaimer that
        # only sits on one page of a multi-page document, since each
        # page was being treated as its own "document" for the presence
        # count, diluting the denominator wrong.
        all_document_texts.append("\n".join(p.text for p in pages if p.text.strip()))

    report = detect_boilerplate_sentences(all_document_texts, min_doc_fraction=min_doc_fraction)
    boilerplate = set(report.boilerplate_sentences)
    stats["boilerplate_sentences"] = report.boilerplate_sentences
    if verbose and boilerplate:
        print(f"Detected {len(boilerplate)} boilerplate sentence(s) "
              f"(>= {min_doc_fraction:.0%} of documents):")
        for s in report.boilerplate_sentences:
            print(f"  [{report.doc_fraction_by_sentence[s]:.0%}] {s[:80]}")

    # Pass 2: chunk with boilerplate stripped, embed, store -- reusing
    # pass 1's extraction, no re-extraction.
    store = VectorStore(dim=1024)
    all_chunks: list[IngestedChunk] = []
    for file_path, (type_info, pages) in file_pages.items():
        rel = str(file_path.relative_to(corpus_dir))
        chunks = pages_to_chunks(
            pages, file_path.name, type_info.detected_type, boilerplate_sentences=boilerplate
        )
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
