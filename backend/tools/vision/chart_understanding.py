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

# How many transformer layers to place on the GPU. None = let Ollama
# decide, which is what this tool did originally and which measured
# badly on the dev box: Ollama sized qwen2.5vl:7b at ~13GB against an
# 8GB RTX 4060, concluded it did not fit, and ran the model at 100% CPU
# — 76-122 seconds per chart image. The model genuinely does not fit
# whole, but that is not the same as it not fitting AT ALL: offloading a
# subset of layers puts the heaviest matmuls on the GPU and leaves the
# remainder on CPU.
#
# This is exactly the situation CLAUDE.md's VRAM discipline section
# describes ("do not write code that assumes all models can be resident
# in VRAM simultaneously ... make concurrency configurable, not
# assumed"), so the split is a parameter with a documented default
# rather than a hardcoded constant: venue hardware with more VRAM should
# raise it, and a machine with less should lower it.
#
# Measured on the 8GB dev card, same chart image, model stopped and
# reloaded between runs so each number includes its own cold start:
#
#   num_gpu   time     note
#   (unset)   109.0s   Ollama's own choice: 100% CPU
#   12         63.1s   fastest measured
#   20         71.8s   SLOWER than 12 — spills past 8GB and thrashes
#   28         63.7s   ~tied with 12
#
# Any offload beats none (~1.7x), but the curve is NOT monotonic, which
# is why this is a measured constant rather than "as many layers as
# possible". 12 is chosen over the statistically-tied 28 because it
# leaves the most VRAM headroom — CLAUDE.md's VRAM discipline is
# explicit that code must not assume a model can be resident alongside
# others, and this tool shares an 8GB card with the embedding model.
#
# Overridable per call, and via OLLAMA_NUM_GPU_LAYERS for deployment
# tuning without a code change: venue hardware with more VRAM should
# raise it, and this exact curve should be re-measured there rather than
# assumed to transfer.
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
        timeout=600,  # partial-offload cold start is slower than a warm call
    )
    response.raise_for_status()

    return ChartVisualDescription(description=response.json()["response"].strip())
