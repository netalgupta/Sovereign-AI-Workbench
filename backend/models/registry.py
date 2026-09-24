"""Model registry loader — VIBECODING_SPEC.md CARD 01.

Reads /models/models.yaml (or a given path) into validated ModelConfig
entries keyed by id. This is the ONLY place a model name may be read from
config in the orchestration layer — per CLAUDE.md hard constraint #2, no
model name is ever hardcoded in router/orchestrator logic. Adding a model
is an edit to the YAML file + a registry reload, never a code change (FR-4).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class Placement(BaseModel):
    """Where an in-process model's weights go. WE decide, not a scheduler.

    Layers fill the GPU up to `gpu_memory_gib`; the rest spill to system
    RAM up to `cpu_memory_gib` and are streamed to the GPU as they run.
    Loading fails rather than exceeding both budgets. Ollama offers no
    equivalent: it estimates a model's footprint itself and, for
    Qwen2.5-VL, places every layer on the CPU regardless of num_gpu.
    """

    gpu_memory_gib: float
    cpu_memory_gib: float
    # "4bit"/"8bit" quantize with bitsandbytes at load; "none" loads fp16.
    quantization: Literal["none", "4bit", "8bit"] = "none"
    # Upper bound on image resolution handed to the vision encoder, in
    # pixels. Image tokens scale with area; this caps activation memory.
    max_image_pixels: int = 960 * 540


class ModelConfig(BaseModel):
    id: str
    # "ollama": a tag served by the local Ollama daemon.
    # "diffusers": weights in models/image/ on disk, loaded in-process by
    #   Hugging Face diffusers with the Hub forced offline -- the image
    #   model. Ollama cannot serve image generation.
    # "transformers": weights in models/vision/ on disk, loaded in-process
    #   by Hugging Face transformers with an explicit GPU/CPU `placement`.
    backend: Literal["ollama", "diffusers", "transformers"]
    model: str
    task_tags: list[str]
    placement: Placement | None = None


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


_WEIGHTS_CATEGORY = {"diffusers": "image", "transformers": "vision"}


def weights_dir(config: ModelConfig) -> Path:
    """Where an in-process model's weights live: models/<category>/<org>__<name>."""
    from backend.ingestion.model_cache import local_cache_dir

    if config.backend not in _WEIGHTS_CATEGORY:
        raise ValueError(f"{config.id} is served by {config.backend}, not loaded from disk")
    return local_cache_dir(_WEIGHTS_CATEGORY[config.backend], config.model)


def diffusers_weights_dir(config: ModelConfig) -> Path:
    """Where a diffusers model's weights live: models/image/<org>__<name>."""
    return weights_dir(config)


def quantized_weights_dir(config: ModelConfig) -> Path | None:
    """Where a quantized entry's prepared copy lives, or None if it has none."""
    if config.backend != "transformers" or config.placement is None:
        return None
    if config.placement.quantization == "none":
        return None
    full = weights_dir(config)
    return full.with_name(f"{full.name}.{config.placement.quantization}")


def fetch_command(config: ModelConfig) -> str:
    """The one-time, online command that puts this model on disk."""
    if config.backend == "ollama":
        return f"ollama pull {config.model}"
    return f"python -m backend.ingestion.fetch_models --model {config.model}"


def is_locally_available(config: ModelConfig, pulled_ollama_tags: set[str] | None) -> bool | None:
    """Is this model usable on this machine right now?

    None when that cannot be known (Ollama unreachable, for an Ollama
    entry). Every place that lists models asks this, rather than assuming
    every entry is an Ollama tag -- which would tell the operator to run
    `ollama pull stabilityai/sd-turbo`.
    """
    if config.backend == "diffusers":
        return (weights_dir(config) / "model_index.json").exists()
    if config.backend == "transformers":
        # A PREPARED (quantized) copy is enough on its own. Once
        # local_vision --prepare has written it, the full-precision download
        # can be deleted -- it is 16 GB against the copy's 6 GB -- and the
        # model still loads. Checking only the full weights reported a
        # usable reviewer as "not pulled".
        prepared = quantized_weights_dir(config)
        if prepared is not None and (prepared / "DONE").exists() and any(prepared.glob("*.safetensors")):
            return True
        # Every shard the index names, not merely "some safetensors": a
        # half-finished download must not read as available.
        d = weights_dir(config)
        index = d / "model.safetensors.index.json"
        if not (d / "config.json").exists():
            return False
        if index.exists():
            import json

            shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
            return all((d / s).exists() for s in shards)
        return (d / "model.safetensors").exists()
    if pulled_ollama_tags is None:
        return None
    return config.model in pulled_ollama_tags or f"{config.model}:latest" in pulled_ollama_tags
