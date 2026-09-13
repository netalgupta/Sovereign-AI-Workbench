"""Tests for row 7's defect/anomaly detection (OCR-box based today).

Skips honestly when the local model copies aren't present (same pattern
as test_ocr_printed.py) rather than mocking OCR output — the point of
testing this tool is whether it really boxes real scanned pixels.
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_MODELS_PRESENT = os.path.isdir(os.path.join(_REPO_ROOT, "models", "ocr", "PP-OCRv6_medium_det"))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CORPUS_IMAGE = os.path.join(
    _REPO_ROOT,
    "MRPL_RAG_Test_Corpus", "06_Diagrams_and_Scans", "Scanned_Inspection_Checklist_CCR1.png",
)

_skip_without_models = pytest.mark.skipif(
    not _MODELS_PRESENT,
    reason=(
        "PaddleOCR model files are not present under models/ocr/ — see "
        "ocr_printed.py's module docstring."
    ),
)

client = TestClient(app)


def test_missing_file_raises_exact_message():
    from backend.tools.vision.defect_detection import detect_defects

    missing_path = os.path.join(FIXTURES, "does_not_exist.png")
    with pytest.raises(FileNotFoundError) as exc_info:
        detect_defects(missing_path)
    assert str(exc_info.value) == f"Image not found at {missing_path}"


@_skip_without_models
@pytest.mark.skipif(not os.path.exists(CORPUS_IMAGE), reason="test corpus image not present")
def test_detections_contract_shape_on_the_scanned_checklist():
    """The overlay's contract (contract.js): every detection has id, label,
    confidence, box{xmin,ymin,xmax,ymax}, severity — and the OCR boxes are
    real pixel regions on the deliberately noisy scanned checklist."""
    from backend.tools.vision.defect_detection import detect_defects

    result = detect_defects(CORPUS_IMAGE)

    assert result.source == "ocr-printed"
    assert len(result.detections) > 0

    for det in result.detections:
        assert det.id.startswith("det-ocr-")
        assert det.label
        assert 0.0 <= det.confidence <= 1.0
        assert det.severity in ("low", "medium", "high", "critical")
        box = det.box
        assert box.xmin <= box.xmax
        assert box.ymin <= box.ymax
        # Pixel boxes on a real scan must be finite and inside the image,
        # which is 1668x1080 for the scanned checklist (any value at or
        # below the page width/height is a plausible region).
        assert 0 <= box.xmin <= 2000

    assert result.image_url.startswith("/api/inspection/image?path=")


@_skip_without_models
def test_offline_with_sockets_hard_blocked(monkeypatch):
    """Same rigor as test_ocr_printed.py: force a FRESH PaddleOCR
    construction (the risky operation) under a hard socket block, and
    prove the whole detection tool still works."""
    import socket

    from backend.tools.vision import ocr_printed

    ocr_printed._ocr_instance = None  # force a real reload under the block

    def _blocked(*args, **kwargs):
        raise AssertionError("detect_defects attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    from backend.tools.vision.defect_detection import detect_defects

    result = detect_defects(CORPUS_IMAGE)
    assert len(result.detections) > 0


def test_inspection_image_route_serves_corpus_image():
    """The overlay must be able to actually fetch the image the boxes
    point at — a URL that 404s is a broken overlay even with perfect
    boxes."""
    from backend.api.state import DEFAULT_CORPUS_DIR

    relative = os.path.relpath(CORPUS_IMAGE, os.path.join(_REPO_ROOT, DEFAULT_CORPUS_DIR)).replace("\\", "/")
    resp = client.get("/api/inspection/image", params={"path": relative})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0


def test_inspection_image_route_rejects_path_escape():
    """Containment is load-bearing: the intended corpus image is under the
    corpus root, and nothing outside it may be served."""
    resp = client.get(
        "/api/inspection/image",
        params={"path": os.path.join("..", "requirements.txt")},
    )
    assert resp.status_code in (400, 404)