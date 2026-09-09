# GRAPH_SPEC.md — Complete Knowledge Graph Specification

## 1. Purpose
Plain vector retrieval cannot answer "show every SOP referencing this valve" or "what maintenance records and incident reports touch the Hassan pumping station segment" — these are graph-shaped questions. This document specifies the exact schema so the graph is buildable without guesswork.

## 2. Storage Choice
**Locked: Neo4j Community Edition.** Cypher query language, mature visualization tooling, and this is now the only graph backend implemented — no NetworkX fallback path to build or maintain. Every Cypher example in this document is the actual implementation target, not a placeholder.

**Hard constraint, verified by actually running the default Docker image:** Neo4j's default config sends anonymous usage telemetry on every startup — its own log prints "Anonymous Usage Data is being sent to Neo4j" unless disabled. This is exactly the kind of default phone-home behavior CLAUDE.md's hard constraint #1 requires auditing every dependency for. It is NOT disabled by default — whoever builds the real `docker-compose.yml` (SYSTEM.md §5 / DEPENDENCIES.md §10) MUST set `NEO4J_dbms_usage__report_enabled=false` as an environment variable on the Neo4j container. Confirmed fixed: the exact same container with this flag set produces a clean startup log with no telemetry line at all.

## 3. Node Types (exact labels, do not invent variants)

| Label | Properties | Example |
|---|---|---|
| `Document` | `id`, `filename`, `document_type`, `ingestion_date` | SOP-114-Rev3.pdf |
| `Equipment` | `id`, `tag`, `unit` (e.g. "Hydrocracker-2", "CCR-1"), `equipment_type` (valve, pump, vessel, etc.) | Valve V-204 |
| `PipelineSegment` | `id`, `segment_name`, `start_point`, `end_point` | "Mangalore-Hassan" |
| `Person` | `id`, `name`, `role` (extracted from correspondence/sign-off blocks only — never inferred) | — |
| `Incident` | `id`, `date`, `severity`, `summary` | — |
| `MaintenanceRecord` | `id`, `date`, `equipment_ref`, `action_taken` | from SAP Maintenance module data via the SAP connector |

## 4. Relationship Types (exact labels)

| Relationship | From → To | Meaning |
|---|---|---|
| `REFERENCES` | `Document` → `Equipment` / `PipelineSegment` | The document mentions this entity |
| `SUPERSEDES` | `Document` → `Document` | Revision N supersedes revision N-1 |
| `APPLIES_TO` | `Document` → `Equipment` / `PipelineSegment` | The SOP's scope explicitly covers this entity (stronger than REFERENCES — extracted from explicit "applicability" sections, not just mentions) |
| `LOCATED_ON` | `Equipment` → `PipelineSegment` | Physical association |
| `AUTHORED_BY` | `Document` → `Person` | Sign-off/authorship |
| `REPORTS_INCIDENT_AT` | `Incident` → `Equipment` / `PipelineSegment` | — |
| `MAINTENANCE_PERFORMED_ON` | `MaintenanceRecord` → `Equipment` | From SAP-sourced data |

## 5. Entity Extraction Pipeline (how nodes/edges get created during ingestion)

1. After chunking (per RAG_SPEC.md §2), run each chunk through a local LLM extraction prompt (use the reasoning sub-agent, `qwen2.5:14b`) with this exact instruction:
```
Extract entities and relationships from the text below. Output ONLY a JSON object with two keys: "entities" (list of {"type": one of ["Equipment","PipelineSegment","Person","Incident"], "name": string, "attributes": object}) and "relationships" (list of {"from": string, "to": string, "type": one of ["REFERENCES","APPLIES_TO","LOCATED_ON","AUTHORED_BY","REPORTS_INCIDENT_AT"]}). Only extract what is explicitly stated in the text. Do not infer relationships that are not directly supported by the text.

TEXT:
{chunk_text}
```
2. Validate extracted `type` values against the fixed lists above — drop anything that doesn't match rather than inventing a new label on the fly
3. Deduplicate entities by normalized name matching (case-insensitive, whitespace-trimmed) before creating new nodes — e.g. "V-204", "v204", "Valve V-204" should resolve to one node; maintain an alias list per entity for this matching, do not silently merge on a fuzzy-match threshold without logging the merge decision to the audit log
4. Create/merge nodes and relationships via Cypher `MERGE` statements (never plain `CREATE`, to avoid duplicate nodes across ingestion runs)

## 6. The Signature Demo Query (implement exactly this, it is the centerpiece graph demo)

**Natural language:** "Show every SOP that references this pipeline segment, and every incident report tied to it."

**Cypher:**
```cypher
MATCH (seg:PipelineSegment {segment_name: $segment_name})
OPTIONAL MATCH (doc:Document)-[:REFERENCES|APPLIES_TO]->(seg)
OPTIONAL MATCH (inc:Incident)-[:REPORTS_INCIDENT_AT]->(seg)
RETURN seg, collect(DISTINCT doc) AS related_documents, collect(DISTINCT inc) AS related_incidents
```

**Demo parameter to use:** `segment_name: "Mangalore-Hassan"` — this is a real named segment of MRPL's actual 363km Petronet MHB pipeline per the MRPL-Grounded Dossier, making the query concrete rather than a toy example with invented data.

**Frontend behavior:** the Graph Explorer (FRONTEND.md §3.6) must visibly highlight the returned subgraph — center the view on `seg`, animate-in the connected `doc` and `inc` nodes, do not just print a text list. The visual "the graph lights up" moment is the actual demo payload, not the underlying Cypher.

## 7. Testing Requirements
- Fixture: a small set of mock SOPs/incident reports mentioning a test pipeline segment and at least 2 equipment tags
- Test asserts: entity extraction correctly identifies the segment and equipment nodes; the signature query returns the expected document/incident set; a document mentioning an entity only in passing (not in an "applicability" section) creates a `REFERENCES` edge, not an `APPLIES_TO` edge — this distinction must be tested explicitly, since collapsing it would misrepresent SOP scope, which matters in a safety context

## 8. Anti-Hallucination Note (graph-specific)
The extraction prompt in §5 explicitly forbids inferring relationships not directly stated in the text. If a document merely mentions a valve tag in passing without an explicit applicability statement, the correct edge is `REFERENCES`, never `APPLIES_TO` — do not let the extraction model or any post-processing step upgrade a passing mention into a scope claim. This distinction is safety-relevant, not pedantic.
