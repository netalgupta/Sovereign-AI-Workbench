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


# ---------------------------------------------------------------------
# Single call site for text generation — added alongside the CARD 02
# health check above, which is unrelated and must stay.
#
# WHY THIS EXISTS. Four modules (generation, verification, router,
# planner) each hand-rolled their own requests.post to /api/generate
# with an inlined json body. Any option that must apply everywhere had
# to be remembered four times, and the next call site would have made
# it five.
#
# THE OPTION THAT PROMPTED IT: num_gpu.
#
# A previous measurement in this repo concluded num_gpu "does nothing on
# this box — the model is placed entirely on CPU regardless", and the
# parameter was kept only as a no-op for venue hardware. That conclusion
# was WRONG. Re-measured on an IDLE GPU (0 MiB used of 8188),
# qwen2.5:14b:
#
#     num_gpu unset  ->   26%/74% CPU/GPU    8.7 tok/s
#     num_gpu=20     ->   55%/45% CPU/GPU    4.3 tok/s
#     num_gpu=99     ->   100% GPU           9.1 tok/s
#
# The earlier run had other models resident (phi3.5 ~4 GB, qwen2.5vl
# ~6 GB), so almost no VRAM was free and Ollama fell back to CPU. The
# measurement was of VRAM CONTENTION and was read as a property of the
# flag — the same self-deceiving-measurement class already recorded
# twice in this repo: the number was real, what it was a number ABOUT
# was not.
#
# Note num_gpu=20 is WORSE than unset: forcing a layer count overrides
# Ollama's own fit calculation. It is 99 (all layers) or nothing.
#
# VRAM DISCIPLINE: 100% GPU for a 9 GB model on an 8 GB card holds only
# while nothing else is resident. keep_alive is left at Ollama's default
# so an idle model releases VRAM for the next one — sequential routing
# is fine, concurrent multi-model use is not, which is what CLAUDE.md
# already requires.
# ---------------------------------------------------------------------
import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GENERATE_URL = f"{OLLAMA_HOST}/api/generate"

# All layers on the GPU when they fit; Ollama falls back to a split, and
# then to CPU, when they do not. Overridable for venue hardware or for
# reproducing a CPU-only run.
DEFAULT_NUM_GPU = int(os.environ.get("WORKBENCH_NUM_GPU", "99"))

DEFAULT_TIMEOUT = int(os.environ.get("WORKBENCH_LLM_TIMEOUT", "600"))


def default_options() -> dict:
    return {"num_gpu": DEFAULT_NUM_GPU}


def generate(
    model_name: str,
    prompt: str,
    *,
    timeout: int | None = None,
    options: dict | None = None,
    **kwargs,
) -> str:
    """Non-streaming completion. Returns the response text.

    Args:
        model_name: a REAL model tag, already resolved through the
            registry. This function deliberately does not resolve
            registry ids: doing so here would make it the second place
            that maps ids to tags, and hard constraint #2 wants exactly
            one.
        options: merged over the defaults, so a caller can override
            num_gpu or add temperature without losing the rest.

    Raises for HTTP errors rather than returning a default -- a caller
    that silently treats an unreachable model as an empty answer is how
    a dead verifier passed for weeks.
    """
    merged = default_options()
    if options:
        merged.update(options)

    response = requests.post(
        GENERATE_URL,
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": merged,
            **kwargs,
        },
        timeout=timeout or DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["response"]
