"""Ollama health check + model pull verification — VIBECODING_SPEC.md CARD 02.

Confirms every model named in the registry has actually been pulled into
the local Ollama instance before the orchestrator tries to call it. This
is a purely local HTTP call to localhost:11434 — no outbound network call
per CLAUDE.md hard constraint #1.
"""

import requests

from backend.models.registry import ModelConfig


def verify_models_available(
    registry: dict[str, ModelConfig],
    ollama_host: str = "http://localhost:11434",
) -> dict[str, bool]:
    """Check which registry models are actually pulled in the local Ollama.

    Raises:
        ConnectionError: if `ollama_host` is unreachable. Message is exactly
            f"Ollama not reachable at {ollama_host} — is it running?" —
            never retried silently, never falls back to a different host.
    """
    try:
        response = requests.get(f"{ollama_host}/api/tags", timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        raise ConnectionError(f"Ollama not reachable at {ollama_host} — is it running?")

    pulled_models = {entry["name"] for entry in response.json().get("models", [])}

    return {
        model_id: config.model in pulled_models
        for model_id, config in registry.items()
    }
