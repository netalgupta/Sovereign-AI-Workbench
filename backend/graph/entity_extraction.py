"""Entity/relationship extraction for the knowledge graph — GRAPH_SPEC.md §5.

Runs each ingested chunk through the reasoning sub-agent with an
extraction prompt, validates the result against GRAPH_SPEC.md's fixed
entity/relationship type lists (§3, §4), and deduplicates entities so
"V-204" and "v204" don't become two separate graph nodes.
"""

import json
from typing import Literal

import requests
from pydantic import BaseModel, Field

from backend.models.registry import resolve_model_name
from backend.utils.llm_output import strip_code_fences

from backend.utils.loopback import require_loopback

# Same check as ollama_client: an endpoint is validated where it is
# built, so a second module cannot become the one that talks off-box.
_OLLAMA_HOST = require_loopback("http://localhost:11434", what="entity extraction host")

# Exact per GRAPH_SPEC.md §3/§4 — these are the ONLY valid values. §5's
# extraction prompt deliberately only asks for 4 of the 6 node types
# (Document and MaintenanceRecord are created by the ingestion pipeline
# and the SAP connector respectively, never extracted from free text —
# see GRAPH_SPEC.md §3's own per-type source column) and 5 of the 7
# relationship types (SUPERSEDES is a revision-tracking relationship
# derived from document metadata, not chunk text; MAINTENANCE_PERFORMED_ON
# is SAP-sourced, same as MaintenanceRecord itself).
VALID_ENTITY_TYPES = ["Equipment", "PipelineSegment", "Person", "Incident"]

# deduplicate_entities' fuzzy-match tier requires a normalized name to be
# at least this long to participate in substring-containment matching --
# see the real bug this fixes in deduplicate_entities' inline comment.
MIN_FUZZY_MATCH_LENGTH = 3
VALID_RELATIONSHIP_TYPES = [
    "REFERENCES", "APPLIES_TO", "LOCATED_ON", "AUTHORED_BY", "REPORTS_INCIDENT_AT",
]

# GRAPH_SPEC.md §4's relationship table, as executable domain/range
# constraints: {type: (allowed FROM types, allowed TO types)}.
#
# WHY THIS EXISTS. The validation below already checked that a
# relationship's TYPE string is legal, that both endpoint NAMES refer to
# entities that survived validation, and that it isn't self-referential
# — but never that the endpoints are the right KINDS of thing for that
# relationship. Measured against the real 21-chunk extraction cache,
# 8 of 11 extracted relationships violated the spec's own table and
# passed straight through: Equipment "LOCATED_ON" an Incident (three
# separate times), Incident "REPORTS_INCIDENT_AT" another Incident,
# PipelineSegment "APPLIES_TO" an Incident. LOCATED_ON in particular was
# being used by the model as a generic "is associated with".
#
# This is also the direct cause of the signature query returning no
# related incidents: GRAPH_SPEC.md §6's query looks for
# (inc:Incident)-[:REPORTS_INCIDENT_AT]->(seg), while the Hassan
# incident had been extracted as Incident-[LOCATED_ON]->Equipment —
# wrong type AND wrong domain, so it matched nothing.
#
# Violations are DROPPED, never auto-corrected. Rewriting a wrong
# LOCATED_ON into a plausible REPORTS_INCIDENT_AT would be inferring a
# relationship the text may not support, which is exactly what §5's
# extraction prompt forbids. Dropping loses information; guessing
# invents it, and an invented edge is indistinguishable downstream from
# a real one.
RELATIONSHIP_DOMAIN_RANGE: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "REFERENCES": (frozenset({"Document"}), frozenset({"Equipment", "PipelineSegment"})),
    "APPLIES_TO": (frozenset({"Document"}), frozenset({"Equipment", "PipelineSegment"})),
    "LOCATED_ON": (frozenset({"Equipment"}), frozenset({"PipelineSegment"})),
    "AUTHORED_BY": (frozenset({"Document"}), frozenset({"Person"})),
    "REPORTS_INCIDENT_AT": (
        frozenset({"Incident"}), frozenset({"Equipment", "PipelineSegment"})
    ),
}

# Verbatim per GRAPH_SPEC.md §5 — do not paraphrase. Built as a fixed
# prefix + chunk_text concatenation, NOT str.format(): the prompt's own
# JSON-schema description contains literal { } characters (e.g.
# {"type": ...}), which .format() would try to parse as placeholders —
# a real bug caught by actually running this, not by reading it.
_EXTRACTION_PROMPT_PREFIX = (
    'Extract entities and relationships from the text below. Output ONLY a JSON '
    'object with two keys: "entities" (list of {"type": one of '
    '["Equipment","PipelineSegment","Person","Incident"], "name": string, '
    '"attributes": object}) and "relationships" (list of {"from": string, "to": '
    'string, "type": one of ["LOCATED_ON","REPORTS_INCIDENT_AT"]}).\n\n'
    'A relationship is only valid between specific entity types. These are the '
    'ONLY two valid combinations:\n'
    '  - "LOCATED_ON": from an Equipment to a PipelineSegment (physical association)\n'
    '  - "REPORTS_INCIDENT_AT": from an Incident to an Equipment or a PipelineSegment\n\n'
    'If a connection you notice does not fit one of those two combinations exactly, '
    'omit it. Do not substitute a different relationship type to express it, and do '
    'not reverse the direction to make it fit. An omitted relationship is correct; '
    'a wrongly-typed one is not.\n\n'
    'Only extract what is explicitly stated in the text. Do not infer relationships '
    'that are not directly supported by the text.\n\n'
    'TEXT:\n'
)
# WHY THIS DEPARTS FROM GRAPH_SPEC.md §5's VERBATIM PROMPT (deliberate,
# measured, and the spec should be updated to match — see the A/B in
# backend/evaluation/extraction_prompt_ab.py):
#
# §5's prompt offers the model all five extractable relationship types,
# but three of them — REFERENCES, APPLIES_TO, AUTHORED_BY — have
# `Document` as their domain per §4's table, and `Document` is
# deliberately NOT in VALID_ENTITY_TYPES (§3: Document nodes are created
# by the ingestion pipeline, never extracted from chunk text). So those
# three types are STRUCTURALLY IMPOSSIBLE to extract validly: there is
# no code path by which a chunk-level extraction can produce a legal
# one. Offering them anyway is not neutral — it actively invites misuse.
# Measured on the real 21-chunk corpus with the original prompt, 8 of 11
# relationships violated §4's domain/range table, and the single most
# common failure was the model reaching for an impossible type
# (APPLIES_TO from an Equipment, LOCATED_ON into an Incident) to express
# an association that had no legal representation available to it.
#
# Naming only the two achievable combinations, and saying explicitly
# that omission beats a wrong type, addresses the cause rather than
# filtering the symptom downstream. The domain/range validation in
# RELATIONSHIP_DOMAIN_RANGE stays regardless — defense in depth, since a
# model can still emit a wrong pairing however the prompt is worded.


def _build_extraction_prompt(chunk_text: str) -> str:
    return _EXTRACTION_PROMPT_PREFIX + chunk_text


class ExtractedEntity(BaseModel):
    type: Literal["Equipment", "PipelineSegment", "Person", "Incident"]
    name: str
    attributes: dict = Field(default_factory=dict)


class ExtractedRelationship(BaseModel):
    from_entity: str = Field(alias="from")
    to_entity: str = Field(alias="to")
    type: Literal["REFERENCES", "APPLIES_TO", "LOCATED_ON", "AUTHORED_BY", "REPORTS_INCIDENT_AT"]

    model_config = {"populate_by_name": True}


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]


class MergeDecision(BaseModel):
    """A non-trivial (not exact-normalized) entity merge, surfaced for
    the audit log — GRAPH_SPEC.md §5 step 3: "do not silently merge on a
    fuzzy-match threshold without logging the merge decision." This
    module produces the record; it does NOT write to the audit log
    itself (TOOLS.md item 45, Aditya's ownership per Aditya.md — outside
    this module's lane). The caller wires this into the real audit
    logger once that exists.
    """

    kept_name: str
    merged_alias: str
    entity_type: str
    reason: str


def _call_extraction_model(prompt: str, model_name: str) -> str:
    response = requests.post(
        f"{_OLLAMA_HOST}/api/generate",
        json={"model": model_name, "prompt": prompt, "stream": False},
        # 240s: qwen2.5:14b at Q4_K_M is ~8-9GB, tight on an 8GB card --
        # DEPENDENCIES.md §1 already documents this needs partial CPU
        # offload of a few layers, which is inherently much slower than
        # full GPU residency. A trivial one-word prompt measured at 45s
        # on this exact machine (nvidia-smi showing 95% GPU utilization
        # at the time -- genuinely computing, not hung); a full
        # extraction prompt over a real 512-token chunk is longer still.
        # 120s was already too tight even before accounting for any
        # concurrent load on the machine.
        timeout=240,
    )
    response.raise_for_status()
    return response.json()["response"]


def extract_entities_and_relationships(
    chunk_text: str, model_id: str = "reasoning-model"
) -> ExtractionResult:
    """Extract entities/relationships from one chunk of text.

    `model_id` is a registry id (per CARD 01/03's pattern), resolved to
    the real Ollama model tag via models.yaml — never hardcoded, per
    CLAUDE.md hard constraint #2.

    Validates every extracted `type` against GRAPH_SPEC.md's fixed
    lists; anything outside them is DROPPED, not raised on — a model
    hallucinating an extra type should degrade gracefully, same
    philosophy as CARD 03's router.

    Raises:
        ValueError: if the model's response isn't parseable JSON at all
            (unlike CARD 03, this has no retry — extraction runs over an
            entire ingestion corpus; retrying every parse failure would
            be expensive at scale. A caller ingesting many chunks should
            catch this per-chunk and skip, not abort the whole corpus).
    """
    model_name = resolve_model_name(model_id)
    prompt = _build_extraction_prompt(chunk_text)
    raw = _call_extraction_model(prompt, model_name)
    cleaned = strip_code_fences(raw)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse extraction output as JSON: {raw!r}") from exc

    raw_entities = parsed.get("entities", [])
    raw_relationships = parsed.get("relationships", [])

    valid_entities = []
    for entry in raw_entities:
        if entry.get("type") not in VALID_ENTITY_TYPES:
            continue  # drop, don't invent a new label — GRAPH_SPEC.md §5 step 2
        valid_entities.append(ExtractedEntity(**entry))

    valid_names = {e.name for e in valid_entities}
    entity_types = {e.name: e.type for e in valid_entities}
    valid_relationships = []
    for entry in raw_relationships:
        if entry.get("type") not in VALID_RELATIONSHIP_TYPES:
            continue
        # A relationship referencing an entity that got dropped above
        # (invalid type) would point at nothing real — drop it too.
        if entry.get("from") not in valid_names or entry.get("to") not in valid_names:
            continue
        # Self-referential relationships are always hallucinated noise,
        # not real content — none of the 5 valid relationship types are
        # ever reflexive (a valve doesn't apply to itself). Found this
        # exact case in a real model's raw output while sanity-checking
        # this function against qwen2.5:7b: it produced
        # {"from": "Valve V-204", "to": "Valve V-204", "type": "APPLIES_TO"}
        # alongside otherwise-correct extractions — both endpoints and
        # the type were individually valid, so without this check it
        # would have silently passed straight through.
        if entry.get("from") == entry.get("to"):
            continue
        # Endpoint TYPES must match GRAPH_SPEC.md §4's domain/range for
        # this relationship type — see RELATIONSHIP_DOMAIN_RANGE above
        # for the real violations this catches and why they are dropped
        # rather than corrected.
        allowed_from, allowed_to = RELATIONSHIP_DOMAIN_RANGE[entry["type"]]
        if (
            entity_types.get(entry["from"]) not in allowed_from
            or entity_types.get(entry["to"]) not in allowed_to
        ):
            continue
        valid_relationships.append(ExtractedRelationship(**entry))

    return ExtractionResult(entities=valid_entities, relationships=valid_relationships)


def _normalize_name(name: str) -> str:
    """Lowercase and strip every non-alphanumeric character.

    Real bug this fixes, found by actually testing GRAPH_SPEC.md §5's
    own worked example: the spec's literal instruction says
    "case-insensitive, whitespace-trimmed", but "V-204" and "v204" don't
    differ by case or whitespace at all — they differ by a HYPHEN. A
    normalizer that only lowercases and trims whitespace never merges
    them, which means it would fail the spec's own definition-of-done.
    Stripping ALL non-alphanumeric characters (not just whitespace) is
    what actually achieves "V-204" == "v204" == "v-204", and this is the
    correct reading of the spec's intent, not a deviation from it — the
    stated example is the actual requirement; the prose describing it
    was simply incomplete.
    """
    return "".join(ch for ch in name.lower() if ch.isalnum())


def deduplicate_entities(
    entities: list[ExtractedEntity],
) -> tuple[list[ExtractedEntity], list[MergeDecision], dict[tuple[str, str], str]]:
    """Merge duplicate entities — GRAPH_SPEC.md §5 step 3.

    Two tiers, matching the spec's own two-tier language:
    1. Exact match after normalization (see _normalize_name) — merged
       silently, unambiguous, no audit entry needed.
    2. Substring containment after normalization ("v204" is contained in
       "valvev204") — the spec's own worked example ("Valve V-204"
       merging with "V-204") needs exactly this, since even the
       stronger normalization above can't equate two strings of
       different length. This tier is the "fuzzy-match" the spec allows
       but requires logging for — every such merge produces a
       MergeDecision.
    Only merges entities of the SAME `type` — never lets a Person and an
    Equipment merge just because their name strings happen to overlap.

    Also returns `name_map`: {(type, original_name): canonical_name} for
    EVERY input entity, not just the ones that got merged. Real gap this
    closes, found while wiring this function into the actual ingestion
    pipeline for the first time (it was built and unit-tested here, but
    nothing had ever called it for real): callers need to remap
    relationship endpoints and document-link references from whatever
    per-chunk name the LLM used to the canonical name this function
    picked, or a relationship extracted as {"from": "V-204", ...} would
    fail to find "V-204" once the graph only has a node named "Valve
    V-204". Returning just the deduplicated entity list was never enough
    to actually use this function correctly.
    """
    canonical: list[ExtractedEntity] = []
    merge_decisions: list[MergeDecision] = []
    name_map: dict[tuple[str, str], str] = {}

    for entity in entities:
        norm = _normalize_name(entity.name)

        exact_match = next(
            (c for c in canonical if _normalize_name(c.name) == norm and c.type == entity.type),
            None,
        )
        if exact_match is not None:
            name_map[(entity.type, entity.name)] = exact_match.name
            continue

        fuzzy_match = None
        # Real bug found running this against the full MRPL corpus, not
        # a hypothetical: a garbage single-letter entity ("N", extraction
        # noise from OCR'd diagram text) has normalized form "n" -- a
        # substring of nearly anything, including "mangalorehassan"
        # (which contains the letter n). With no length guard, that
        # "N" PipelineSegment entity fuzzy-merged straight into the
        # canonical "Mangalore-Hassan" node, and the P&ID diagram it
        # came from got a spurious REFERENCES edge to a pipeline segment
        # it has nothing to do with. MIN_FUZZY_MATCH_LENGTH excludes
        # exactly this failure mode while still allowing the spec's own
        # worked example ("v204", 4 characters) to match correctly.
        if len(norm) >= MIN_FUZZY_MATCH_LENGTH:
            fuzzy_match = next(
                (
                    c
                    for c in canonical
                    if c.type == entity.type
                    and len(_normalize_name(c.name)) >= MIN_FUZZY_MATCH_LENGTH
                    and (norm in _normalize_name(c.name) or _normalize_name(c.name) in norm)
                ),
                None,
            )
        if fuzzy_match is not None:
            merge_decisions.append(
                MergeDecision(
                    kept_name=fuzzy_match.name,
                    merged_alias=entity.name,
                    entity_type=entity.type,
                    reason="substring match after case/whitespace normalization",
                )
            )
            name_map[(entity.type, entity.name)] = fuzzy_match.name
            continue

        canonical.append(entity)
        name_map[(entity.type, entity.name)] = entity.name

    return canonical, merge_decisions, name_map
