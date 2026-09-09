"""Task router / classifier — VIBECODING_SPEC.md CARD 03.

Classifies a user request into a set of fixed task tags via the local
fast-router model (phi-3.5-mini via Ollama). This is the ONLY place the
valid task-tag vocabulary is defined — do not invent new tags (e.g.
"math", "vision") anywhere else without updating this list, models.yaml,
and TOOLS.md in the same change (per this card's anti-hallucination note).

Known open gap (flagged, not silently resolved): REQUIREMENTS.md FR-3
describes the router's accuracy test set as spanning "code / summarization
/ vision / math", but there is no "math" tag in VALID_TASK_TAGS below and
this card explicitly forbids inventing one. A math-shaped request cannot
be represented by this function's output today — see the note left in
CLAUDE.md discussion / commit message. This must be resolved (either drop
"math" from FR-3's literal test-set description, or add a documented tag
here + a documented mapping to AgentState.PlanStep.assigned_agent's "math"
value in AGENTS_SPEC.md) before the 20-prompt accuracy test can honestly
claim to cover FR-3 as written.
"""

import json
import os
import re
from pathlib import Path

import requests

from backend.models.registry import load_registry

# Bug found only by actually running this against a live Ollama: CARD 03's
# `router_model_id` is a registry ID ("fast-router"), not an Ollama model
# tag. Ollama has no model literally named "fast-router" — the real tag is
# whatever models.yaml maps that id to (e.g. "phi-3.5-mini"). Resolve
# through the registry (CARD 01) instead of passing the id straight through.
_DEFAULT_REGISTRY_PATH = str(Path(__file__).resolve().parents[2] / "models" / "models.yaml")


def _resolve_model_name(router_model_id: str) -> str:
    registry_path = os.environ.get("MODELS_REGISTRY_PATH", _DEFAULT_REGISTRY_PATH)
    registry = load_registry(registry_path)
    if router_model_id not in registry:
        raise ValueError(
            f"Unknown model id {router_model_id!r} — not found in registry at {registry_path}"
        )
    return registry[router_model_id].model


VALID_TASK_TAGS = [
    "code_generation",
    "code_review",
    "debugging",
    "summarization",
    "drafting",
    "approval_notes",
    "planning",
    "ocr",
    "image_understanding",
    "diagram_reading",
]

_OLLAMA_HOST = "http://localhost:11434"

_PROMPT_TEMPLATE = (
    'You are a task classifier. Given the user\'s request, output ONLY a JSON array '
    'of task tags from this exact list: ["code_generation", "code_review", "debugging", '
    '"summarization", "drafting", "approval_notes", "planning", "ocr", '
    '"image_understanding", "diagram_reading"]. Output nothing except the JSON array. '
    'If multiple tags apply, include all of them.\n\n'
    'User request: {user_input}'
)

_RETRY_SUFFIX = "\nOutput ONLY the JSON array, no other text."

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    match = _FENCE_PATTERN.match(text)
    return match.group(1).strip() if match else text


def _call_router_model(prompt: str, model_name: str) -> str:
    response = requests.post(
        f"{_OLLAMA_HOST}/api/generate",
        json={"model": model_name, "prompt": prompt, "stream": False},
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        # Ollama puts the actually-useful detail (e.g. "model 'x' not
        # found") in a JSON body that raise_for_status() discards —
        # surface it instead of a bare "404 Client Error".
        try:
            detail = response.json().get("error")
        except ValueError:
            detail = None
        if detail:
            raise requests.exceptions.HTTPError(f"{exc} — {detail}", response=response) from exc
        raise
    return response.json()["response"]


def classify_task(user_input: str, router_model_id: str = "fast-router") -> list[str]:
    """Classify `user_input` into a list of valid task tags.

    `router_model_id` is a registry id (see CARD 01), resolved to an actual
    Ollama model tag via models.yaml before calling Ollama.

    Raises:
        ValueError: exactly f"Router could not classify: {user_input!r}"
            if the model's response still isn't parseable JSON after one
            retry with a stricter instruction appended.
    """
    model_name = _resolve_model_name(router_model_id)
    prompt = _PROMPT_TEMPLATE.format(user_input=user_input)
    raw = _call_router_model(prompt, model_name)

    tags = _try_parse(raw)
    if tags is None:
        raw_retry = _call_router_model(prompt + _RETRY_SUFFIX, model_name)
        tags = _try_parse(raw_retry)

    if tags is None:
        raise ValueError(f"Router could not classify: {user_input!r}")

    # A router hallucinating an extra tag degrades gracefully (dropped),
    # it does not crash the pipeline.
    return [tag for tag in tags if tag in VALID_TASK_TAGS]


def _try_parse(raw: str) -> list[str] | None:
    cleaned = _strip_code_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None
