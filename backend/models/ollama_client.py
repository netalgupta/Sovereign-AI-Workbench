from __future__ import annotations

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
import threading

# CHECKED, NOT TRUSTED. Setting OLLAMA_HOST to a remote address used to
# send every model call in the product off the premises -- silently, no
# code change, no warning. The sovereignty claim was resting on the
# default value of an environment variable. See backend/utils/loopback.py.
from backend.utils.loopback import require_loopback

OLLAMA_HOST = require_loopback(
    os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    what="OLLAMA_HOST",
)
GENERATE_URL = f"{OLLAMA_HOST}/api/generate"

# All layers on the GPU when they fit; Ollama falls back to a split, and
# then to CPU, when they do not. Overridable for venue hardware or for
# reproducing a CPU-only run.
DEFAULT_NUM_GPU = int(os.environ.get("WORKBENCH_NUM_GPU", "99"))

# Context for the GENERATION model, sized to the job rather than left at
# Ollama's 4096 default.
#
# WHY IT IS A VRAM DECISION, NOT A QUALITY ONE. A measured grounded
# prompt is ~6800 characters (5 chunks plus instructions), about 2000
# tokens, and the answer adds a few hundred. 3072 covers that with
# headroom. The remaining 1024 tokens of the default window were never
# used -- but their KV cache was allocated and held resident.
#
# That mattered: with generation at 4096 (~5.5 GB) and the verifier at
# 4096 (~4.0 GB), the pair needed ~9.5 GB on an 8.2 GB card, so
# `ollama ps` after every turn showed only the verifier. Both models
# reloaded from scratch on every turn, and one measured turn spiked to
# 127s when the thrash collided with GPU pressure. Unpredictable is
# worse than slow.
#
# If a future change grows the prompt (more chunks, longer
# instructions), raise this deliberately and re-check residency with
# `ollama ps` -- silently overflowing the window truncates the SOURCES
# block, which would drop citations without any error.
# 6144, RAISED FROM 3072 AFTER A SELF-INFLICTED REGRESSION.
#
# 3072 was sized against a measured ~2000-token prompt. Then neighbour
# expansion doubled the number of retrieved chunks (5 -> 10, by design:
# it repairs procedures truncated at a chunk boundary), and the same
# prompt became 2986 tokens against a 3072 window.
#
# It did not overflow, which is what made it hard to see. It left ~86
# tokens for the answer. When the window fills, Ollama drops from the
# START of the prompt -- and the retrieved value sat at token 57. The
# model was answering from a prompt whose grounding instructions and
# first sources had been silently cut.
#
# The symptom was a correct question getting "The information provided
# does not contain any data related to MFI for Homopolymer H030SG" while
# the trace showed 10 passages retrieved and the value present in them.
# Retrieval was right; the prompt the model actually saw was not the
# prompt that was built.
#
# This is exactly the failure the previous comment here warned about --
# "if a future change grows the prompt, raise this deliberately" -- and
# it was introduced two commits later by the person who wrote the
# warning. A note is not a mechanism.
#
# 6144 holds the measured 2986-token prompt plus a long answer with
# room to spare. The VRAM argument for a tight window is moot in any
# case: a 7B generation model and the verifier do not co-reside on an
# 8 GB card at any context size, so shaving the KV cache bought nothing.
#
# ONE CONTEXT SIZE, NOT FOUR. Ollama reloads a model whenever a request
# asks for a different num_ctx than the one loaded -- measured at ~13 s
# per reload (a warm 5.1 s answer took 18.0 s straight after a job had
# left the model at 8192). Chat asked for 6144, the verifier 3072, jobs
# 8192 and 12288, so a question asked during a background job paid a
# reload each way. Everything now asks for STANDARD_NUM_CTX, and only a
# prompt that genuinely does not fit asks for LONG_NUM_CTX
# (context_for). With OLLAMA_NUM_PARALLEL=2, 8192 is 6.3 GB, 100% GPU;
# 12288 already spills 11% to CPU, so it is the exception, not a bucket.
STANDARD_NUM_CTX = 8192
LONG_NUM_CTX = 12288


def context_for(prompt_chars: int, answer_tokens: int = 1024) -> int:
    """The context a prompt of this many characters needs: standard unless it cannot fit."""
    return STANDARD_NUM_CTX if prompt_chars // 3 + answer_tokens <= STANDARD_NUM_CTX else LONG_NUM_CTX


GENERATION_NUM_CTX = int(os.environ.get("WORKBENCH_GEN_CTX", str(STANDARD_NUM_CTX)))

DEFAULT_TIMEOUT = int(os.environ.get("WORKBENCH_LLM_TIMEOUT", "600"))


# Context window for the SHORT-PROMPT models (router, verifier). They
# read one request plus one answer -- a few hundred tokens -- while
# Ollama's 4096 default sizes a KV cache for the full window and keeps
# it resident.
#
# Measured: with reasoning-model (qwen2.5:7b, ~5.5 GB resident) and
# fast-router (phi3.5) both at 4096, the pair needs ~9.5 GB on an 8.2 GB
# card, so `ollama ps` after every turn showed ONLY phi3.5 -- qwen had
# been evicted and had to be reloaded on the next turn. Both models were
# being loaded from scratch every single turn, which was the bulk of the
# per-turn time, not the inference.
# 2048 was sized for a verifier that saw only the request and the
# draft. It now also receives the retrieved sources (truncated to 700
# characters each) so it can check a cited value against the source it
# is attributed to, which is the difference between verifying
# grounding and verifying prose style. 3072 covers that; the router,
# which really does send a short prompt, is unaffected by the extra
# headroom because unused context is not allocated per request.
# Now the standard size too: the verifier runs on the same qwen2.5:7b as
# chat, and a different num_ctx on the same model is a reload.
SHORT_PROMPT_NUM_CTX = int(os.environ.get("WORKBENCH_SHORT_CTX", str(STANDARD_NUM_CTX)))


# Deterministic by default.
#
# Ollama defaults to temperature 0.8. Measured: the SAME question
# ("compare batches for H030SG vs H110F and total them") ran twice
# through the agent loop and produced 2 tool calls / 25.9s / the correct
# answer 38, then 6 tool calls / 42.5s / an answer about a completely
# different quantity. Sampling variance in tool SELECTION compounds --
# a different first choice becomes the context for every choice after
# it, so small randomness at the top becomes a different conversation.
#
# For a workbench whose claim is that answers are traceable, the same
# question giving materially different work is its own problem,
# separate from whether either answer was right.
DEFAULT_TEMPERATURE = float(os.environ.get("WORKBENCH_TEMPERATURE", "0"))


def default_options() -> dict:
    return {
        "num_gpu": DEFAULT_NUM_GPU,
        "num_ctx": GENERATION_NUM_CTX,
        "temperature": DEFAULT_TEMPERATURE,
    }


def short_prompt_options() -> dict:
    """Options for models that only ever see a short prompt."""
    return {"num_gpu": DEFAULT_NUM_GPU, "num_ctx": SHORT_PROMPT_NUM_CTX}


# What Ollama reported for the most recent generate() on THIS thread, for
# callers that report usage (the agent map) without threading it through
# every signature. Reset it before a call you intend to read.
last_call = threading.local()


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
    data = response.json()
    last_call.stats = {
        "model": model_name,
        "prompt_tokens": data.get("prompt_eval_count"),
        "output_tokens": data.get("eval_count"),
        "seconds": round((data.get("total_duration") or 0) / 1e9, 2),
    }
    return data["response"]
