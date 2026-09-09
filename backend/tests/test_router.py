"""Tests for CARD 03's classify_task.

Two tiers, deliberately kept separate:

1. Plumbing tests (mocked via `responses`) — verify prompt formatting,
   code-fence stripping, the one-shot retry-on-bad-JSON, graceful dropping
   of hallucinated tags, and the exact ValueError after two failures.
   These run fully offline, every time, no Ollama required.

2. The FR-3 20-prompt accuracy test — runs against a REAL local Ollama
   instance (localhost:11434, not an external call). It is skipped, not
   faked, when Ollama isn't running: mocking canned "correct" answers here
   would fabricate the exact kind of proof CARD 07's anti-hallucination
   note warns against, just for a different tool. Run it for real once
   phi-3.5-mini is pulled locally (`ollama pull phi-3.5-mini`).
"""

import json
import os

import pytest
import requests
import responses

from backend.models.registry import resolve_model_name
from backend.orchestrator.router import VALID_TASK_TAGS, classify_task

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "router_test_set.json")
GENERATE_URL = "http://localhost:11434/api/generate"


def _mock_generate(text: str):
    responses.add(responses.POST, GENERATE_URL, json={"response": text}, status=200)


def _router_model_actually_pulled() -> bool:
    """Not just "is Ollama up" — is the specific model classify_task will
    call actually pulled. Discovered on this exact dev machine: Ollama is
    running, but with qwen2.5:7b / llama3:8b / nomic-embed-text /
    budget-bandhu pulled — none of which is phi-3.5-mini (models.yaml's
    fast-router). Skip rather than let that 404 masquerade as a router bug.
    """
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=0.5)
        response.raise_for_status()
        pulled = {entry["name"] for entry in response.json().get("models", [])}
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return False
    try:
        resolved_model = resolve_model_name("fast-router")
    except (FileNotFoundError, ValueError):
        return False
    return resolved_model in pulled


@responses.activate
def test_classify_task_parses_clean_json_response():
    _mock_generate('["code_generation", "code_review"]')

    tags = classify_task("write and review a function")

    assert tags == ["code_generation", "code_review"]


@responses.activate
def test_classify_task_strips_markdown_code_fences():
    _mock_generate('```json\n["summarization"]\n```')

    tags = classify_task("summarize this report")

    assert tags == ["summarization"]


@responses.activate
def test_classify_task_retries_once_on_bad_json_then_succeeds():
    _mock_generate("not json at all")
    _mock_generate('["planning"]')

    tags = classify_task("plan my week")

    assert tags == ["planning"]
    assert len(responses.calls) == 2


@responses.activate
def test_classify_task_raises_after_two_failures():
    _mock_generate("still not json")
    _mock_generate("nope, still not json")

    with pytest.raises(ValueError, match="Router could not classify"):
        classify_task("gibberish request")


@responses.activate
def test_classify_task_drops_tags_outside_fixed_list():
    _mock_generate('["code_generation", "math", "vision"]')

    tags = classify_task("some request")

    assert tags == ["code_generation"]
    assert all(tag in VALID_TASK_TAGS for tag in tags)


@pytest.mark.skipif(
    not _router_model_actually_pulled(),
    reason=(
        "phi-3.5-mini (models.yaml's fast-router) is not pulled on this "
        "Ollama instance — skipping the live FR-3 accuracy test rather than "
        "mocking canned answers, which would fabricate the accuracy proof. "
        "Run `ollama pull phi-3.5-mini` to exercise this for real, or "
        "repoint models.yaml's fast-router entry at a model already pulled "
        "on this dev machine (see DEPENDENCIES.md §1 for the tier design)."
    ),
)
def test_router_accuracy_against_fixture_meets_fr3_threshold():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    cases = fixture["cases"]
    correct = 0
    for case in cases:
        predicted = set(classify_task(case["prompt"]))
        expected = set(case["expected_tags"])
        if predicted == expected:
            correct += 1

    accuracy = correct / len(cases)
    assert accuracy >= 0.90, f"Router accuracy {accuracy:.0%} fell below FR-3's 90% threshold"
