"""Tests for describe_chart_image — CARD 13.

Mocked HTTP throughout, deliberately: this suite runs alongside other
work that may already have a real Ollama call in flight against the
configured vision model, and mocking here means these tests never add
to that contention. A live-model sanity check belongs in a manual
verification pass, not the automated suite's default path, given how
much slower this dev machine's CPU/partial-GPU-offload inference is
than the intended venue hardware (see entity_extraction.py's own
timeout-bump commit for the measured numbers).
"""

import os

import pytest
import responses

from backend.tools.vision.chart_understanding import ChartVisualDescription, describe_chart_image

GENERATE_URL = "http://localhost:11434/api/generate"
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_native.pdf")  # any real file works


@responses.activate
def test_describe_chart_image_returns_response_text():
    responses.add(
        responses.POST,
        GENERATE_URL,
        json={"response": "Bar chart titled 'Widgets Sold'. Y-axis: units. Data label '22' printed on the March bar."},
        status=200,
    )

    result = describe_chart_image(FIXTURE)

    assert isinstance(result, ChartVisualDescription)
    assert "22" in result.description
    assert result.is_estimate is True  # always, by design -- see module docstring


@responses.activate
def test_request_includes_base64_image_and_correct_model():
    import base64
    import json

    responses.add(responses.POST, GENERATE_URL, json={"response": "ok"}, status=200)

    describe_chart_image(FIXTURE)

    sent = json.loads(responses.calls[0].request.body)
    assert sent["model"] == "qwen2-vl:7b"  # models.yaml's vision-model, resolved through the registry
    assert len(sent["images"]) == 1
    # Confirm it's real base64 of the actual file, not a placeholder.
    decoded = base64.b64decode(sent["images"][0])
    with open(FIXTURE, "rb") as f:
        assert decoded == f.read()


def test_missing_file_raises_before_any_request():
    missing_path = os.path.join(os.path.dirname(__file__), "fixtures", "does_not_exist.png")
    with pytest.raises(FileNotFoundError) as exc_info:
        describe_chart_image(missing_path)
    assert str(exc_info.value) == f"Image not found at {missing_path}"
