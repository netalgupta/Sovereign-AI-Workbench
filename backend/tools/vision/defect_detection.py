"""Defect / anomaly region detection — TOOLS.md row 7.

WHAT THIS IS TODAY vs WHAT IT BECOMES. Row 7 is "Defect/anomaly
detection (YOLOv8)". That model is NOT wired in yet, deliberately, and
this module is the honest bridge: it produces overlay-contract
detections from the offline OCR already proven in this repo
(extract_printed_text / row 1), giving a working annotated-image
viewer with ZERO model risk. When a real detector lands, it replaces
the detection source inside this function while the output shape stays
exactly the same — the frontend overlay (DefectOverlay.jsx) does not
know or care where its boxes came from.

THREE CONSTRAINTS THAT MUST SURVIVE THE DETECTOR UPGRADE:

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

# Severity bands, derived ONLY from OCR confidence. These are
# transcription-confidence levels, not defect classifications — the
# overlay colors boxes by them, and calling a sub-threshold OCR reading
# "critical" would be importing vocabulary the tool does not have yet.
_HIGH_CONF = 0.90
_MED_CONF = 0.70


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
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class DefectDetectionResult(BaseModel):
    image_url: str
    image_width: int | None = None
    image_height: int | None = None
    detections: list[Detection]
    source: str  # "ocr-printed" today; the detector's name later
    # What the regions ARE. "text_region" until a real defect model lands;
    # a consumer must not describe these as defects.
    kind: str = "text_region"


def _severity_for(confidence: float) -> str:
    """Always "low". There is no severity to report.

    This mapped LOW OCR confidence to HIGH severity, so a blurry nameplate
    rendered on the overlay as a high-severity defect and a crisp one as
    low -- a defect judgement made from how legible the text was. The
    overlay contract requires a severity; the honest one for a region that
    is not a defect is the neutral band. OCR confidence is still reported
    in `confidence`, where it means what it says.
    """
    return "low"


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
    """Run defect/anomaly region detection on `image_path`.

    Today the detection source is local OCR: every text line is emitted
    as a detection region with its OCR box and confidence, labeled by
    the recognized text. That is the annotated-image viewer with zero
    model risk; when the row-7 detector (YOLOv8) is integrated it
    replaces the source behind this same output contract.

    Fully offline: constructively built on extract_printed_text, which
    is itself offline-proven (see test_ocr_printed.py).

    Args:
        image_path: path to the inspection image (corpus-relative or
            absolute; must exist on disk).

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
                severity=_severity_for(line.confidence),
            )
        )

    return DefectDetectionResult(
        image_url=_image_url_for(image_path),
        detections=detections,
        source="ocr-printed",
    )