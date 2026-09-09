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

from backend.graph.entity_extraction import (
    ExtractedRelationship,
    ExtractionResult,
    deduplicate_entities,
    extract_entities_and_relationships,
)
from backend.graph.neo4j_client import GraphClient
from backend.ingestion.document_ingestion import IngestedChunk


def build_graph_from_chunks(
    chunks: list[IngestedChunk],
    client: GraphClient,
    verbose: bool = True,
) -> dict:
    """Run entity extraction on every chunk, deduplicate entities ACROSS
    THE WHOLE CORPUS, then ingest.

    Real bug this fixes, found only by inspecting a real built graph
    (not by re-reading the code): an earlier version ingested each
    chunk's raw extraction straight into Neo4j immediately, one chunk at
    a time. deduplicate_entities() (GRAPH_SPEC.md §5 step 3) was built
    and unit-tested, but never actually CALLED — Neo4j's own MERGE only
    catches an EXACT string match, so two chunks extracting "P-HS-02"
    and "P-HS-02 discharge flange" (referring to related but
    differently-worded things) landed as two separate Equipment nodes,
    with nothing running the fuzzy/cross-chunk dedup pass at all.
    Deduplication only means something if it runs across every chunk's
    entities together, not one chunk's tiny list in isolation — so this
    now runs extraction for every chunk FIRST, dedupes the accumulated
    list once, and only then ingests, with every relationship/document-
    link reference remapped through deduplicate_entities' name_map to
    whatever name actually survived deduplication.

    Returns stats: per-chunk entity/relationship counts, the corpus-wide
    merge decisions (for the audit log, per GRAPH_SPEC.md §5 step 3 —
    see entity_extraction.py's MergeDecision docstring on why this
    module doesn't write the audit log itself), and any chunk that
    failed extraction (with its error) — one bad chunk must not abort
    graph construction for the rest of the corpus.
    """
    stats = {
        "chunks_processed": 0,
        "total_entities_extracted": 0,
        "total_relationships_extracted": 0,
        "canonical_entities_after_dedup": 0,
        "merge_decisions": [],
        "errors": {},
    }

    chunk_results: list[tuple[IngestedChunk, ExtractionResult]] = []
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

        chunk_results.append((chunk, result))
        stats["chunks_processed"] += 1
        stats["total_entities_extracted"] += len(result.entities)
        stats["total_relationships_extracted"] += len(result.relationships)
        if verbose:
            elapsed = time.time() - start
            print(
                f"[{i+1}/{len(chunks)}] {chunk_id}: "
                f"{len(result.entities)} entities, {len(result.relationships)} rels "
                f"({elapsed:.1f}s)"
            )

    all_entities = [e for _, result in chunk_results for e in result.entities]
    canonical_entities, merge_decisions, name_map = deduplicate_entities(all_entities)
    stats["canonical_entities_after_dedup"] = len(canonical_entities)
    stats["merge_decisions"] = [d.model_dump() for d in merge_decisions]
    if verbose and merge_decisions:
        print(f"\n{len(merge_decisions)} cross-chunk merge decision(s):")
        for d in merge_decisions:
            print(f"  {d.entity_type}: {d.merged_alias!r} -> {d.kept_name!r} ({d.reason})")

    for chunk, result in chunk_results:
        # Only this chunk's OWN entities tell us what type a bare name
        # like "P-HS-02" was extracted as — name_map is keyed by
        # (type, name), so this local lookup is required before it can
        # be consulted for a relationship endpoint.
        name_to_type = {e.name: e.type for e in result.entities}

        remapped_entities = [
            e.model_copy(update={"name": name_map[(e.type, e.name)]}) for e in result.entities
        ]

        remapped_relationships = []
        for r in result.relationships:
            from_type = name_to_type.get(r.from_entity)
            to_type = name_to_type.get(r.to_entity)
            # Both endpoints are always among this chunk's own entities
            # -- extract_entities_and_relationships already guarantees
            # this (it drops any relationship referencing a name that
            # isn't one of the chunk's own valid entities). Guard anyway
            # rather than trust that silently if it's ever called some
            # other way.
            if from_type is None or to_type is None:
                continue
            remapped_relationships.append(
                ExtractedRelationship(
                    **{
                        "from": name_map[(from_type, r.from_entity)],
                        "to": name_map[(to_type, r.to_entity)],
                        "type": r.type,
                    }
                )
            )

        client.ingest_extraction_result(
            ExtractionResult(entities=remapped_entities, relationships=remapped_relationships)
        )
        if remapped_entities:
            client.link_document_to_entities(
                chunk.metadata.source_document,
                chunk.metadata.document_type,
                chunk.metadata.ingestion_date,
                remapped_entities,
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
