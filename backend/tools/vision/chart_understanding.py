"""Vision-model chart description — for chart IMAGES with no underlying
data (an embedded picture in a PDF page, or a standalone chart PNG), as
opposed to xlsx_charts.py's exact native-chart-DATA extraction.

CRITICAL DISTINCTION, stated once here because every caller must
understand it before using this function's output: this is a VISION
MODEL'S ESTIMATE of what a chart shows, never a verified number. A
vision model reading a bar's height or a pie slice's angle and inferring
a value is doing exactly the kind of estimation CLAUDE.md hard
constraint #3 forbids for math elsewhere in this system — so this
tool's output must always be labeled as an estimate, and the
generation/approval-note pipeline must never cite `description` the way
it would cite a SymPy result or one of xlsx_charts.py's cached values.
`ChartVisualDescription.is_estimate` is hardcoded True for exactly this
reason — there is no code path that produces a "verified" value here,
by design.

The prompt explicitly separates two very different kinds of "reading a
chart": (a) transcribing a number that's LITERALLY PRINTED as text on
the chart (a data label, an axis tick) — that's OCR-shaped, close to
reliable — from (b) inferring a value from a bar's visual height or a
slice's visual angle, which is a genuine estimate and must be flagged as
such, never returned with the same confidence as (a).
"""

import base64
import os
from pathlib import Path

import requests
from pydantic import BaseModel

from backend.models.registry import resolve_model_name

_OLLAMA_HOST = "http://localhost:11434"

# How many transformer layers to ASK Ollama to place on the GPU.
#
# CORRECTION TO AN EARLIER CLAIM IN THIS FILE (commit 989933b). This
# comment previously reported "any offload beats none (~1.7x)" from a
# benchmark of 109s / 63.1s / 71.8s / 63.7s at num_gpu unset / 12 / 20 /
# 28. That conclusion was WRONG, and the way it was wrong is worth
# keeping written down: the benchmark ran `ollama stop` before every
# arm, so every single measurement included a cold model load, and the
# spread it attributed to GPU offload was load-time variance.
#
# Re-measured properly — same image, cold AND warm timing per arm, and
# `ollama ps` actually inspected rather than inferred:
#
#   num_gpu   cold     warm    ollama ps PROCESSOR
#   (unset)   86.7s    6.9s    100% CPU
#   12        59.3s   11.9s    100% CPU
#   99        57.6s    8.9s    100% CPU
#
# num_gpu=99 means "put every layer on the GPU" and STILL reports 100%
# CPU, with nvidia-smi showing ~200MiB used. On this box the option has
# no effect whatsoever: qwen2.5vl:7b measures 13GB resident against an
# 8GB card (see docs/DEPENDENCIES.md), and Ollama places it entirely on
# CPU regardless of what is requested. There is no partial-offload win
# to be had here — the earlier 1.7x was an artifact of measurement.
#
# The real effect, which the first benchmark hid by making every run
# cold, is model RESIDENCY: 86.7s cold versus 6.9s warm is ~12x, an
# order of magnitude larger than anything num_gpu did. Anything issuing
# many vision calls should keep the model loaded (Ollama's keep_alive)
# rather than let it unload between batches.
#
# The parameter is KEPT rather than deleted, for two honest reasons: it
# costs nothing, and venue hardware with enough VRAM to actually fit
# this model would benefit from it. But it is no longer presented as a
# measured speedup on this hardware, because it is not one. Re-measure
# on the venue machine — including `ollama ps`, not just a stopwatch.
_DEFAULT_NUM_GPU_LAYERS = int(os.environ.get("OLLAMA_NUM_GPU_LAYERS", "12"))

_CHART_DESCRIPTION_PROMPT = (
    "You are looking at an image that may contain a chart (bar chart, pie chart, "
    "or line chart) from an industrial/engineering document. Describe, in this "
    "exact order: "
    "(1) the chart type; "
    "(2) the title or subject, if visible; "
    "(3) axis labels or legend entries visible; "
    "(4) any numeric values LITERALLY PRINTED as text on the chart (data labels, "
    "axis tick marks) — transcribe these exactly as OCR would, do not estimate "
    "a value from a bar's height or a slice's angle instead; "
    "(5) if no numeric labels are printed, a one-sentence qualitative description "
    "of the overall trend or pattern only (e.g. 'increasing across categories'), "
    "explicitly not a specific number. "
    "If any of the above is not visible or not applicable, say so explicitly "
    "rather than guessing."
)


class ChartVisualDescription(BaseModel):
    description: str
    is_estimate: bool = True  # always True -- see module docstring


def _encode_image(image_path: str) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("ascii")


def describe_chart_image(
    image_path: str,
    model_id: str = "vision-model",
    num_gpu_layers: int | None = None,
    timeout_seconds: int = 180,
) -> ChartVisualDescription:
    """Ask the vision model to describe a chart image.

    Args:
        image_path: the chart image to describe.
        model_id: registry id (never a raw model name — CLAUDE.md hard
            constraint #2), resolved through models.yaml.
        num_gpu_layers: how many transformer layers to place on the GPU.
            Defaults to _DEFAULT_NUM_GPU_LAYERS — see its comment for why
            this is a tunable parameter rather than left to Ollama's own
            all-or-nothing fit check. Pass 0 to force pure CPU.

    Raises:
        FileNotFoundError: if `image_path` doesn't exist — checked
            before touching the model at all.
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found at {image_path}")

    if num_gpu_layers is None:
        num_gpu_layers = _DEFAULT_NUM_GPU_LAYERS

    model_name = resolve_model_name(model_id)
    response = requests.post(
        f"{_OLLAMA_HOST}/api/generate",
        json={
            "model": model_name,
            "prompt": _CHART_DESCRIPTION_PROMPT,
            "images": [_encode_image(image_path)],
            "stream": False,
            "options": {"num_gpu": num_gpu_layers},
        },
        # Bounded, and short enough that a wedged request is caught in
        # minutes rather than blocking a sweep indefinitely. Measured:
        # a normal chart takes 45-75s on this hardware, so 180s is ~2.5x
        # headroom. Real incident this guards against: one corpus image
        # made Ollama hang past a 600s timeout entirely, stalling a
        # 12-chart sweep for 15 minutes on its 4th item.
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    return ChartVisualDescription(description=response.json()["response"].strip())
