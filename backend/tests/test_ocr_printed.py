"""Tests for CARD 05's extract_printed_text.

Skips honestly if the local model copies aren't present (same pattern as
every other model-backed tool in this suite) rather than mocking
PaddleOCR's output — the whole point of testing OCR is whether it
actually reads real pixels correctly.
"""

import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_MODELS_PRESENT = os.path.isdir(os.path.join(_REPO_ROOT, "models", "ocr", "PP-OCRv6_medium_det"))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CORPUS_IMAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "MRPL_RAG_Test_Corpus", "06_Diagrams_and_Scans", "Scanned_Inspection_Checklist_CCR1.png",
)

pytestmark = pytest.mark.skipif(
    not _MODELS_PRESENT,
    reason=(
        "PaddleOCR model files are not present under models/ocr/ — see "
        "ocr_printed.py's module docstring for how they were fetched "
        "(paddleocr's own default download, then copied into this "
        "repo's models/ocr/ convention)."
    ),
)


def test_missing_file_raises_exact_message():
    from backend.tools.vision.ocr_printed import extract_printed_text

    missing_path = os.path.join(FIXTURES, "does_not_exist.png")
    with pytest.raises(FileNotFoundError) as exc_info:
        extract_printed_text(missing_path)
    assert str(exc_info.value) == f"Image not found at {missing_path}"


@pytest.mark.skipif(not os.path.exists(CORPUS_IMAGE), reason="test corpus image not present")
def test_extracts_known_text_from_the_deliberately_noisy_scanned_checklist():
    """The actual OCR-robustness test case the corpus README calls out —
    this image has deliberate rotation + pixel noise applied, and OCR
    must still correctly read the form number/cycle/date that a later
    cross-document-linking test depends on."""
    from backend.tools.vision.ocr_printed import extract_printed_text

    result = extract_printed_text(CORPUS_IMAGE)

    assert "F-140-A" in result.full_text
    assert "CCR-1" in result.full_text
    assert "Cycle No: 18" in result.full_text or "Cycle No:18" in result.full_text.replace(" ", "")
    assert len(result.lines) > 0
    assert all(0.0 <= line.confidence <= 1.0 for line in result.lines)
    assert all(len(line.bbox) == 4 for line in result.lines)


@pytest.mark.skipif(not os.path.exists(CORPUS_IMAGE), reason="test corpus image not present")
def test_offline_with_sockets_hard_blocked(monkeypatch):
    """Same rigor as embeddings.py/voice_transcription.py's equivalent
    tests: force a FRESH PaddleOCR construction (the risky operation --
    that's where a Hub/hoster reachability check would fire) under a
    hard socket block, and prove it still works.
    """
    import socket

    from backend.tools.vision import ocr_printed

    ocr_printed._ocr_instance = None  # force a real reload under the block

    def _blocked(*args, **kwargs):
        raise AssertionError("extract_printed_text attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    result = ocr_printed.extract_printed_text(CORPUS_IMAGE)

    assert "F-140-A" in result.full_text
