import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from backend.models.ollama_client import verify_models_available
from backend.models.registry import ModelConfig

REGISTRY = {
    "coder-model": ModelConfig(
        id="coder-model", backend="ollama", model="qwen2.5-coder:7b", task_tags=["code_generation"]
    ),
    "reasoning-model": ModelConfig(
        id="reasoning-model", backend="ollama", model="qwen2.5:14b", task_tags=["drafting"]
    ),
}


@responses.activate
def test_reports_true_false_per_model():
    responses.add(
        responses.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "qwen2.5-coder:7b"}]},
        status=200,
    )

    result = verify_models_available(REGISTRY)

    assert result == {"coder-model": True, "reasoning-model": False}


@responses.activate
def test_connection_failure_raises_exact_message():
    responses.add(
        responses.GET,
        "http://localhost:11434/api/tags",
        body=RequestsConnectionError("refused"),
    )

    with pytest.raises(ConnectionError, match="Ollama not reachable at http://localhost:11434 — is it running?"):
        verify_models_available(REGISTRY)
