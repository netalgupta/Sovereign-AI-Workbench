"""Presentations as background jobs.

Model calls, artwork and the page reviewer are stubbed; the renderer, the
job stages, the approval gate and the API are real. What matters here:
nothing reaches outputs/ before approval, the approval carries the deck
that was REVIEWED (with its fixes) and says how it scored, a refusal or a
crash is reported as one, and chat starts a job instead of blocking.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.orchestrator import deck_jobs as J
from backend.tools.generation.deck import improve as I
from backend.tools.generation.deck import qa

SPEC = {
    "title": "CCR-1 regeneration cycle 18 ran six hours long",
    "sources": [{"id": "S1", "document": "Inspection_Report_CCR1.pdf", "pages": [1]}],
    "sections": [{"title": "What happened", "slides": [
        {"type": "points", "title": "Cycle 18 ran 34 hours against a 28-hour target",
         "bullets": ["Cycle 18 took 34 hours.", "The target is 28 hours."], "sources": ["S1"]}]}],
}
QUALITY = qa.DeckQuality(score=6.6, grade="C", method="layout+vision", pages=[
    qa.PageQuality(page=1, title="", score=6.6, vision_score=6.6)], reviewed_by="Qwen/Qwen2.5-VL-7B-Instruct",
    pages_reviewed=1)


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    import copy

    from backend.audit import approval_gate
    from backend.orchestrator import action_resolver, slide_agent
    from backend.tools.generation.deck import art

    J.reset_for_tests()
    seen: dict = {}

    def prepare(request, session_id="default", max_slides=None):
        if "diwali" in request.lower():
            from backend.orchestrator.deck_agent import NotInCorpus

            raise NotInCorpus("The documents in the corpus do not cover this request.")
        return {"deck_spec": copy.deepcopy(SPEC), "filename": "MRPL_CCR1.pptx",
                "slide_titles": ["Cycle 18 ran 34 hours against a 28-hour target"],
                "citations": ["Inspection_Report_CCR1.pdf"], "omitted_sections": [],
                "writer": "reasoning-model"}

    def fake_improve(spec, out_path, *, vision=True, max_rounds=2, progress=None):
        seen["preview_path"] = Path(out_path)
        seen["artwork_flag"] = spec.get("artwork")
        fixed = copy.deepcopy(spec)
        fixed["sections"][0]["slides"][0]["max_items"] = 1  # a fix the loop kept
        return I.Improvement(QUALITY, fixed, str(out_path),
                             rounds=[I.Round(1, {"0/0": 1}, ["0/0"], [], 5.5, 6.6)])

    class Gate(approval_gate.ApprovalGate):
        def __init__(self, *a, **k):
            super().__init__(requests_file=tmp_path / "requests.jsonl")

    monkeypatch.setattr(slide_agent, "prepare_deck", prepare)
    monkeypatch.setattr(I, "improve", fake_improve)
    monkeypatch.setattr(art, "styled", lambda *a, **k: None)
    monkeypatch.setattr(approval_gate, "ApprovalGate", Gate)
    monkeypatch.setattr(action_resolver, "OUTPUT_DIR", tmp_path / "outputs")
    seen["gate"] = Gate
    return seen


def test_a_job_writes_nothing_and_asks_for_the_reviewed_deck(stubs, tmp_path):
    job = J.run(J.DeckJob(job_id="deck-t1", request="Make a presentation on CCR-1 cycle 18",
                          session_id="s"))
    assert job.status == "awaiting_approval", job.error
    assert not (tmp_path / "outputs").exists(), "nothing is written before approval"
    assert not stubs["preview_path"].parent.exists(), "previews live in a temp dir that is removed"
    assert stubs["artwork_flag"] is True

    req = stubs["gate"]().get(job.approval["id"])
    assert req.tool_name == "generate_deck"
    approved_spec = req.arguments["deck_spec"]
    assert approved_spec["sections"][0]["slides"][0]["max_items"] == 1, "the approved spec is the FIXED one"
    assert any("design 6.6/10 (grade C)" in line and "Qwen2.5-VL-7B-Instruct" in line
               for line in job.approval["preview"]), job.approval["preview"]
    assert job.quality["score"] == 6.6 and job.rounds[0]["kept"] == ["0/0"]
    assert job.writer == "reasoning-model"


def test_the_approved_call_renders_exactly_the_reviewed_deck(stubs, tmp_path):
    from backend.orchestrator.slide_agent import generate_deck

    job = J.run(J.DeckJob(job_id="deck-t2", request="Make a presentation on CCR-1", session_id="s"))
    req = stubs["gate"]().get(job.approval["id"])
    out = generate_deck(**req.arguments)
    assert Path(out["deck_path"]).exists() and out["slide_count"] >= 2


def test_a_topic_the_corpus_does_not_cover_is_refused_with_no_approval(stubs):
    job = J.run(J.DeckJob(job_id="deck-t3", request="Make a presentation on Diwali recipes", session_id="s"))
    assert job.status == "refused" and "do not cover" in job.error
    assert job.approval is None


def test_an_expired_approval_can_be_asked_for_again_without_redoing_the_job(stubs):
    job = J.run(J.DeckJob(job_id="deck-t4", request="Make a presentation on CCR-1", session_id="s"))
    first = job.approval["id"]
    again = J.request_approval(job)
    assert again["id"] != first
    assert stubs["gate"]().get(again["id"]).arguments["deck_spec"] == stubs["gate"]().get(first).arguments["deck_spec"]


def test_a_crash_is_reported_on_the_job(stubs, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("PowerPoint went away")

    monkeypatch.setattr(I, "improve", boom)
    job = J.start("Make a presentation on CCR-1", session_id="s")
    deadline = time.time() + 20
    while job.status not in ("failed", "awaiting_approval") and time.time() < deadline:
        time.sleep(0.05)
    assert job.status == "failed" and "PowerPoint went away" in job.error
    assert job.finished_at is not None


@pytest.mark.parametrize("quality, expected", [
    (None, "not checked"),
    ({"method": "unavailable"}, "not checked"),
    ({"method": "layout", "score": None, "pages": [{}] * 7, "layout_defect_pages": 0},
     "layout measured on 7 pages, no defects; design not reviewed"),
    ({"method": "layout+vision", "score": 6.6, "grade": "C", "pages": [{}] * 7, "pages_reviewed": 7,
      "layout_defect_pages": 1, "reviewed_by": "Qwen/Qwen2.5-VL-7B-Instruct"},
     "design 6.6/10 (grade C) by Qwen2.5-VL-7B-Instruct on 7 pages; layout measured on 7 pages, 1 with defects"),
])
def test_the_quality_line_says_what_was_checked(quality, expected):
    assert expected in J.quality_line(quality)


# ── chat starts a job instead of blocking ───────────────────────────────────


def test_a_deck_request_in_chat_starts_a_job_and_files_no_approval_yet(monkeypatch):
    from backend.orchestrator import action_resolver

    started = []
    monkeypatch.setattr(J, "start", lambda request, session_id="default": started.append(request)
                        or J.DeckJob(job_id="deck-chat", request=request, session_id=session_id))
    resolved = action_resolver.resolve("Create a presentation on the Hassan incident", "file write")
    assert resolved.job_id == "deck-chat" and resolved.executable is False
    assert started == ["Create a presentation on the Hassan incident"]
    assert "deck-chat" in action_resolver.deck_job_reply(resolved)


def test_the_decks_api(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setattr(J, "start", lambda request, session_id="default": J._jobs.setdefault(
        "deck-api", J.DeckJob(job_id="deck-api", request=request, session_id=session_id)))
    client = TestClient(app)
    started = client.post("/api/decks", json={"request": "Make a presentation on CCR-1"}).json()
    assert started["job_id"] == "deck-api" and started["status"] == "queued"
    assert "_spec" not in started
    assert client.get("/api/decks/deck-api").json()["job_id"] == "deck-api"
    assert client.get("/api/decks/deck-nope").status_code == 404
    assert client.post("/api/decks/deck-api/approval").status_code == 409  # nothing finished to approve
    assert client.post("/api/decks", json={"request": "  "}).status_code == 400


# ── model routing and the GPU hand-off ──────────────────────────────────────


def test_long_sources_go_to_the_large_writer():
    from backend.orchestrator import deck_agent as D
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    short = [{"text": "x" * 2000}]
    long = [{"text": "x" * 6000}, {"text": "y" * 6000}]
    assert D.choose_writer(short) == D.WRITER_SMALL
    assert D.choose_writer(long) == D.WRITER_LARGE
    registry = load_registry(_DEFAULT_REGISTRY_PATH)
    assert D.WRITER_SMALL in registry and D.WRITER_LARGE in registry


def test_loading_one_in_process_model_releases_the_others(monkeypatch):
    from backend.models import gpu

    calls = []
    monkeypatch.setattr(gpu, "_RELEASERS", {"image-model": lambda: calls.append("image-model"),
                                            "page-reviewer": lambda: calls.append("page-reviewer")})
    monkeypatch.setattr(gpu, "free_ollama_vram", lambda: ["qwen2.5:7b"])
    released = gpu.make_room_for("page-reviewer")
    assert calls == ["image-model"]
    assert released == ["image-model", "qwen2.5:7b"]


def test_both_in_process_models_register_for_release():
    from backend.models import gpu, local_vision  # noqa: F401 - registers on import
    from backend.tools.generation.deck import art  # noqa: F401

    assert {"image-model", "page-reviewer"} <= set(gpu._RELEASERS)
