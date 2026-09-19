"""In-process vision model: the registry sets the GPU/CPU split, not a scheduler.

Nothing here loads the model. What is tested is what decides whether it
is used safely: that placement comes from models.yaml, that a half-done
download is not "available", that the budget never exceeds the free card,
that a missing model degrades to an unreviewed page rather than a score,
and that page review goes where the registry says.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.models import local_vision as LV
from backend.models import registry as R
from backend.tools.generation.deck import qa


def _write_registry(tmp_path: Path, entries: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(entries, encoding="utf-8")
    return path


def test_the_real_registry_gives_the_page_reviewer_an_explicit_placement():
    cfg = R.load_registry(R._DEFAULT_REGISTRY_PATH)["page-reviewer"]
    assert cfg.backend == "transformers"
    assert cfg.placement is not None
    assert 0 < cfg.placement.gpu_memory_gib < 8, "the dev card is 8 GB"
    assert cfg.placement.cpu_memory_gib > 0


def test_a_half_finished_download_is_not_available(tmp_path, monkeypatch):
    import backend.ingestion.model_cache as mc

    monkeypatch.setattr(mc, "MODELS_ROOT", tmp_path)
    cfg = R.ModelConfig(id="v", backend="transformers", model="org/vl", task_tags=["t"],
                        placement={"gpu_memory_gib": 4, "cpu_memory_gib": 2})
    d = tmp_path / "vision" / "org__vl"
    d.mkdir(parents=True)
    (d / "config.json").write_text("{}")
    (d / "model.safetensors.index.json").write_text(json.dumps(
        {"weight_map": {"a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}))
    (d / "model-00001-of-00002.safetensors").write_bytes(b"x")
    assert R.is_locally_available(cfg, None) is False
    (d / "model-00002-of-00002.safetensors").write_bytes(b"x")
    assert R.is_locally_available(cfg, None) is True


def test_the_fetch_command_is_never_ollama_pull_for_an_in_process_model():
    cfg = R.load_registry(R._DEFAULT_REGISTRY_PATH)["page-reviewer"]
    cmd = R.fetch_command(cfg)
    assert "ollama pull" not in cmd
    assert cfg.model in cmd


def test_the_fetcher_accepts_the_id_the_registry_prints():
    from backend.ingestion import fetch_models

    for cfg in R.load_registry(R._DEFAULT_REGISTRY_PATH).values():
        if cfg.backend != "ollama":
            assert cfg.model in fetch_models._FETCHERS, f"{R.fetch_command(cfg)} would be rejected"


def test_an_ollama_entry_cannot_be_loaded_in_process(tmp_path, monkeypatch):
    path = _write_registry(tmp_path, "- id: v\n  backend: ollama\n  model: qwen2.5vl:3b\n  task_tags: [t]\n")
    monkeypatch.setenv("MODELS_REGISTRY_PATH", str(path))
    with pytest.raises(LV.LocalVisionUnavailable, match="ollama"):
        LV.load("v")


def test_missing_weights_say_how_to_fetch_them(tmp_path, monkeypatch):
    import backend.ingestion.model_cache as mc

    monkeypatch.setattr(mc, "MODELS_ROOT", tmp_path)
    path = _write_registry(tmp_path, (
        "- id: v\n  backend: transformers\n  model: org/vl\n  task_tags: [t]\n"
        "  placement: {gpu_memory_gib: 4, cpu_memory_gib: 2}\n"))
    monkeypatch.setenv("MODELS_REGISTRY_PATH", str(path))
    with pytest.raises(LV.LocalVisionUnavailable, match="fetch_models --model org/vl"):
        LV.load("v")


def test_weight_accounting_follows_the_device_map():
    import torch

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.a = torch.nn.Linear(10, 10, bias=False)  # 100 params
            self.b = torch.nn.Linear(10, 30, bias=False)  # 300 params

    m = Tiny()
    m.hf_device_map = {"a": 0, "b": "cpu"}
    by_dev = LV._weight_bytes_by_device(m)
    assert by_dev == {"gpu": 100 * 4, "cpu": 300 * 4}


# ── page review routing ─────────────────────────────────────────────────────


def test_the_page_score_is_computed_from_the_ratings_not_asked_for():
    reply = ('```json\n{"balance": 5, "readability": 5, "hierarchy": 1, "finish": 1, '
             '"fix": "the title sits too high"}\n```')
    review = qa._parse_review(reply)
    assert review["score"] == 5.5  # mean 3 of 1..5 -> 5.5 of 1..10
    assert review["ratings"] == {"balance": 5, "readability": 5, "hierarchy": 1, "finish": 1}
    assert review["issues"] == ["the title sits too high"]


def test_the_extremes_map_to_one_and_ten():
    lo = '{"balance": 1, "readability": 1, "hierarchy": 1, "finish": 1, "fix": ""}'
    hi = '{"balance": 5, "readability": 5, "hierarchy": 5, "finish": 5, "fix": ""}'
    assert qa._parse_review(lo)["score"] == 1.0
    assert qa._parse_review(hi) == {"score": 10.0, "ratings": dict.fromkeys(qa.DIMENSIONS, 5), "issues": []}


def test_an_out_of_range_rating_is_no_review_not_a_clamped_one():
    assert qa._parse_review('{"balance": 7, "readability": 3, "hierarchy": 3, "finish": 3}') is None


def test_a_range_instead_of_a_rating_is_no_review():
    """Observed from the 3B model: "balance": "2-5"."""
    assert qa._parse_review('{"balance": "2-5", "readability": 3, "hierarchy": 3, "finish": 3}') is None
    assert qa._parse_review('{"readability": 3, "hierarchy": 3, "finish": 3}') is None


def test_the_rubric_does_not_list_what_powerpoint_measures():
    """A rubric naming "overlapping text" was echoed back on pages measured to have none."""
    rubric = qa._RUBRIC.lower()
    for measured in ("overlap", "cut off", "too small"):
        assert measured not in rubric


def test_page_review_goes_in_process_when_the_registry_says_transformers(tmp_path, monkeypatch):
    calls = []

    def fake_ask(model_id, image, prompt, *, max_new_tokens):
        calls.append(model_id)
        return '{"balance": 4, "readability": 4, "hierarchy": 4, "finish": 4, "fix": "tight margins"}'

    monkeypatch.setattr(LV, "ask", fake_ask)
    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("page review went to Ollama")))
    review = qa.review_page(str(tmp_path / "p.png"))
    assert review["score"] == 7.8 and review["issues"] == ["tight margins"]
    assert calls == [qa.REVIEWER_ID]


def test_a_failed_review_is_none_so_the_page_is_reported_unreviewed(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise LV.LocalVisionUnavailable("no CUDA device")

    monkeypatch.setattr(LV, "ask", boom)
    assert qa.review_page(str(tmp_path / "p.png")) is None


def test_assess_without_powerpoint_gives_no_score_rather_than_a_guess(monkeypatch):
    monkeypatch.setattr(qa, "render_and_measure", lambda *a, **k: None)
    result = qa.assess("missing.pptx")
    assert result.score is None and result.grade == "unrated" and result.method == "unavailable"


def test_assess_releases_the_reviewer_after_the_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "render_and_measure", lambda *a, **k: {
        "pngs": ["p1.png", "p2.png"], "defects": {1: [], 2: ["overflow"]},
        "titles": {1: "A", 2: "B"}, "words": {1: 10, 2: 20}})
    monkeypatch.setattr(qa, "review_page", lambda png: {"score": 8, "issues": []})
    released = []
    monkeypatch.setattr(LV, "release", lambda: released.append(True))
    result = qa.assess("d.pptx")
    assert released == [True]
    assert result.method == "layout+vision"
    assert [p.score for p in result.pages] == [8.0, 6.0]  # overflow costs 2 points
    assert result.score == 7.0 and result.grade == "B"
