"""A/B the extraction prompt: GRAPH_SPEC.md §5's original vs the revised
one in entity_extraction.py.

WHY THIS EXISTS. Changing a spec-locked prompt on the strength of "this
looks better to me" is exactly the move that spec-locking is meant to
prevent. The revision has a concrete, falsifiable claim behind it —
that offering the model three structurally-impossible relationship types
(REFERENCES/APPLIES_TO/AUTHORED_BY, whose domain is `Document`, which is
never extracted from chunk text) causes it to misuse them, and that
naming only the two achievable combinations produces more VALID
relationships, not merely fewer invalid ones.

That claim is testable, so it gets tested before the spec is changed.
Both prompts run against the SAME chunks in the SAME process against the
SAME model, and both outputs are scored against GRAPH_SPEC.md §4's
domain/range table by the same function the pipeline uses.

The metric that matters is VALID relationships, not total. A prompt that
produces zero relationships would trivially have a 0% violation rate
while being useless. Both numbers are reported.
"""

import json
import sys
import time

from backend.graph.entity_extraction import (
    RELATIONSHIP_DOMAIN_RANGE,
    VALID_ENTITY_TYPES,
    VALID_RELATIONSHIP_TYPES,
    _call_extraction_model,
)
from backend.models.registry import resolve_model_name
from backend.utils.llm_output import strip_code_fences

# GRAPH_SPEC.md §5 verbatim, preserved here as the A-arm baseline so the
# comparison survives entity_extraction.py's prompt changing again.
_ORIGINAL_PROMPT_PREFIX = (
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


def _score_raw_output(raw: str) -> dict:
    """Parse a raw model response and classify every relationship in it
    against GRAPH_SPEC.md §4, WITHOUT the pipeline's filtering — the
    point is to see what the model actually produced, including what
    validation would have silently discarded."""
    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return {"parse_failed": True, "entities": 0, "valid": 0, "invalid": 0, "violations": []}

    entities = [e for e in parsed.get("entities", []) if e.get("type") in VALID_ENTITY_TYPES]
    types_by_name = {e["name"]: e["type"] for e in entities}

    valid = invalid = 0
    violations = []
    for rel in parsed.get("relationships", []):
        rel_type = rel.get("type")
        if rel_type not in VALID_RELATIONSHIP_TYPES:
            invalid += 1
            violations.append(f"unknown type {rel_type!r}")
            continue
        from_type = types_by_name.get(rel.get("from"))
        to_type = types_by_name.get(rel.get("to"))
        allowed_from, allowed_to = RELATIONSHIP_DOMAIN_RANGE[rel_type]
        if from_type in allowed_from and to_type in allowed_to:
            valid += 1
        else:
            invalid += 1
            violations.append(f"({from_type})-[{rel_type}]->({to_type})")

    return {
        "parse_failed": False,
        "entities": len(entities),
        "valid": valid,
        "invalid": invalid,
        "violations": violations,
    }


def run(chunk_texts: list[str], model_id: str = "reasoning-model") -> dict:
    from backend.graph.entity_extraction import _EXTRACTION_PROMPT_PREFIX as REVISED

    model_name = resolve_model_name(model_id)
    arms = {"original": _ORIGINAL_PROMPT_PREFIX, "revised": REVISED}
    results: dict[str, list] = {"original": [], "revised": []}

    for i, text in enumerate(chunk_texts, start=1):
        for arm, prefix in arms.items():
            started = time.time()
            raw = _call_extraction_model(prefix + text, model_name)
            score = _score_raw_output(raw)
            score["seconds"] = round(time.time() - started, 1)
            results[arm].append(score)
            print(
                f"  chunk {i}/{len(chunk_texts)} [{arm:<8}] "
                f"valid={score['valid']} invalid={score['invalid']} "
                f"({score['seconds']}s)",
                flush=True,
            )

    summary = {}
    for arm, rows in results.items():
        total_valid = sum(r["valid"] for r in rows)
        total_invalid = sum(r["invalid"] for r in rows)
        total = total_valid + total_invalid
        summary[arm] = {
            "chunks": len(rows),
            "relationships_total": total,
            "relationships_valid": total_valid,
            "relationships_invalid": total_invalid,
            "violation_rate": (total_invalid / total) if total else None,
            "parse_failures": sum(1 for r in rows if r["parse_failed"]),
            "all_violations": [v for r in rows for v in r["violations"]],
        }
    summary["per_chunk"] = results
    return summary


if __name__ == "__main__":
    cache_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "backend/evaluation/extraction_cache/mrpl_extractions.jsonl"
    )
    out_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/extraction_prompt_ab.json"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    # Reuse the chunks already captured in the extraction checkpoint —
    # same text the original numbers were measured on, no re-ingestion.
    texts = []
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if record.get("chunk_text"):
                texts.append(record["chunk_text"])
    texts = texts[:limit]

    print(f"A/B over {len(texts)} chunks, 2 prompts each ({len(texts) * 2} model calls)...")
    result = run(texts)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\nWrote {out_path}\n")
    for arm in ("original", "revised"):
        s = result[arm]
        rate = f"{s['violation_rate']:.0%}" if s["violation_rate"] is not None else "n/a"
        print(
            f"{arm:<9} total={s['relationships_total']:>3}  "
            f"valid={s['relationships_valid']:>3}  invalid={s['relationships_invalid']:>3}  "
            f"violation rate={rate}"
        )
