# Defect / anomaly detection (TOOLS.md row 7) — handed to Sahil

**Owner: Sahil, end to end — the model and the overlay.** This was
previously split (Aryan integrates the model, Sahil renders the boxes),
which left the format hand-off as a dependency in both directions and
nothing built on either side. One owner now.

Priority 🟡. Read the last section before you start: there is a real
argument for leaving this registry-listed, and you should make that call
knowingly rather than discover it three days in.

---

## What the deliverable is

A tool that takes an inspection photograph and returns bounding boxes
with a class and a confidence, plus the viewer that draws them
(FRONTEND.md §3.14). Registered in the tool registry like every other
tool, so the orchestrator can reach it and `/api/tools` lists it.

```python
# backend/tools/vision/defect_detection.py
def detect_defects(image_path: str, min_confidence: float = 0.35) -> DefectResult
```

`DefectResult` should carry, per detection: `label`, `confidence`,
`bbox` as `(x_min, y_min, x_max, y_max)` in pixels. Match
`OCRResult`/`OCRLine` in `backend/tools/vision/ocr_printed.py` — same
shape, same conventions, so the overlay can render OCR boxes and defect
boxes with one component.

---

## Three things that will bite you, in order

### 1. `ultralytics` phones home, and that breaks hard constraint #1

This is the one that matters most, because the whole product claim is
"nothing leaves the premises" and there is a network monitor on screen
during the demo proving it. Out of the box, ultralytics:

- sends anonymous usage analytics on import and on every predict
- downloads weights from GitHub on first use if they are not local
- fetches a font file (`Arial.ttf`) for drawing labels
- checks for package updates

All four must be off before this is allowed anywhere near the app:

```python
import os
os.environ["YOLO_OFFLINE"] = "True"
# Set BEFORE importing ultralytics -- the settings file is read at import.
from ultralytics import settings
settings.update({"sync": False})   # analytics off
```

Then load weights from an explicit local path only, the way every other
model-backed tool in this repo does. Read
`backend/ingestion/model_cache.py` — it is the fetch-once /
offline-forever pattern, and `ocr_printed.py` is a worked example
including the env var PaddleOCR needed for exactly this reason.

**Verify it rather than trust it.** There is already a test pattern for
this: `backend/tests/test_sandbox.py` proves `--network none` is
actually enforced, not merely configured. Do the same here — block
network access and confirm detection still runs.

### 2. The GPU is available now, and the setup is fragile in one place

PaddleOCR was moved to the GPU today (21.08s → 0.61s on OCR). That
involved a genuine conflict you will hit too if you install anything
CUDA-related:

- `torch` bundles cuDNN **9.10.2** inside `torch/lib`
- pip's `nvidia-cudnn-cu12` is the shared copy other frameworks use
- Windows loads **one DLL per base name per process**, so two versions
  means whichever binds first wins and the other dies with
  `WinError 127` on a symbol it expected

`requirements.txt` pins `nvidia-cudnn-cu12==9.10.2.21` to match torch.
**Do not change that pin**, and if you install a package that moves it,
check both frameworks still run a convolution before committing.
`backend/utils/cuda_dll_path.py` handles the rest; call
`ensure_cuda_dll_path()` before importing anything CUDA-backed.

ultralytics depends on torch, which is already installed as `2.9.1+cu126`
— install it with `--no-deps` if pip tries to move torch.

### 3. Accuracy measured on someone else's photos is not accuracy here

A public fine-tune (corrosion, cracks, leaks) will produce a number.
That number will be measured on the public dataset's images, and MRPL's
inspection photographs are different equipment, different lighting,
different camera. Reporting the public figure as if it described
performance here is the mistake this repository has made six times in
other forms — the running list is in `HANDOFF.md` §5 under
"self-deceiving measurement", and it is worth reading before you pick a
number to put in a slide.

If you report accuracy, say what corpus it was measured on, in the same
sentence. "0.82 mAP on the public <name> dataset; not measured on MRPL
imagery" is a strong, honest claim. "82% accurate" is not.

The same rule the chart tool already follows applies: register the tool
with `is_estimate=True` if its output is a model's guess rather than a
measured fact. See `backend/tools/registry.py` and the
`describe_chart_image` registration in `catalog.py` — that tool exists
precisely because the vision model was measured inventing numbers, and
`CHART_STRESS_REPORT.md` is the evidence.

---

## Where everything goes

| Thing | Path |
|---|---|
| The tool | `backend/tools/vision/defect_detection.py` |
| Registration | `backend/tools/catalog.py` (add a `tool(...)` block) |
| Weights | `models/vision/` — gitignored, fetched once |
| Tests | `backend/tests/test_defect_detection.py` |
| Overlay viewer | `frontend/src/` — FRONTEND.md §3.14 |
| TOOLS.md row | 7 — update the status and describe what you built |

Registering it is four lines; copy the `extract_printed_text` block in
`catalog.py`. The dispatcher enforces the safety flags centrally, so you
cannot forget them.

---

## The argument for NOT building it

Made properly, because 🟡 means "registry-listed is acceptable" and
CLAUDE.md's demo-day rule says to protect 🔴 first:

- Nothing in the demo script (TOOLS.md §I) depends on defect detection.
- It needs a labelled dataset, a fine-tune, and GPU time — all of which
  compete with the network monitor, which §I calls the single most
  judge-scrutinised UI element in the app, and which is **yours**.
- The overlay viewer is the visible half, and it can be built and
  demonstrated against OCR bounding boxes, which are real, local, and
  already produced by `extract_printed_text` on the scanned CCR1
  checklist. That gives you a working annotated-image viewer with no
  model risk at all.

**Recommendation: build the overlay against OCR boxes first.** It is the
part a judge sees, it has no offline or accuracy hazard, and it makes
the detection model a drop-in later — same shape, same renderer. Then
decide on YOLOv8 with the network monitor already finished.

If you do build the model, the three hazards above are the whole brief.

---

## What is already done for you

- OCR runs on the GPU and returns boxes in `(x_min, y_min, x_max, y_max)`
  — the exact shape your overlay needs, available today
- `/api/health` reports `ocr_device` so you can tell GPU from CPU
- The scanned checklist (`MRPL_RAG_Test_Corpus/06_Diagrams_and_Scans/`)
  is a real image with real detected text, 23 lines, for building the
  viewer against
- The tool registry derives JSON schemas from type hints and docstrings,
  so you write a normal Python function and get a callable tool

Ask me for anything on the model-integration side — the split is gone,
but the knowledge is not.
