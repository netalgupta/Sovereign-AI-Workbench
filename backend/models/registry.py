"""Model registry loader — VIBECODING_SPEC.md CARD 01.

Reads /models/models.yaml (or a given path) into validated ModelConfig
entries keyed by id. This is the ONLY place a model name may be read from
config in the orchestration layer — per CLAUDE.md hard constraint #2, no
model name is ever hardcoded in router/orchestrator logic. Adding a model
is an edit to the YAML file + a registry reload, never a code change (FR-4).
"""

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
