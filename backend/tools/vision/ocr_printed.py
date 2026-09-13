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


_device_cache: str | None = None


def _ocr_device() -> str:
    """"gpu" when this build of paddle can actually reach one, else "cpu".

    Two separate conditions, and both matter. `paddlepaddle` (CPU) and
    `paddlepaddle-gpu` are different distributions that both import as
    `paddle`, so the CPU wheel reports is_compiled_with_cuda() False no
    matter what hardware is present. And a CUDA build on a machine with
    no visible device reports device_count() 0.

    Honoured override for the venue: WORKBENCH_OCR_DEVICE=cpu forces the
    CPU path without uninstalling anything, which is the difference
    between a config change and a reinstall five minutes before a demo.
    """
    global _device_cache
    if _device_cache is not None:
        return _device_cache

    override = (os.environ.get("WORKBENCH_OCR_DEVICE") or "").strip().lower()
    if override in ("cpu", "gpu"):
        _device_cache = override
        return override
    try:
        # Before importing paddle, not after: the CUDA DLLs live in
        # sibling nvidia/*/bin directories that Windows does not search,
        # and the failure that causes surfaces only at the first
        # convolution -- long after import, device query and tensor
        # placement have all reported success.
        from backend.utils.cuda_dll_path import ensure_cuda_dll_path

        ensure_cuda_dll_path()

        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            _device_cache = "gpu"
            return "gpu"
    except Exception:  # noqa: BLE001 - a probe must never break OCR
        pass
    _device_cache = "cpu"
    return "cpu"


def ocr_device() -> str:
    """The device OCR will use, determining it if necessary (~4s cold).

    A pipeline that silently fell back to CPU looks identical to one
    that chose CPU, which is how "the GPU is not working" becomes an
    afternoon of guessing. Memoised: the cost is paid once per process.
    """
    return _ocr_device()


def ocr_device_if_known() -> str:
    """The device, ONLY if it has already been determined.

    A HEALTH CHECK MUST NOT DO EXPENSIVE WORK. ocr_device() imports
    torch and paddle to answer, which is 3.87s on a cold process --
    measured -- and /api/health is polled by the frontend. A health
    endpoint that blocks a worker for four seconds is not reporting
    health, it is degrading it, and with a single worker every other
    request queues behind it.

    Returns "not-initialised" rather than a guess. That is a real
    answer: OCR has not run yet, so there is nothing to report, and
    guessing "cpu" here would be a wrong claim on a GPU machine.
    """
    return _device_cache or "not-initialised"


def _get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        from backend.utils.cuda_dll_path import ensure_cuda_dll_path

        ensure_cuda_dll_path()

        from paddleocr import PaddleOCR

        _ocr_instance = PaddleOCR(
            # No `lang=` here: PaddleOCR ignores it (with a warning) once
            # explicit model dirs are given below — verified directly,
            # not left in as harmless-looking dead configuration.
            enable_mkldnn=False,  # see module docstring point 2
            # GPU WHEN THERE IS ONE, CPU WHEN THERE IS NOT.
            #
            # PaddleOCR was running on CPU because `paddlepaddle` (the
            # CPU wheel) was installed; the CUDA build is a different
            # distribution, not a flag. It is now `paddlepaddle-gpu`
            # built against CUDA 12.6, matching torch's cu126 — and
            # crucially with NO virtualenv, because the cascading
            # dependency conflict this repo hit before was the Linux
            # pattern where torch and paddle fight over shared nvidia-*
            # wheels. On Windows torch bundles its CUDA DLLs inside
            # torch/lib, so the two coexist. Verified after the swap:
            # paddle on gpu:0 AND torch.cuda.is_available() still True.
            #
            # DETECTED, NOT ASSUMED. A hardcoded device="gpu" turns a
            # machine without CUDA into a crash at first OCR call, which
            # on venue hardware is a demo failure with no fallback. The
            # CPU path stays fully supported and is what a CPU-only
            # install silently gets.
            device=_ocr_device(),
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
