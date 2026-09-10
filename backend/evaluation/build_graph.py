"""Phase 2 of graph construction: load already-extracted entities into
Neo4j — GRAPH_SPEC.md §5's dedup step + §4.1's Document-REFERENCES edges.

Deliberately takes pre-computed extraction results (from
extract_corpus.py's JSON Lines checkpoint), not raw chunks needing a
fresh LLM call — this is the cheap, local, infinitely-replayable half of
graph construction, decoupled on purpose from the expensive LLM-calling
half. See extract_corpus.py's module docstring for why that split
exists: rebuilding a lost/reset graph database should cost seconds, not
another 40 minutes of GPU-tied inference.
"""

import sys

from backend.graph.entity_extraction import (
    ExtractedRelationship,
    ExtractionResult,
    deduplicate_entities,
    extract_entities_and_relationships,
)
from backend.graph.neo4j_client import GraphClient
from backend.ingestion.document_ingestion import IngestedChunk


def build_graph_from_extractions(
    chunk_extractions: list[tuple[dict, ExtractionResult]],
    client: GraphClient,
    verbose: bool = True,
) -> dict:
    """Deduplicate entities ACROSS THE WHOLE CORPUS, then ingest into Neo4j.

    `chunk_extractions` is [(chunk_metadata_dict, ExtractionResult), ...]
    — chunk_metadata_dict needs source_document/document_type/
    ingestion_date (extract_corpus.load_extractions() produces exactly
    this shape). No LLM call happens anywhere in this function — it is
    pure local computation (dedup) plus Neo4j writes, safe to re-run as
    many times as needed.

    Real bug this fixes (kept from the version of this function that
    used to also run extraction inline): deduplicate_entities()
    (GRAPH_SPEC.md §5 step 3) was built and unit-tested, but an earlier
    version of the ingestion pipeline never actually CALLED it — Neo4j's
    own MERGE only catches an EXACT string match, so two chunks
    extracting "P-HS-02" and "P-HS-02 discharge flange" landed as two
    separate Equipment nodes. Deduplication only means something if it
    runs across every chunk's entities together, which requires having
    ALL chunks' extractions in hand first — exactly what this function
    receives.

    Returns stats: corpus-wide entity/relationship counts, the merge
    decisions (for the audit log — see MergeDecision's docstring on why
    this module doesn't write the audit log itself).
    """
    stats = {
        "chunks_loaded": len(chunk_extractions),
        "total_entities_extracted": sum(len(r.entities) for _, r in chunk_extractions),
        "total_relationships_extracted": sum(len(r.relationships) for _, r in chunk_extractions),
        "canonical_entities_after_dedup": 0,
        "merge_decisions": [],
    }

    all_entities = [e for _, result in chunk_extractions for e in result.entities]
    canonical_entities, merge_decisions, name_map = deduplicate_entities(all_entities)
    stats["canonical_entities_after_dedup"] = len(canonical_entities)
    stats["merge_decisions"] = [d.model_dump() for d in merge_decisions]
    if verbose and merge_decisions:
        print(f"{len(merge_decisions)} cross-chunk merge decision(s):")
        for d in merge_decisions:
            print(f"  {d.entity_type}: {d.merged_alias!r} -> {d.kept_name!r} ({d.reason})")

    for i, (chunk_meta, result) in enumerate(chunk_extractions):
        name_to_type = {e.name: e.type for e in result.entities}

        remapped_entities = [
            e.model_copy(update={"name": name_map[(e.type, e.name)]}) for e in result.entities
        ]

        remapped_relationships = []
        for r in result.relationships:
            from_type = name_to_type.get(r.from_entity)
            to_type = name_to_type.get(r.to_entity)
            if from_type is None or to_type is None:
                continue  # defensive: extract_entities_and_relationships already guarantees this
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
                chunk_meta["source_document"],
                chunk_meta["document_type"],
                chunk_meta["ingestion_date"],
                remapped_entities,
            )
        if verbose:
            chunk_id = f"{chunk_meta['source_document']}#{chunk_meta['chunk_index']}"
            print(f"[{i+1}/{len(chunk_extractions)}] loaded {chunk_id}")

    return stats


def build_graph_from_chunks(
    chunks: list[IngestedChunk],
    client: GraphClient,
    verbose: bool = True,
) -> dict:
    """Convenience wrapper: extract (expensive, LLM calls) THEN load
    (cheap, local) in one call, for small ad-hoc runs where checkpointing
    to disk isn't worth the extra step (a handful of chunks). For a full
    corpus, prefer extract_corpus.py + build_graph_from_extractions
    separately — see this file's module docstring for why.
    """
    chunk_extractions: list[tuple[dict, ExtractionResult]] = []
    errors: dict[str, str] = {}

    for i, chunk in enumerate(chunks):
        chunk_id = f"{chunk.metadata.source_document}#{chunk.metadata.chunk_index}"
        try:
            result = extract_entities_and_relationships(chunk.text)
        except Exception as exc:  # noqa: BLE001 — one bad chunk must not abort the run
            errors[chunk_id] = f"{type(exc).__name__}: {exc}"
            if verbose:
                print(f"[{i+1}/{len(chunks)}] ERROR {chunk_id}: {exc}", file=sys.stderr)
            continue

        chunk_meta = {
            "source_document": chunk.metadata.source_document,
            "document_type": chunk.metadata.document_type,
            "ingestion_date": chunk.metadata.ingestion_date,
            "chunk_index": chunk.metadata.chunk_index,
        }
        chunk_extractions.append((chunk_meta, result))
        if verbose:
            print(
                f"[{i+1}/{len(chunks)}] {chunk_id}: "
                f"{len(result.entities)} entities, {len(result.relationships)} rels"
            )

    stats = build_graph_from_extractions(chunk_extractions, client, verbose=verbose)
    stats["errors"] = errors
    return stats


if __name__ == "__main__":
    import json

    from backend.evaluation.extract_corpus import load_extractions

    extractions_path = sys.argv[1] if len(sys.argv) > 1 else "backend/evaluation/extraction_cache/mrpl_extractions.jsonl"
    neo4j_uri = sys.argv[2] if len(sys.argv) > 2 else "bolt://localhost:7687"
    neo4j_user = sys.argv[3] if len(sys.argv) > 3 else "neo4j"
    neo4j_password = sys.argv[4] if len(sys.argv) > 4 else "testpassword123"

    print(f"Loading cached extractions from {extractions_path}...")
    chunk_extractions = load_extractions(extractions_path)
    print(f"{len(chunk_extractions)} chunk extractions loaded (zero LLM calls made).\n")

    client = GraphClient(neo4j_uri, neo4j_user, neo4j_password)
    graph_stats = build_graph_from_extractions(chunk_extractions, client)
    client.close()

    print("\n=== Graph load stats ===")
    print(json.dumps(graph_stats, indent=2))
