"""Local deck artwork and the multi-backend model registry.

No test here loads the image model (a 55-second cold load). What is
tested is everything around it that decides whether it is used safely:
that the registry knows it is not an Ollama tag, that nothing tells the
operator to `ollama pull` it, that a missing model degrades to the vector
design, and that the prompts ask for abstraction and never equipment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models import registry as R
from backend.tools.generation.deck import art, render


def _cfg(backend: str, model: str) -> R.ModelConfig:
    return R.ModelConfig(id="x", backend=backend, model=model, task_tags=["t"])


def test_the_registry_accepts_a_diffusers_backend_and_checks_it_on_disk(tmp_path, monkeypatch):
    import backend.ingestion.model_cache as mc

    monkeypatch.setattr(mc, "MODELS_ROOT", tmp_path)
    cfg = _cfg("diffusers", "stabilityai/sd-turbo")
    assert R.is_locally_available(cfg, set()) is False

    weights = tmp_path / "image" / "stabilityai__sd-turbo"
    weights.mkdir(parents=True)
    (weights / "model_index.json").write_text("{}")
    assert R.is_locally_available(cfg, set()) is True


def test_an_ollama_entry_is_unknown_when_ollama_is_unreachable():
    assert R.is_locally_available(_cfg("ollama", "qwen2.5:7b"), None) is None
    assert R.is_locally_available(_cfg("ollama", "qwen2.5:7b"), {"qwen2.5:7b"}) is True


def test_the_real_registry_names_the_new_roles():
    reg = R.load_registry(R._DEFAULT_REGISTRY_PATH)
    assert reg["image-model"].backend == "diffusers"
    assert reg["deck-writer-large"].backend == "ollama"


def test_the_models_listing_never_says_ollama_pull_for_the_image_model():
    from fastapi.testclient import TestClient

    from backend.main import app

    models = {m["id"]: m for m in TestClient(app).get("/api/models").json()["models"]}
    detail = models["image-model"]["detail"] or ""
    assert "ollama pull" not in detail


def test_prompts_ask_for_abstraction_and_exclude_equipment():
    """A generated picture of a plant would be a fabricated record."""
    for key in ("Hydrocracker catalyst changeout", "CCR-1 regeneration", "Hassan pipeline incident"):
        prompt = art.prompt_for(key).lower()
        assert "abstract" in prompt
        assert "no machines" in prompt and "no people" in prompt and "no text" in prompt
        for banned in ("refinery", "reactor", "pipeline", "plant", "hydrocracker"):
            assert banned not in prompt, f"prompt names equipment: {banned}"


def test_a_missing_image_model_falls_back_to_the_vector_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "styled", lambda *a, **k: None)
    spec = {"title": "CCR-1 findings", "artwork": True, "sources": [],
            "sections": [{"title": "S", "slides": [{"type": "points", "title": "A finding worth a slide",
                                                     "bullets": ["One.", "Two."]}]}]}
    result = render.render_deck(spec, tmp_path / "d.pptx")
    assert result["slide_count"] >= 2


def test_artwork_is_opt_in_so_ordinary_renders_never_load_a_model(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the image model was touched without artwork: true")

    monkeypatch.setattr(art, "styled", boom)
    spec = {"title": "CCR-1 findings", "sources": [],
            "sections": [{"title": "S", "slides": [{"type": "points", "title": "A finding worth a slide",
                                                     "bullets": ["One.", "Two."]}]}]}
    render.render_deck(spec, tmp_path / "d.pptx")
