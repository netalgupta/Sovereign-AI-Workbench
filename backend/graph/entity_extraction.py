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

_OLLAMA_HOST = "http://localhost:11434"

# Exact per GRAPH_SPEC.md §3/§4 — these are the ONLY valid values. §5's
# extraction prompt deliberately only asks for 4 of the 6 node types
# (Document and MaintenanceRecord are created by the ingestion pipeline
# and the SAP connector respectively, never extracted from free text —
# see GRAPH_SPEC.md §3's own per-type source column) and 5 of the 7
# relationship types (SUPERSEDES is a revision-tracking relationship
# derived from document metadata, not chunk text; MAINTENANCE_PERFORMED_ON
# is SAP-sourced, same as MaintenanceRecord itself).
VALID_ENTITY_TYPES = ["Equipment", "PipelineSegment", "Person", "Incident"]
VALID_RELATIONSHIP_TYPES = [
    "REFERENCES", "APPLIES_TO", "LOCATED_ON", "AUTHORED_BY", "REPORTS_INCIDENT_AT",
]

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
    'string, "type": one of '
    '["REFERENCES","APPLIES_TO","LOCATED_ON","AUTHORED_BY","REPORTS_INCIDENT_AT"]}). '
    'Only extract what is explicitly stated in the text. Do not infer relationships '
    'that are not directly supported by the text.\n\n'
    'TEXT:\n'
)


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
        # 120s, not 60s: a real run of the live test against the actual
        # 14B reasoning model took 61s in isolation and timed out when
        # run as part of the full suite (CPU inference under contention
        # from other tests running back to back) -- 60s was already
        # marginal even in the best case, not a safe margin at all.
        timeout=120,
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
) -> tuple[list[ExtractedEntity], list[MergeDecision]]:
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
    """
    canonical: list[ExtractedEntity] = []
    merge_decisions: list[MergeDecision] = []

    for entity in entities:
        norm = _normalize_name(entity.name)

        exact_match = next(
            (c for c in canonical if _normalize_name(c.name) == norm and c.type == entity.type),
            None,
        )
        if exact_match is not None:
            continue

        fuzzy_match = next(
            (
                c
                for c in canonical
                if c.type == entity.type
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
            continue

        canonical.append(entity)

    return canonical, merge_decisions
