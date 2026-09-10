"""Tests for build_graph_from_chunks — specifically the cross-chunk
deduplication fix.

Regression test for a real bug found by inspecting a real built graph:
deduplicate_entities() was built and unit-tested but never actually
called by the real ingestion pipeline, so two chunks extracting
differently-worded names for related entities ("P-HS-02" vs "P-HS-02
discharge flange") landed as two separate nodes instead of being
resolved through the dedup pass. Uses a REAL Neo4j instance (same
pattern as test_neo4j_client.py) but MOCKS extract_entities_and_relationships
— this test is about the dedup-and-remap wiring, not about a live LLM
call, and mocking here means it never competes with an actual extraction
job for the same Ollama model.
"""

import pytest

from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "testpassword123"


def _neo4j_reachable() -> bool:
    try:
        from backend.graph.neo4j_client import GraphClient

        client = GraphClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        client.verify_connectivity()
        client.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _neo4j_reachable(),
    reason="Neo4j is not reachable at bolt://localhost:7687 — see test_neo4j_client.py's module docstring.",
)


@pytest.fixture
def client():
    from backend.graph.neo4j_client import GraphClient

    c = GraphClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    c.run_cypher("MATCH (n) DETACH DELETE n")
    yield c
    c.run_cypher("MATCH (n) DETACH DELETE n")
    c.close()


def _chunk(source: str, index: int) -> IngestedChunk:
    return IngestedChunk(
        text=f"chunk text {index}",
        metadata=ChunkMetadata(
            source_document=source, document_type="pdf", page_number=1,
            chunk_index=index, ingestion_date="2026-09-09",
        ),
    )


def test_cross_chunk_duplicate_names_merge_into_one_node(client, monkeypatch):
    """The exact real-world case that surfaced this bug: chunk A
    extracts "P-HS-02", chunk B extracts "P-HS-02 discharge flange" --
    both Equipment. Must end up as ONE node in the graph, not two."""
    import backend.evaluation.build_graph as build_graph_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

    fake_results = {
        "chunk text 0": ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name="P-HS-02", attributes={})],
            relationships=[],
        ),
        "chunk text 1": ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name="P-HS-02 discharge flange", attributes={})],
            relationships=[],
        ),
    }

    def fake_extract(chunk_text, model_id="reasoning-model"):
        return fake_results[chunk_text]

    monkeypatch.setattr(build_graph_module, "extract_entities_and_relationships", fake_extract)

    chunks = [_chunk("incident.pdf", 0), _chunk("incident.pdf", 1)]
    stats = build_graph_module.build_graph_from_chunks(chunks, client, verbose=False)

    assert stats["canonical_entities_after_dedup"] == 1
    assert len(stats["merge_decisions"]) == 1

    rows = client.run_cypher("MATCH (n:Equipment) RETURN count(n) AS c")
    assert rows[0]["c"] == 1  # exactly one node, not two


def test_relationship_endpoints_are_remapped_to_canonical_names(client, monkeypatch):
    """A relationship extracted using the PRE-dedup name must still
    resolve correctly once that name gets merged into a different
    canonical name."""
    import backend.evaluation.build_graph as build_graph_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractedRelationship, ExtractionResult

    fake_results = {
        "chunk text 0": ExtractionResult(
            entities=[
                ExtractedEntity(type="Equipment", name="V-204", attributes={}),
                ExtractedEntity(type="PipelineSegment", name="Mangalore-Hassan", attributes={}),
            ],
            relationships=[
                ExtractedRelationship(**{"from": "V-204", "to": "Mangalore-Hassan", "type": "LOCATED_ON"}),
            ],
        ),
        "chunk text 1": ExtractionResult(
            # A later chunk uses the fuzzy-matchable alias for the SAME
            # equipment -- this entity itself gets merged into "V-204"'s
            # canonical form (whichever survives), but the point being
            # tested is that chunk 0's relationship still resolves.
            entities=[ExtractedEntity(type="Equipment", name="Valve V-204", attributes={})],
            relationships=[],
        ),
    }

    def fake_extract(chunk_text, model_id="reasoning-model"):
        return fake_results[chunk_text]

    monkeypatch.setattr(build_graph_module, "extract_entities_and_relationships", fake_extract)

    chunks = [_chunk("sop.pdf", 0), _chunk("sop.pdf", 1)]
    build_graph_module.build_graph_from_chunks(chunks, client, verbose=False)

    # Whichever name survived as canonical, the LOCATED_ON edge must
    # still connect a real Equipment node to the real PipelineSegment
    # node -- not silently vanish because "V-204" no longer exists
    # under that literal string after dedup.
    rows = client.run_cypher(
        "MATCH (e:Equipment)-[:LOCATED_ON]->(seg:PipelineSegment {segment_name: 'Mangalore-Hassan'}) "
        "RETURN count(*) AS c"
    )
    assert rows[0]["c"] == 1
