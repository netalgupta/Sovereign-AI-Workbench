"""Tests for GraphClient — run against a REAL Neo4j instance, not mocked.

A graph database's actual behavior (MERGE idempotency, relationship
MATCH semantics, Cypher syntax correctness) is exactly the kind of thing
a mock would let slip through wrong. Skips honestly if Neo4j isn't
reachable, same pattern as every other live-service test in this suite.

Start Neo4j for this suite with (usage telemetry disabled — see
GRAPH_SPEC.md §2's dependency-audit finding):
    docker run -d -p 7687:7687 -p 7474:7474 \\
      -e NEO4J_AUTH=neo4j/testpassword123 \\
      -e NEO4J_dbms_usage__report_enabled=false neo4j:5-community
"""

import pytest

from backend.graph.entity_extraction import ExtractedEntity, ExtractedRelationship, ExtractionResult

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
    reason=(
        "Neo4j is not reachable at bolt://localhost:7687 — skipping live graph "
        "tests. See this file's module docstring for the docker run command "
        "(usage telemetry must be disabled per GRAPH_SPEC.md §2)."
    ),
)


@pytest.fixture
def client():
    from backend.graph.neo4j_client import GraphClient

    c = GraphClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    c.run_cypher("MATCH (n) DETACH DELETE n")  # clean slate
    yield c
    c.run_cypher("MATCH (n) DETACH DELETE n")  # leave it clean
    c.close()


def test_merge_node_is_idempotent(client):
    client.merge_node("Equipment", "tag", "V-204", {"unit": "Hydrocracker-2"})
    client.merge_node("Equipment", "tag", "V-204", {"unit": "Hydrocracker-2"})  # merge again

    rows = client.run_cypher("MATCH (n:Equipment {tag: 'V-204'}) RETURN count(n) AS c")

    assert rows[0]["c"] == 1  # MERGE, not CREATE -- must not duplicate


def test_merge_node_sets_properties(client):
    client.merge_node("Equipment", "tag", "V-204", {"unit": "Hydrocracker-2", "equipment_type": "valve"})

    rows = client.run_cypher("MATCH (n:Equipment {tag: 'V-204'}) RETURN n.unit AS unit, n.equipment_type AS t")

    assert rows[0]["unit"] == "Hydrocracker-2"
    assert rows[0]["t"] == "valve"


def test_merge_node_rejects_unknown_label(client):
    with pytest.raises(ValueError, match="Unknown node label"):
        client.merge_node("NotARealLabel", "name", "x")


def test_merge_relationship_rejects_unknown_type(client):
    client.merge_node("Equipment", "tag", "A")
    client.merge_node("Equipment", "tag", "B")
    with pytest.raises(ValueError, match="Unknown relationship type"):
        client.merge_relationship("Equipment", "tag", "A", "NOT_A_REAL_TYPE", "Equipment", "tag", "B")


def test_ingest_extraction_result_creates_nodes_and_relationship(client):
    result = ExtractionResult(
        entities=[
            ExtractedEntity(type="Equipment", name="V-204", attributes={}),
            ExtractedEntity(type="PipelineSegment", name="Mangalore-Hassan", attributes={}),
        ],
        relationships=[
            ExtractedRelationship(**{"from": "V-204", "to": "Mangalore-Hassan", "type": "LOCATED_ON"}),
        ],
    )

    client.ingest_extraction_result(result)

    rows = client.run_cypher(
        "MATCH (e:Equipment {tag: 'V-204'})-[:LOCATED_ON]->(seg:PipelineSegment {segment_name: 'Mangalore-Hassan'}) "
        "RETURN count(*) AS c"
    )
    assert rows[0]["c"] == 1


def test_relationship_to_nonexistent_entity_is_silently_skipped(client):
    # Only ONE entity actually extracted, but a relationship claims to
    # reference a second one that was never in the entities list --
    # ingest_extraction_result must not crash, and must not create a
    # relationship pointing at nothing.
    result = ExtractionResult(
        entities=[ExtractedEntity(type="Equipment", name="V-204", attributes={})],
        relationships=[
            ExtractedRelationship(**{"from": "V-204", "to": "Ghost", "type": "LOCATED_ON"}),
        ],
    )

    client.ingest_extraction_result(result)  # must not raise

    rows = client.run_cypher("MATCH ()-[r:LOCATED_ON]->() RETURN count(r) AS c")
    assert rows[0]["c"] == 0


def test_signature_query_the_actual_demo_scenario(client):
    """GRAPH_SPEC.md §6's literal signature query, built up from the
    pieces a real ingestion run would actually produce."""
    client.link_document_to_entities(
        "SOP-114-Rev3.pdf", "sop", "2026-09-09",
        [ExtractedEntity(type="PipelineSegment", name="Mangalore-Hassan", attributes={})],
    )
    client.merge_node("Incident", "summary", "Valve leak reported near Hassan pumping station")
    client.merge_relationship(
        "Incident", "summary", "Valve leak reported near Hassan pumping station",
        "REPORTS_INCIDENT_AT",
        "PipelineSegment", "segment_name", "Mangalore-Hassan",
    )

    result = client.signature_pipeline_segment_query("Mangalore-Hassan")

    assert result.segment_found is True
    assert "SOP-114-Rev3.pdf" in result.related_documents
    assert "Valve leak reported near Hassan pumping station" in result.related_incidents


def test_signature_query_on_missing_segment(client):
    result = client.signature_pipeline_segment_query("Some-Segment-That-Does-Not-Exist")

    assert result.segment_found is False
    assert result.related_documents == []
    assert result.related_incidents == []


def test_link_document_to_entities_uses_references_never_applies_to(client):
    """GRAPH_SPEC.md §8's anti-hallucination rule: a mere chunk mention
    must be REFERENCES, never upgraded to APPLIES_TO."""
    client.link_document_to_entities(
        "inspection_report.pdf", "inspection_report", "2026-09-09",
        [ExtractedEntity(type="Equipment", name="V-204", attributes={})],
    )

    references = client.run_cypher("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c")
    applies_to = client.run_cypher("MATCH ()-[r:APPLIES_TO]->() RETURN count(r) AS c")

    assert references[0]["c"] == 1
    assert applies_to[0]["c"] == 0
