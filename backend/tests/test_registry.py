import os

import pytest
from pydantic import ValidationError

from backend.models.registry import load_registry, resolve_model_name

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
    assert registry["vision-model"].model == "qwen2.5vl:7b"
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


def test_resolve_model_name_maps_registry_id_to_real_model_tag():
    sample_path = os.path.join(FIXTURES, "sample_models.yaml")

    assert resolve_model_name("fast-router", registry_path=sample_path) == "phi-3.5-mini"
    assert resolve_model_name("reasoning-model", registry_path=sample_path) == "qwen2.5:14b"


def test_resolve_model_name_raises_for_unknown_id():
    sample_path = os.path.join(FIXTURES, "sample_models.yaml")

    with pytest.raises(ValueError, match="Unknown model id 'not-a-real-id'"):
        resolve_model_name("not-a-real-id", registry_path=sample_path)


def test_resolve_model_name_uses_this_repos_real_models_yaml_by_default():
    # No registry_path override -- exercises the actual default path
    # resolution against this repo's real /models/models.yaml, not a
    # test fixture. If this breaks, the real registry file moved or
    # changed shape.
    assert resolve_model_name("fast-router") == "phi-3.5-mini"
