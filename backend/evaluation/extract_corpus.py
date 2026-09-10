"""Phase 1 of graph construction: entity extraction ONLY, checkpointed
to a durable JSON file on disk.

WHY THIS IS A SEPARATE STEP FROM LOADING THE GRAPH (real lesson, paid
for directly): an earlier version of this pipeline ran extraction and
Neo4j ingestion in one pass, with no checkpoint in between. When the
sandbox environment this was developed in got recycled mid-session,
Neo4j's container (which had no persistent volume either -- a second,
related gap) came back with zero data, and the ~40 minutes of real LLM
compute that produced it was gone with no way to recover it except
paying for it again. That's a real, direct cost of coupling "expensive,
slow, irreplaceable" (the LLM calls) to "fragile, ephemeral" (an
unpersisted graph database container).

This file does ONLY the expensive part, and writes every result to disk
as it goes (not just at the end) -- so even a crash mid-run loses at
most the one chunk in flight, not the whole run. Loading that JSON into
Neo4j (build_graph.py's `build_graph_from_extractions`) is fast, local,
and infinitely replayable: if the graph database dies for any reason,
rebuilding it costs seconds, not 40 minutes of GPU-tied inference.
"""

import json
import sys
import time
from pathlib import Path

from backend.graph.entity_extraction import ExtractionResult, extract_entities_and_relationships
from backend.ingestion.document_ingestion import IngestedChunk


def _completed_chunk_ids(output_path: str) -> set[str]:
    """Chunk ids already present in an existing checkpoint file, so a
    resumed run never re-pays for (or duplicates) work already done.
    """
    if not Path(output_path).exists():
        return set()
    ids = set()
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            ids.add(f"{record['source_document']}#{record['chunk_index']}")
    return ids


def extract_corpus(
    chunks: list[IngestedChunk],
    output_path: str,
    verbose: bool = True,
    resume: bool = True,
) -> dict:
    """Run entity extraction over every chunk, writing each result to
    `output_path` incrementally (one JSON object per line — JSON Lines,
    not a single JSON array) as soon as it's produced.

    JSON Lines specifically, not a single array: a single JSON array
    isn't valid until the closing `]` is written, so a crash mid-run
    would corrupt the entire file, not just lose the in-flight chunk.
    Appending one complete, independently-parseable line per chunk means
    every chunk that finished before a crash is still safely readable.

    `resume=True` (default): if `output_path` already has results for
    some chunks (e.g. a prior run that got 17/21 before hitting transient
    Ollama 500s and a malformed-JSON response on the other 4 — a real
    case this was built to handle, not hypothetical), skip those and
    APPEND only the missing ones — never re-pay for or duplicate
    already-successful extraction. `resume=False` truncates and starts
    clean, for when you deliberately want to redo everything.
    """
    stats = {"chunks_processed": 0, "total_entities": 0, "total_relationships": 0, "errors": {}}

    already_done = _completed_chunk_ids(output_path) if resume else set()
    pending = [
        c for c in chunks
        if f"{c.metadata.source_document}#{c.metadata.chunk_index}" not in already_done
    ]
    if verbose and already_done:
        print(f"Resuming: {len(already_done)} chunk(s) already in {output_path}, "
              f"{len(pending)} remaining.")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    file_mode = "a" if (resume and already_done) else "w"
    with open(output_path, file_mode, encoding="utf-8") as f:
        for i, chunk in enumerate(pending):
            chunk_id = f"{chunk.metadata.source_document}#{chunk.metadata.chunk_index}"
            start = time.time()
            try:
                result = extract_entities_and_relationships(chunk.text)
            except Exception as exc:  # noqa: BLE001 — one bad chunk must not abort the run
                stats["errors"][chunk_id] = f"{type(exc).__name__}: {exc}"
                if verbose:
                    print(f"[{i+1}/{len(pending)}] ERROR {chunk_id}: {exc}", file=sys.stderr)
                continue

            record = {
                "source_document": chunk.metadata.source_document,
                "document_type": chunk.metadata.document_type,
                "ingestion_date": chunk.metadata.ingestion_date,
                "chunk_index": chunk.metadata.chunk_index,
                "extraction": result.model_dump(by_alias=True),
            }
            f.write(json.dumps(record) + "\n")
            f.flush()  # durable as soon as one chunk finishes, not just at process exit

            stats["chunks_processed"] += 1
            stats["total_entities"] += len(result.entities)
            stats["total_relationships"] += len(result.relationships)
            if verbose:
                elapsed = time.time() - start
                print(
                    f"[{i+1}/{len(pending)}] {chunk_id}: "
                    f"{len(result.entities)} entities, {len(result.relationships)} rels "
                    f"({elapsed:.1f}s)"
                )

    return stats


def load_extractions(path: str) -> list[tuple[dict, ExtractionResult]]:
    """Read back a JSON Lines file written by extract_corpus().

    Returns [(chunk_metadata_dict, ExtractionResult), ...] — the chunk
    metadata dict has source_document/document_type/ingestion_date/
    chunk_index, everything build_graph.py's link_document_to_entities
    needs, without requiring the original IngestedChunk objects (whose
    `.text` isn't even needed anymore at this stage).
    """
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            chunk_meta = {
                "source_document": record["source_document"],
                "document_type": record["document_type"],
                "ingestion_date": record["ingestion_date"],
                "chunk_index": record["chunk_index"],
            }
            results.append((chunk_meta, ExtractionResult(**record["extraction"])))
    return results


if __name__ == "__main__":
    from backend.evaluation.ingest_corpus import ingest_corpus

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/extraction_cache/mrpl_extractions.jsonl"

    print(f"Ingesting corpus from {corpus_dir}...")
    _, all_chunks, ingest_stats = ingest_corpus(corpus_dir, verbose=False)
    print(f"{len(all_chunks)} chunks to extract. Writing incrementally to {output_path}.\n")

    stats = extract_corpus(all_chunks, output_path)
    print("\n=== Extraction stats ===")
    print(json.dumps(stats, indent=2))
