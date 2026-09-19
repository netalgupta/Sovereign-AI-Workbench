"""Tests for describe_image — TOOLS.md row 72, FR-14.

Mocked HTTP throughout, for the same reason as test_chart_understanding.py:
a live-model sanity check belongs in a manual verification pass, not in a
suite that may already share the box's single Ollama vision model with
other in-flight work. The off-line patterns below (base64 of the real
fixture, registry dispatch) are what would catch a description pipeline
that registers but cannot execute — the recurring failure this repo has
measured and learned to test for.
"""

import os

import pytest
import responses

from backend.tools import catalog  # noqa: F401 - registers every tool
from backend.tools.registry import call_tool, get_tool
from backend.tools.vision.image_description import ImageDescription, describe_image

GENERATE_URL = "http://localhost:11434/api/generate"
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_native.pdf")  # any real file works


@responses.activate
def test_describe_image_returns_response_text():
    responses.add(
        responses.POST,
        GENERATE_URL,
        json={
            "response": (
                "This is a P&ID schematic. It depicts a hydrocracker section with a "
                "reactor vessel connected to two feed lines. Printed label 'RC-101' "
                "is visible."
            )
        },
        status=200,
    )

    result = describe_image(FIXTURE)

    assert isinstance(result, ImageDescription)
    assert "reactor" in result.description
    assert result.is_estimate is True  # always, by design -- see module docstring


@responses.activate
def test_request_includes_base64_image_and_correct_model():
    import base64
    import json

    responses.add(responses.POST, GENERATE_URL, json={"response": "ok"}, status=200)

    describe_image(FIXTURE)

    sent = json.loads(responses.calls[0].request.body)
    assert sent["model"] == "qwen2.5vl:7b"  # models.yaml's vision-model, resolved through the registry
    assert len(sent["images"]) == 1
    # Confirm it's real base64 of the actual file, not a placeholder.
    decoded = base64.b64decode(sent["images"][0])
    with open(FIXTURE, "rb") as f:
        assert decoded == f.read()


def test_missing_file_raises_before_any_request():
    missing_path = os.path.join(os.path.dirname(__file__), "fixtures", "does_not_exist.png")
    with pytest.raises(FileNotFoundError) as exc_info:
        describe_image(missing_path)
    assert str(exc_info.value) == f"Image not found at {missing_path}"


@responses.activate
def test_describe_image_is_registered_and_executes_through_the_registry():
    """Rule 1: a tool is not built until it has been CALLED the way the
    orchestrator calls it. Importing the module and checking `/api/tools`
    would prove nothing past import-time correctness."""
    assert get_tool("describe_image") is not None

    responses.add(
        responses.POST,
        GENERATE_URL,
        json={"response": "A photograph of a pump station."},
        status=200,
    )
    result = call_tool("describe_image", {"image_path": FIXTURE})

    assert isinstance(result, ImageDescription)
    assert result.is_estimate is True
    assert "pump" in result.description