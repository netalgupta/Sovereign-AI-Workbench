import os

import pytest
from pydantic import ValidationError

from backend.models.registry import load_registry

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_load_registry_returns_exact_four_entries():
    registry = load_registry(os.path.join(FIXTURES, "sample_models.yaml"))

    assert len(registry) == 4
    assert set(registry.keys()) == {
        "coder-model",
        "reasoning-model",
        "vision-model",
        "fast-router",
    }
    assert registry["coder-model"].model == "qwen2.5-coder:7b"
    assert registry["reasoning-model"].model == "qwen2.5:14b"
    assert registry["vision-model"].model == "qwen2-vl:7b"
    assert registry["fast-router"].model == "phi-3.5-mini"


def test_missing_file_raises_exact_message():
    # Windows paths contain backslashes, which pytest.raises(match=...) would
    # otherwise interpret as regex escapes — compare the literal message instead.
    missing_path = os.path.join(FIXTURES, "does_not_exist.yaml")
    with pytest.raises(FileNotFoundError) as exc_info:
        load_registry(missing_path)
    assert str(exc_info.value) == f"Model registry not found at {missing_path}"


def test_malformed_entry_raises_unmodified_validation_error():
    with pytest.raises(ValidationError):
        load_registry(os.path.join(FIXTURES, "malformed_models.yaml"))
