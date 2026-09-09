"""Build the knowledge graph from an already-ingested corpus's chunks
— GRAPH_SPEC.md §5, entity extraction, tied to per-document REFERENCES
edges (§4.1's bridge, §6's signature query target).

Per-chunk entity extraction over a real 14B model on CPU is slow (~60-
120s/chunk observed) — this writes progress to stdout as it goes and is
meant to be run in the background for anything beyond a handful of
chunks, not blocked on interactively.
"""

import sys
import time

from backend.graph.entity_extraction import extract_entities_and_relationships
from backend.graph.neo4j_client import GraphClient
from backend.ingestion.document_ingestion import IngestedChunk


def build_graph_from_chunks(
    chunks: list[IngestedChunk],
    client: GraphClient,
    verbose: bool = True,
) -> dict:
    """Run entity extraction on every chunk and ingest the results,
    including per-document REFERENCES edges (link_document_to_entities).

    Returns stats: per-chunk entity/relationship counts and any chunk
    that failed extraction (with its error) — one bad chunk must not
    abort graph construction for the rest of the corpus.
    """
    stats = {"chunks_processed": 0, "total_entities": 0, "total_relationships": 0, "errors": {}}

    for i, chunk in enumerate(chunks):
        chunk_id = f"{chunk.metadata.source_document}#{chunk.metadata.chunk_index}"
        start = time.time()
        try:
            result = extract_entities_and_relationships(chunk.text)
        except Exception as exc:  # noqa: BLE001 — one bad chunk must not abort the run
            stats["errors"][chunk_id] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[{i+1}/{len(chunks)}] ERROR {chunk_id}: {exc}", file=sys.stderr)
            continue

        client.ingest_extraction_result(result)
        if result.entities:
            client.link_document_to_entities(
                chunk.metadata.source_document,
                chunk.metadata.document_type,
                chunk.metadata.ingestion_date,
                result.entities,
            )

        stats["chunks_processed"] += 1
        stats["total_entities"] += len(result.entities)
        stats["total_relationships"] += len(result.relationships)
        if verbose:
            elapsed = time.time() - start
            print(
                f"[{i+1}/{len(chunks)}] {chunk_id}: "
                f"{len(result.entities)} entities, {len(result.relationships)} rels "
                f"({elapsed:.1f}s)"
            )

    return stats


if __name__ == "__main__":
    import json

    from backend.evaluation.ingest_corpus import ingest_corpus

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    neo4j_uri = sys.argv[2] if len(sys.argv) > 2 else "bolt://localhost:7687"
    neo4j_user = sys.argv[3] if len(sys.argv) > 3 else "neo4j"
    neo4j_password = sys.argv[4] if len(sys.argv) > 4 else "testpassword123"

    print(f"Ingesting corpus from {corpus_dir}...")
    _, all_chunks, ingest_stats = ingest_corpus(corpus_dir, verbose=True)
    print(f"\n{len(all_chunks)} chunks to process for graph extraction.\n")

    client = GraphClient(neo4j_uri, neo4j_user, neo4j_password)
    graph_stats = build_graph_from_chunks(all_chunks, client)
    client.close()

    print("\n=== Graph build stats ===")
    print(json.dumps(graph_stats, indent=2))
