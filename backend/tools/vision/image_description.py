"""Vision-model description of ANY image/diagram — TOOLS.md row 72.

FR-14: uploaded photos and diagrams get OCR only today; the vision model
never INTERPRETS them. `describe_chart_image` (row 62) understands charts;
this tool understands everything else — photos, P&IDs, sketches, scans —
with a general prompt. The demo's P&ID upload, fed to this tool, becomes
a description of the equipment and connections a reply can ground on.

OWNERSHIP BOUNDARY, stated once because it matters: this is a PROSE
description of what an image depicts. It is deliberately NOT row 6 —
P&ID symbol/connection EXTRACTION (Aryan, not started) turns a P&ID into
structured graph-layer records (valves, lines, tags). That is a different
deliverable with a different output shape. If touch with row 6 is ever
needed, the coordination point is the same one the RAG brief names:
Aryan owns the structured extraction, this tool owns the readable
description, and neither should absorb the other's output contract.

ESTIMATE, ALWAYS. Identical discipline to chart_understanding.py: a
vision model reading an engineering drawing and describing connections,
rough geometry, or any quantity is estimating, not measuring. CLAUDE.md
hard constraint #3 forbids the LLM "doing arithmetic in its head", and a
vision model inferring a size or count from pixels is the visual
analogue. `ImageDescription.is_estimate` is hardcoded True for exactly
this reason — there is no path that produces a verified value here, by
design. The pipeline must badge this output ESTIMATE (the frontend does
via `/api/tools` metadata) and must never cite it the way it would cite
an OCR transcription or a SymPy result.
"""

import base64
import os
from pathlib import Path

import requests
from pydantic import BaseModel

from backend.models.registry import resolve_model_name

_OLLAMA_HOST = "http://localhost:11434"

# See chart_understanding.py's comment block on this constant for the
# measured background: on this 8GB-carded dev box OLLAMA_NUM_GPU_LAYERS
# has no effect (qwen2.5vl:7b is 13GB resident -> 100% CPU regardless),
# and RESIDENCY matters far more than the split. Kept as a tunable for
# venue hardware that can actually fit the model.
_DEFAULT_NUM_GPU_LAYERS = int(os.environ.get("OLLAMA_NUM_GPU_LAYERS", "12"))

_IMAGE_DESCRIPTION_PROMPT = (
    "You are looking at an image uploaded to an industrial inspection system. It "
    "may be a photograph, a diagram, a P&ID schematic, a sketch, or a scan. "
    "Describe, in this exact order: "
    "(1) the kind of image it is (photograph / P&ID / flow diagram / sketch / scan); "
    "(2) the main subject — for a diagram or P&ID, the equipment, instruments, and "
    "the connections/lines between them; for a photograph, the scene and any "
    "visible equipment; "
    "(3) any text LITERALLY PRINTED in the image (titles, tags, labels, values) — "
    "transcribe these exactly as OCR would, do not guess what they might say; "
    "(4) any connections, flow direction, or relationships you can identify between "
    "the elements. "
    "If any part is not visible or not applicable, say so explicitly rather than "
    "guessing. Any quantity you state from looking at the image is an ESTIMATE, "
    "not a measured value — never present an inferred number as a fact."
)


class ImageDescription(BaseModel):
    description: str
    is_estimate: bool = True  # always True -- see module docstring


def _encode_image(image_path: str) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("ascii")


def describe_image(
    image_path: str,
    model_id: str = "vision-model",
    num_gpu_layers: int | None = None,
    timeout_seconds: int = 180,
) -> ImageDescription:
    """Ask the vision model to describe any image or diagram.

    Args:
        image_path: the image to describe.
        model_id: registry id (never a raw model name — CLAUDE.md hard
            constraint #2), resolved through models.yaml.
        num_gpu_layers: how many transformer layers to place on the GPU.
            Defaults to _DEFAULT_NUM_GPU_LAYERS — see the constant's
            comment for what was actually measured on this box.
        timeout_seconds: bounded request timeout; a wedged Ollama request
            is caught in minutes, not forever.

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
            "prompt": _IMAGE_DESCRIPTION_PROMPT,
            "images": [_encode_image(image_path)],
            "stream": False,
            "options": {"num_gpu": num_gpu_layers},
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    return ImageDescription(description=response.json()["response"].strip())