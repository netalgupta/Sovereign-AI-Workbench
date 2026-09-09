"""Printed-text OCR — VIBECODING_SPEC.md CARD 05.

Two real gaps found by actually running this against the currently
pip-installable `paddleocr` package, not by implementing CARD 05's
pseudocode literally:

1. CARD 05 was written against PaddleOCR's OLD API — `.ocr(path, cls=True)`
   returning `[[[bbox_points], (text, confidence)], ...]`, 4 corner
   points per line. The current package (PaddleOCR 3.x / PaddleX) is a
   completely different pipeline with a different result shape:
   `result[0]` is a dict with `rec_texts`, `rec_scores`, `rec_boxes` —
   already `[x_min, y_min, x_max, y_max]`, not 4 corner points needing
   conversion. This wrapper targets the ACTUAL library, buffering
   callers from that difference — the CARD 05 caller-facing contract
   (OCRResult/OCRLine) stays exactly as specified either way.

2. On this exact platform, default construction crashes with a PaddleX/
   oneDNN incompatibility (`NotImplementedError:
   ConvertPirAttribute2RuntimeAttribute not support
   [pir::ArrayAttribute<pir::DoubleAttribute>]`) — nothing to do with
   models or input; `enable_mkldnn=False` avoids it. Found by running
   the plain library call before writing a single line of wrapper code.

Same fetch-once/offline-forever discipline as every other model-backed
tool: PaddleOCR's own log says it outright — "Checking connectivity to
the model hosters, this may take a while. To bypass this check, set
`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` to `True`." The 5 sub-models it
needs were downloaded once (to PaddleX's default cache) and copied into
this repo's models/ocr/ convention, matching embeddings/audio's
already-established pattern; every load here points explicit
`*_model_dir` params at those local copies AND sets the disable-check
env var, belt-and-suspenders.
"""

import os
from pathlib import Path

from pydantic import BaseModel

_MODELS_ROOT = Path(__file__).resolve().parents[3] / "models" / "ocr"

# Must be set before constructing PaddleOCR — this is what stops it
# phoning out to check model-hoster connectivity even when every model
# is already cached locally.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x_min, y_min, x_max, y_max


class OCRResult(BaseModel):
    full_text: str
    lines: list[OCRLine]


_ocr_instance = None


def _get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR

        _ocr_instance = PaddleOCR(
            # No `lang=` here: PaddleOCR ignores it (with a warning) once
            # explicit model dirs are given below — verified directly,
            # not left in as harmless-looking dead configuration.
            enable_mkldnn=False,  # see module docstring point 2
            doc_orientation_classify_model_dir=str(_MODELS_ROOT / "PP-LCNet_x1_0_doc_ori"),
            doc_unwarping_model_dir=str(_MODELS_ROOT / "UVDoc"),
            textline_orientation_model_dir=str(_MODELS_ROOT / "PP-LCNet_x1_0_textline_ori"),
            text_detection_model_dir=str(_MODELS_ROOT / "PP-OCRv6_medium_det"),
            text_recognition_model_dir=str(_MODELS_ROOT / "PP-OCRv6_medium_rec"),
        )
    return _ocr_instance


def extract_printed_text(image_path: str) -> OCRResult:
    """Extract printed text from `image_path`.

    Raises:
        FileNotFoundError: if `image_path` doesn't exist — checked
            before touching PaddleOCR at all, so the error message is
            this function's own clear one, not PaddleOCR's less legible
            internal failure for a missing file.
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found at {image_path}")

    ocr = _get_ocr_instance()
    raw_results = ocr.predict(image_path)  # .ocr() is deprecated in favor of .predict(); same result shape, verified

    if not raw_results or raw_results[0] is None:
        return OCRResult(full_text="", lines=[])

    page = raw_results[0]
    lines = [
        OCRLine(
            text=text,
            confidence=float(score),
            bbox=tuple(int(v) for v in box.tolist()),
        )
        for text, score, box in zip(page["rec_texts"], page["rec_scores"], page["rec_boxes"])
    ]

    return OCRResult(full_text="\n".join(line.text for line in lines), lines=lines)
