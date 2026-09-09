"""Model registry loader — VIBECODING_SPEC.md CARD 01.

Reads /models/models.yaml (or a given path) into validated ModelConfig
entries keyed by id. This is the ONLY place a model name may be read from
config in the orchestration layer — per CLAUDE.md hard constraint #2, no
model name is ever hardcoded in router/orchestrator logic. Adding a model
is an edit to the YAML file + a registry reload, never a code change (FR-4).
"""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ModelConfig(BaseModel):
    id: str
    backend: Literal["ollama"]
    model: str
    task_tags: list[str]


def load_registry(path: str = "/models/models.yaml") -> dict[str, ModelConfig]:
    """Load and validate the model registry YAML at `path`.

    Raises:
        FileNotFoundError: if `path` does not exist. Message is exactly
            f"Model registry not found at {path}" — never a silently
            returned empty dict.
        pydantic.ValidationError: if any entry is malformed. Propagated
            unmodified — never caught and suppressed.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_entries = yaml.safe_load(f) or []
    except FileNotFoundError:
        raise FileNotFoundError(f"Model registry not found at {path}")

    registry: dict[str, ModelConfig] = {}
    for entry in raw_entries:
        config = ModelConfig(**entry)
        registry[config.id] = config
    return registry


# The actual on-disk models.yaml for THIS repo (not the CARD 01 function
# default above, which is an absolute container-style path that only
# makes sense inside the eventual Docker deployment). Resolved once,
# relative to this file's own location, so every caller in this repo
# gets the same answer regardless of current working directory.
_DEFAULT_REGISTRY_PATH = str(Path(__file__).resolve().parents[2] / "models" / "models.yaml")


def resolve_model_name(model_id: str, registry_path: str | None = None) -> str:
    """Resolve a registry id (e.g. "fast-router") to the real backend
    model tag (e.g. "phi-3.5-mini") it maps to in models.yaml.

    Extracted here (not left duplicated in router.py) once a second
    caller — entity_extraction.py — needed the exact same resolution.
    Originally written as a bug fix inside router.py: CARD 03's
    router_model_id is a registry id, not an Ollama model tag, and
    passing the id straight to Ollama 404s (Ollama has no model literally
    named "fast-router"). See router.py's history for the full story.

    Args:
        model_id: a registry id, e.g. "reasoning-model" or "fast-router".
        registry_path: override for testing; defaults to (in order) the
            MODELS_REGISTRY_PATH env var, then this repo's real
            models.yaml.

    Raises:
        ValueError: if `model_id` isn't in the registry.
    """
    path = registry_path or os.environ.get("MODELS_REGISTRY_PATH", _DEFAULT_REGISTRY_PATH)
    registry = load_registry(path)
    if model_id not in registry:
        raise ValueError(f"Unknown model id {model_id!r} — not found in registry at {path}")
    return registry[model_id].model
