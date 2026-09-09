"""Neo4j graph store client — GRAPH_SPEC.md §2-§6.

Owns: node/relationship creation via MERGE (never CREATE, per §5 step 4
— CREATE would duplicate nodes across ingestion runs), and §6's
signature demo query. Connection details are passed in, never hardcoded
(same "no hardcoded infra config" spirit as CLAUDE.md rule #2, applied
to a database instead of a model).
"""

from typing import Any

from neo4j import GraphDatabase
from pydantic import BaseModel

from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

# §3's full fixed label set — Document and MaintenanceRecord are never
# produced by entity_extraction.py (see that module's own comment on
# why), but a generic merge_node still needs to validate against all 6,
# since Document nodes ARE created here (see link_chunk_to_graph).
VALID_NODE_LABELS = [
    "Document", "Equipment", "PipelineSegment", "Person", "Incident", "MaintenanceRecord",
]

# §4's full fixed relationship set, including the 2 entity_extraction.py
# never produces (SUPERSEDES: document-revision metadata, not chunk
# text; MAINTENANCE_PERFORMED_ON: SAP-sourced).
VALID_RELATIONSHIP_TYPES = [
    "REFERENCES", "SUPERSEDES", "APPLIES_TO", "LOCATED_ON",
    "AUTHORED_BY", "REPORTS_INCIDENT_AT", "MAINTENANCE_PERFORMED_ON",
]

# GRAPH_SPEC.md §4.1's extraction-to-schema bridge — see that section for
# the full reasoning on why this mapping exists and why each choice was
# made. Keeping this table here (not duplicated) and referencing it from
# the doc, rather than the reverse, since this file is the executable
# source of truth.
_ENTITY_TYPE_KEY_PROPERTY = {
    "Equipment": "tag",
    "PipelineSegment": "segment_name",
    "Person": "name",
    "Incident": "summary",
}


class SignatureQueryResult(BaseModel):
    segment_found: bool
    related_documents: list[str]
    related_incidents: list[str]


class GraphClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def merge_node(self, label: str, key_property: str, key_value: str, properties: dict | None = None) -> None:
        """MERGE a node by (label, key_property=key_value), setting any
        extra `properties` on it. Never CREATE — see module docstring.

        Raises:
            ValueError: if `label` isn't one of GRAPH_SPEC.md §3's fixed
                types. This is a real injection-safety check, not just a
                spec-compliance one: `label` gets interpolated directly
                into the Cypher query text (Neo4j's driver has no
                parameterized-label syntax), so validating it against a
                fixed allowlist before that interpolation matters.
        """
        if label not in VALID_NODE_LABELS:
            raise ValueError(f"Unknown node label {label!r} — not in GRAPH_SPEC.md §3's fixed types")
        properties = properties or {}
        query = f"MERGE (n:{label} {{{key_property}: $key_value}}) SET n += $properties"
        with self._driver.session() as session:
            session.run(query, key_value=key_value, properties=properties)

    def merge_relationship(
        self,
        from_label: str, from_key_property: str, from_key_value: str,
        rel_type: str,
        to_label: str, to_key_property: str, to_key_value: str,
    ) -> None:
        """MERGE a relationship between two already-existing nodes,
        matched by their own key property (not necessarily the same
        property name on both sides — a Document->PipelineSegment
        REFERENCES edge matches `filename` on one side and
        `segment_name` on the other).
        """
        if rel_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown relationship type {rel_type!r} — not in GRAPH_SPEC.md §4's fixed types")
        if from_label not in VALID_NODE_LABELS or to_label not in VALID_NODE_LABELS:
            raise ValueError(f"Unknown node label in ({from_label!r}, {to_label!r})")

        query = (
            f"MATCH (a:{from_label} {{{from_key_property}: $from_value}}), "
            f"(b:{to_label} {{{to_key_property}: $to_value}}) "
            f"MERGE (a)-[r:{rel_type}]->(b)"
        )
        with self._driver.session() as session:
            session.run(query, from_value=from_key_value, to_value=to_key_value)

    def merge_extracted_entity(self, entity: ExtractedEntity) -> None:
        """merge_node, using GRAPH_SPEC.md §4.1's bridge to pick the
        right key property for this entity's type."""
        key_property = _ENTITY_TYPE_KEY_PROPERTY[entity.type]
        self.merge_node(entity.type, key_property, entity.name, entity.attributes)

    def ingest_extraction_result(self, result: ExtractionResult) -> None:
        """Merge every entity, then every relationship, from one
        chunk's extraction result. Entities first, always — a
        relationship's MATCH clause requires both endpoint nodes to
        already exist, or it silently matches nothing and merges no
        relationship at all (Cypher's MATCH doesn't error on zero
        matches, it just returns no rows).
        """
        entities_by_name: dict[str, ExtractedEntity] = {}
        for entity in result.entities:
            self.merge_extracted_entity(entity)
            entities_by_name[entity.name] = entity

        for rel in result.relationships:
            from_entity = entities_by_name.get(rel.from_entity)
            to_entity = entities_by_name.get(rel.to_entity)
            if from_entity is None or to_entity is None:
                # Defensive: entity_extraction.py already filters these
                # out before returning, but this function must not
                # trust that blindly if called with hand-built input.
                continue
            self.merge_relationship(
                from_entity.type, _ENTITY_TYPE_KEY_PROPERTY[from_entity.type], from_entity.name,
                rel.type,
                to_entity.type, _ENTITY_TYPE_KEY_PROPERTY[to_entity.type], to_entity.name,
            )

    def link_document_to_entities(
        self, source_document: str, document_type: str, ingestion_date: str, entities: list[ExtractedEntity]
    ) -> None:
        """Create/merge a Document node and a REFERENCES edge from it to
        every entity mentioned in that document — this is the piece that
        makes §6's signature query return anything: that query looks for
        Document nodes connected to a PipelineSegment via
        REFERENCES|APPLIES_TO, and nothing produces those Document nodes
        or edges without this function.

        Always REFERENCES, never APPLIES_TO — per §8's anti-hallucination
        note, a mere chunk mention is never upgraded to a scope claim
        without an explicit "applicability" signal, which this pipeline
        doesn't attempt to detect (a documented, known gap, not a silent
        one — see GRAPH_SPEC.md §8).

        Real bug fixed here, found by actually running this against
        Neo4j: merge_relationship's Cypher does MATCH (not MERGE) on
        both endpoint nodes. If an entity node was never separately
        created (e.g. this is called standalone, not right after
        ingest_extraction_result already merged it), that MATCH silently
        matches zero rows and Cypher creates NO relationship at all —
        no error, no exception, just a graph missing an edge nobody
        notices until the signature query comes back empty. This
        function now merges each entity node itself first, defensively
        and idempotently (MERGE is always safe to repeat), rather than
        trusting the caller already did so elsewhere.
        """
        self.merge_node("Document", "filename", source_document,
                         {"document_type": document_type, "ingestion_date": ingestion_date})
        for entity in entities:
            self.merge_extracted_entity(entity)
            self.merge_relationship(
                "Document", "filename", source_document,
                "REFERENCES",
                entity.type, _ENTITY_TYPE_KEY_PROPERTY[entity.type], entity.name,
            )

    def signature_pipeline_segment_query(self, segment_name: str) -> SignatureQueryResult:
        """GRAPH_SPEC.md §6's signature demo query, verbatim Cypher."""
        query = (
            "MATCH (seg:PipelineSegment {segment_name: $segment_name}) "
            "OPTIONAL MATCH (doc:Document)-[:REFERENCES|APPLIES_TO]->(seg) "
            "OPTIONAL MATCH (inc:Incident)-[:REPORTS_INCIDENT_AT]->(seg) "
            "RETURN seg, collect(DISTINCT doc) AS related_documents, "
            "collect(DISTINCT inc) AS related_incidents"
        )
        with self._driver.session() as session:
            record = session.run(query, segment_name=segment_name).single()

        if record is None or record["seg"] is None:
            return SignatureQueryResult(segment_found=False, related_documents=[], related_incidents=[])

        return SignatureQueryResult(
            segment_found=True,
            related_documents=[doc["filename"] for doc in record["related_documents"] if doc is not None],
            related_incidents=[inc["summary"] for inc in record["related_incidents"] if inc is not None],
        )

    def run_cypher(self, query: str, **params: Any) -> list[dict]:
        """Escape hatch for anything not covered by the typed methods
        above (e.g. GRAPH_SPEC.md §7's test fixtures). Returns plain
        dicts, not neo4j Record objects, so callers/tests don't need the
        driver's types just to make assertions.
        """
        with self._driver.session() as session:
            return [dict(record) for record in session.run(query, **params)]
