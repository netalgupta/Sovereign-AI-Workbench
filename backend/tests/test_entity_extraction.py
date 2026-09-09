"""Tests for extract_entities_and_relationships and deduplicate_entities.

Split the same way test_router.py is: mocked-HTTP plumbing tests that
run every time, offline, plus one honest skip-if-unavailable live-model
test — qwen2.5:14b (models.yaml's reasoning-model) isn't pulled on this
dev machine's Ollama (see router.py's history for the same situation),
so faking a "correct" mocked extraction for that test would prove
nothing real.
"""

import responses

from backend.graph.entity_extraction import (
    MergeDecision,
    VALID_ENTITY_TYPES,
    VALID_RELATIONSHIP_TYPES,
    ExtractedEntity,
    deduplicate_entities,
    extract_entities_and_relationships,
)

GENERATE_URL = "http://localhost:11434/api/generate"


def _mock_generate(payload: dict):
    import json as json_module

    responses.add(responses.POST, GENERATE_URL, json={"response": json_module.dumps(payload)}, status=200)


@responses.activate
def test_valid_extraction_round_trips():
    _mock_generate(
        {
            "entities": [
                {"type": "Equipment", "name": "Valve V-204", "attributes": {}},
                {"type": "PipelineSegment", "name": "Mangalore-Hassan", "attributes": {}},
            ],
            "relationships": [
                {"from": "Valve V-204", "to": "Mangalore-Hassan", "type": "LOCATED_ON"},
            ],
        }
    )

    result = extract_entities_and_relationships("some SOP text")

    assert len(result.entities) == 2
    assert result.entities[0].name == "Valve V-204"
    assert len(result.relationships) == 1
    assert result.relationships[0].type == "LOCATED_ON"


@responses.activate
def test_invalid_entity_type_is_dropped_not_raised():
    _mock_generate(
        {
            "entities": [
                {"type": "Equipment", "name": "Pump P-1", "attributes": {}},
                {"type": "MadeUpType", "name": "Something", "attributes": {}},  # hallucinated type
            ],
            "relationships": [],
        }
    )

    result = extract_entities_and_relationships("text")

    assert len(result.entities) == 1
    assert result.entities[0].name == "Pump P-1"
    assert all(e.type in VALID_ENTITY_TYPES for e in result.entities)


@responses.activate
def test_relationship_referencing_a_dropped_entity_is_also_dropped():
    _mock_generate(
        {
            "entities": [{"type": "Equipment", "name": "Pump P-1", "attributes": {}}],
            "relationships": [
                # "Ghost Entity" was never a valid entity -- this
                # relationship must not silently point at nothing.
                {"from": "Pump P-1", "to": "Ghost Entity", "type": "LOCATED_ON"},
            ],
        }
    )

    result = extract_entities_and_relationships("text")

    assert result.relationships == []


@responses.activate
def test_self_referential_relationship_is_dropped():
    """Regression test for a REAL hallucination observed running this
    against qwen2.5:7b: the model produced a self-loop relationship
    (Valve V-204 -> Valve V-204, type APPLIES_TO) that passes both the
    type-validity check AND the endpoint-existence check individually --
    only an explicit from == to check catches it."""
    _mock_generate(
        {
            "entities": [{"type": "Equipment", "name": "Valve V-204", "attributes": {}}],
            "relationships": [
                {"from": "Valve V-204", "to": "Valve V-204", "type": "APPLIES_TO"},
            ],
        }
    )

    result = extract_entities_and_relationships("text")

    assert result.relationships == []


@responses.activate
def test_invalid_relationship_type_is_dropped():
    _mock_generate(
        {
            "entities": [
                {"type": "Equipment", "name": "A", "attributes": {}},
                {"type": "Equipment", "name": "B", "attributes": {}},
            ],
            "relationships": [{"from": "A", "to": "B", "type": "MADE_UP_RELATIONSHIP"}],
        }
    )

    result = extract_entities_and_relationships("text")

    assert result.relationships == []
    assert all(r.type in VALID_RELATIONSHIP_TYPES for r in result.relationships)


@responses.activate
def test_unparseable_response_raises_value_error():
    responses.add(responses.POST, GENERATE_URL, json={"response": "not json at all"}, status=200)

    import pytest

    with pytest.raises(ValueError, match="Could not parse extraction output"):
        extract_entities_and_relationships("text")


# --- deduplicate_entities: pure logic, no network at all ---

def _entity(name: str, type_: str = "Equipment") -> ExtractedEntity:
    return ExtractedEntity(type=type_, name=name, attributes={})


def test_exact_normalized_duplicate_merges_silently():
    entities = [_entity("V-204"), _entity("v204")]

    canonical, decisions = deduplicate_entities(entities)

    assert len(canonical) == 1
    assert decisions == []  # unambiguous case-only match needs no audit entry


def test_the_specs_own_worked_example():
    # GRAPH_SPEC.md §5's literal example: "V-204", "v204", "Valve V-204"
    # must all resolve to one node.
    entities = [_entity("V-204"), _entity("v204"), _entity("Valve V-204")]

    canonical, decisions = deduplicate_entities(entities)

    assert len(canonical) == 1
    # "Valve V-204" is NOT an exact case/whitespace match for "V-204" --
    # merging it required the substring-containment tier, which must be
    # logged.
    assert len(decisions) == 1
    assert isinstance(decisions[0], MergeDecision)
    assert decisions[0].merged_alias == "Valve V-204"


def test_different_entity_types_never_merge_even_if_names_overlap():
    entities = [_entity("V-204", type_="Equipment"), _entity("V-204", type_="PipelineSegment")]

    canonical, decisions = deduplicate_entities(entities)

    assert len(canonical) == 2
    assert decisions == []


def test_genuinely_distinct_entities_stay_separate():
    entities = [_entity("Valve V-204"), _entity("Pump P-1"), _entity("Compressor C-9")]

    canonical, decisions = deduplicate_entities(entities)

    assert len(canonical) == 3
    assert decisions == []


# --- live-model test, honest skip if the configured model isn't pulled ---

import pytest  # noqa: E402
import requests  # noqa: E402


def _reasoning_model_pulled() -> bool:
    from backend.models.registry import resolve_model_name

    try:
        model_name = resolve_model_name("reasoning-model")
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        response.raise_for_status()
        pulled = {entry["name"] for entry in response.json().get("models", [])}
        return model_name in pulled
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return False


@pytest.mark.skipif(
    not _reasoning_model_pulled(),
    reason=(
        "models.yaml's reasoning-model (qwen2.5:14b) is not pulled on this "
        "Ollama instance — skipping the live extraction test rather than "
        "mocking a fake 'correct' response. Run `ollama pull qwen2.5:14b` "
        "to exercise this for real."
    ),
)
def test_live_extraction_against_the_configured_reasoning_model():
    text = (
        "Valve V-204, located on the Mangalore-Hassan pipeline segment, was "
        "inspected on schedule with no anomalies found."
    )

    result = extract_entities_and_relationships(text)

    names = {e.name for e in result.entities}
    assert any("V-204" in name for name in names)
    assert all(e.type in VALID_ENTITY_TYPES for e in result.entities)
    assert all(r.type in VALID_RELATIONSHIP_TYPES for r in result.relationships)
    assert all(r.from_entity != r.to_entity for r in result.relationships)
