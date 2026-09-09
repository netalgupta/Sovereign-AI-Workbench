"""Tests for the fetch-once/load-offline pattern in model_cache.py."""

import os

import pytest

from backend.ingestion import model_cache


def test_require_cached_raises_actionable_message_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MODELS_ROOT", tmp_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        model_cache.require_cached("embeddings", "some/unfetched-model")

    message = str(exc_info.value)
    assert "not cached locally" in message
    # Must tell the caller the actual fix, not just that something's wrong.
    assert "fetch_models" in message


def test_require_cached_returns_path_when_populated(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MODELS_ROOT", tmp_path)
    cache_dir = model_cache.local_cache_dir("embeddings", "some/model")
    cache_dir.mkdir(parents=True)
    (cache_dir / "config.json").write_text("{}")

    result = model_cache.require_cached("embeddings", "some/model")

    assert result == cache_dir


def test_require_cached_raises_when_dir_exists_but_empty(tmp_path, monkeypatch):
    # An empty directory is not the same as "actually fetched" — a
    # half-finished download or a stray mkdir must not be mistaken for
    # a valid cache.
    monkeypatch.setattr(model_cache, "MODELS_ROOT", tmp_path)
    cache_dir = model_cache.local_cache_dir("embeddings", "some/model")
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        model_cache.require_cached("embeddings", "some/model")


def test_force_offline_mode_sets_both_env_vars(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    model_cache.force_offline_mode()

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_local_cache_dir_sanitizes_slashes_in_model_id(tmp_path, monkeypatch):
    # Model ids like "BAAI/bge-large-en-v1.5" contain a "/" — that must
    # not be interpreted as a subdirectory separator someone could path-
    # traverse with, or collide with a real "BAAI" folder.
    monkeypatch.setattr(model_cache, "MODELS_ROOT", tmp_path)

    result = model_cache.local_cache_dir("embeddings", "BAAI/bge-large-en-v1.5")

    assert result == tmp_path / "embeddings" / "BAAI__bge-large-en-v1.5"
