"""OCR text-region overlay — TOOLS.md row 7 (DESCOPED).

This is deliberately NOT a defect/anomaly detector. Row 7 was marked
"built" while describing YOLOv8 defect detection; the code never did
that. It returns the regions where PRINTED TEXT sits on an image (OCR
text lines from extract_printed_text / row 1), so a judge who uploads
a photo of a corroded flange and asks what is wrong gets text boxes,
not findings. That is the exact failure the descope removes.

DECISION (2026-09-19, Option A): row 7's status is `not started (OCR
text-region overlay only)`. What exists here is the overlay half — a
real, offline, registered tool that boxes recognized text — and real
defect/anomaly detection is not started. The tool's output is honest
about what it is: every region carries `kind: "text_region"` and
severity is always `"low"`, because OCR confidence is a
transcription-confidence signal, not a defect classification. If a real
detector is ever built, it swaps in behind this same output contract
(same box shape, same overlay), and the constraints below govern that
upgrade.

THREE CONSTRAINTS THAT MUST SURVIVE ANY FUTURE DETECTOR UPGRADE:

1. Hard constraint #1 (no outbound network). Ultralytics phones home
   FOUR ways: analytics on import, analytics on predict, a weight-file
   download from GitHub, and an Arial.ttf font fetch. All four must be
   disabled or proven absent (see the offline test in this repo's
   test_sandbox.py pattern) before ultralytics is ever imported. The
   documented egress-blocking configuration lives in the demo script
   notes; the test `test_offline_with_sockets_hard_blocked` here proves
   the CURRENT source is offline and stays that way.

2. cuDNN is load-bearing and torch is NOT in requirements.txt today —
   and staying out of it is the point. torch ships a bundled cuDNN
   (9.10.2 on this box); Windows loads ONE cuDNN DLL per name per
   process, so an unrelated CUDA-adjacent install can move the DLL and
   break every framework that trusted it — the failure only shows up at
   the first convolution, by far the worst place to discover it. Do not
   add torch/ultralytics casually, and never install CUDA toolchain
   pieces blindly; extras belong in a venv, not the shared env.

3. Accuracy claims name their corpus. A fine-tune measured against a
   public dataset describes THAT dataset, not MRPL photos. Whenever a
   number is reported, the sentence names the corpus it was measured
   on, here and downstream.
"""

from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field

from backend.tools.vision.ocr_printed import extract_printed_text


class DetectionBox(BaseModel):
    xmin: int
    ymin: int
    xmax: int
    ymax: int


class Detection(BaseModel):
    id: str
    label: str
    confidence: float
    box: DetectionBox
    severity: str = Field(default="low", pattern="^(low|medium|high|critical)$")
    kind: str = "text_region"


class DefectDetectionResult(BaseModel):
    image_url: str
    image_width: int | None = None
    image_height: int | None = None
    detections: list[Detection]
    source: str  # "ocr-printed" today; a real detector's name later


def _image_url_for(image_path: str) -> str:
    """Map a corpus-relative image path to the route that serves it.

    The overlay downloads the image over HTTP, so the URL must point at
    a route the backend can serve read-only — the frontend cannot fetch
    a bare filesystem path. The route (GET /api/inspection/image)
    resolves this URL's `path` query back to a file confined to the
    corpus root.
    """
    path = str(image_path).replace("\\", "/")
    return f"/api/inspection/image?path={quote(path)}"


def detect_defects(image_path: str) -> DefectDetectionResult:
    """Return OCR text-region overlay boxes for `image_path`.

    NOT a defect/anomaly detector — defect detection is not implemented
    (TOOLS.md row 7 status: `not started (OCR text-region overlay
    only)`). This returns where PRINTED TEXT is on the image: every OCR
    text line becomes a box labeled by the recognized text, confidence
    is OCR transcription confidence, severity is always ``"low"``, and
    every region carries ``kind: "text_region"``. Presenting these boxes
    as defect findings would be presenting text locations as defects,
    which is exactly what the descope forbids.

    Fully offline: constructively built on extract_printed_text, which
    is itself offline-proven (see test_ocr_printed.py).

    Args:
        image_path: path to the image (corpus-relative or absolute; must
            exist on disk).

    Raises:
        FileNotFoundError: if `image_path` doesn't exist.
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found at {image_path}")

    ocr = extract_printed_text(image_path)

    detections = []
    for i, line in enumerate(ocr.lines):
        x_min, y_min, x_max, y_max = line.bbox
        detections.append(
            Detection(
                id=f"det-ocr-{i:03d}",
                label=line.text,
                confidence=round(line.confidence, 4),
                box=DetectionBox(xmin=x_min, ymin=y_min, xmax=x_max, ymax=y_max),
                severity="low",
                kind="text_region",
            )
        )

    return DefectDetectionResult(
        image_url=_image_url_for(image_path),
        detections=detections,
        source="ocr-printed",
    )