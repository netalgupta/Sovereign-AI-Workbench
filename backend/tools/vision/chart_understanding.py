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
from pathlib import Path

import requests
from pydantic import BaseModel

from backend.models.registry import resolve_model_name

_OLLAMA_HOST = "http://localhost:11434"

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


def describe_chart_image(image_path: str, model_id: str = "vision-model") -> ChartVisualDescription:
    """Ask the vision model to describe a chart image.

    Raises:
        FileNotFoundError: if `image_path` doesn't exist — checked
            before touching the model at all.
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found at {image_path}")

    model_name = resolve_model_name(model_id)
    response = requests.post(
        f"{_OLLAMA_HOST}/api/generate",
        json={
            "model": model_name,
            "prompt": _CHART_DESCRIPTION_PROMPT,
            "images": [_encode_image(image_path)],
            "stream": False,
        },
        timeout=180,
    )
    response.raise_for_status()

    return ChartVisualDescription(description=response.json()["response"].strip())
