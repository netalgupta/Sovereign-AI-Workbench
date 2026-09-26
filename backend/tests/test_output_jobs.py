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

from backend.orchestrator import output_jobs as J
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
    job = J.run(J.OutputJob(job_id="deck-t1", request="Make a presentation on CCR-1 cycle 18",
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

    job = J.run(J.OutputJob(job_id="deck-t2", request="Make a presentation on CCR-1", session_id="s"))
    req = stubs["gate"]().get(job.approval["id"])
    out = generate_deck(**req.arguments)
    assert Path(out["deck_path"]).exists() and out["slide_count"] >= 2


def test_a_topic_the_corpus_does_not_cover_is_refused_with_no_approval(stubs):
    job = J.run(J.OutputJob(job_id="deck-t3", request="Make a presentation on Diwali recipes", session_id="s"))
    assert job.status == "refused" and "do not cover" in job.error
    assert job.approval is None


def test_an_expired_approval_can_be_asked_for_again_without_redoing_the_job(stubs):
    job = J.run(J.OutputJob(job_id="deck-t4", request="Make a presentation on CCR-1", session_id="s"))
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
    monkeypatch.setattr(J, "start", lambda request, session_id="default", kind="deck":
                        started.append((request, kind))
                        or J.OutputJob(job_id="deck-chat", request=request, session_id=session_id, kind=kind))
    resolved = action_resolver.resolve("Create a presentation on the Hassan incident", "file write")
    assert resolved.job_id == "deck-chat" and resolved.executable is False
    assert started == [("Create a presentation on the Hassan incident", "deck")]
    assert "deck-chat" in action_resolver.deck_job_reply(resolved)


def test_the_decks_api(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setattr(J, "start", lambda request, session_id="default", kind="deck": J._jobs.setdefault(
        "deck-api", J.OutputJob(job_id="deck-api", request=request, session_id=session_id, kind=kind)))
    client = TestClient(app)
    started = client.post("/api/decks", json={"request": "Make a presentation on CCR-1"}).json()
    assert started["job_id"] == "deck-api" and started["status"] == "queued"
    assert "_spec" not in started
    assert client.get("/api/decks/deck-api").json()["job_id"] == "deck-api"
    assert client.get("/api/decks/deck-nope").status_code == 404
    assert client.post("/api/decks/deck-api/approval").status_code == 409  # nothing finished to approve
    assert client.post("/api/decks", json={"request": "  "}).status_code == 400


# ── model routing and the GPU hand-off ──────────────────────────────────────


def test_one_writer_by_measurement_not_by_size():
    """Routing by size sent most requests to qwen2.5:14b: 588 s to plan and
    206 s a section on this card, scoring the same as the 7b on the corpus
    QA set. The large writer stays registered for hardware that can hold it."""
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry
    from backend.orchestrator import deck_agent as D

    assert D.choose_writer([{"text": "x" * 40000}]) == D.WRITER_SMALL
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


def test_the_embedding_model_is_released_with_the_others():
    """Measured: bge-large on CUDA (1.26 GiB) pushed part of the 4-bit reviewer off the GPU."""
    from backend.ingestion import embeddings  # noqa: F401 - registers on import
    from backend.models import gpu

    assert "embedding-model" in gpu._RELEASERS


def test_a_quantized_reviewer_that_does_not_fit_is_refused_not_returned_broken(tmp_path, monkeypatch):
    """Placed partly on the CPU, every 4-bit call failed "Cannot copy out of meta tensor"."""

    import torch
    import transformers

    import backend.ingestion.model_cache as mc
    from backend.models import gpu
    from backend.models import local_vision as LV

    monkeypatch.setattr(mc, "MODELS_ROOT", tmp_path)
    weights = tmp_path / "vision" / "org__vl"
    weights.mkdir(parents=True)
    (weights / "config.json").write_text("{}")
    (weights / "model.safetensors").write_bytes(b"x")
    registry = tmp_path / "models.yaml"
    registry.write_text("- id: v\n  backend: transformers\n  model: org/vl\n  task_tags: [t]\n"
                        "  placement: {gpu_memory_gib: 4, cpu_memory_gib: 2, quantization: 4bit}\n")
    monkeypatch.setenv("MODELS_REGISTRY_PATH", str(registry))

    class Half(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.a = torch.nn.Linear(10, 10, bias=False)
            self.b = torch.nn.Linear(10, 10, bias=False)
            self.hf_device_map = {"a": 0, "b": "cpu"}

        def eval(self):
            return self

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(gpu, "make_room_for", lambda name: [])
    monkeypatch.setattr(gpu, "cuda_free_gib", lambda: 7.0)
    monkeypatch.setattr(transformers.Qwen2_5_VLForConditionalGeneration, "from_pretrained",
                        classmethod(lambda cls, *a, **k: Half()))
    monkeypatch.setattr(transformers, "BitsAndBytesConfig", lambda **k: None)
    monkeypatch.setattr(transformers.AutoProcessor, "from_pretrained",
                        classmethod(lambda cls, *a, **k: object()))
    LV.release()
    with pytest.raises(LV.LocalVisionUnavailable, match="cannot run from system RAM"):
        LV.load("v")
    assert LV.placement_report() is None, "nothing broken is left loaded"


# ── documents and spreadsheets go through the same pipeline ─────────────────


DOC_SPEC = {
    "title": "CCR-1 regeneration cycle 18",
    "subtitle": "Findings and actions",
    "sections": [{"heading": "Cycle 18 ran six hours long", "body": "Cycle 18 took 34 hours "
                  "against a target of 28 hours, six hours beyond plan.", "sources": ["S1"],
                  "contains_estimate": False}],
    "documents": ["Inspection_Report_CCR1.pdf"],
    "dropped_sections": ["Costs: these figures are in no source document: 4200"],
    "writer": "reasoning-model",
    "topic": "ccr-1 regeneration cycle 18",
}
SHEET_SPEC = {
    "title": "Batch QA",
    "sheets": [{"sheet_name": "Batches", "headers": ["Grade", "MFI"],
                "rows": [{"cells": ["H030SG", "3.4"], "sources": ["S1"], "is_unsourced": False},
                         {"cells": ["H110F", ""], "sources": ["S1"], "is_unsourced": False}],
                "emptied_cells": 1}],
    "documents": ["Novolen_Batch_QA_Report.pdf"],
    "dropped_sheets": [],
    "writer": "reasoning-model",
    "emptied_cells": 1,
}


@pytest.fixture
def doc_stubs(tmp_path, monkeypatch):
    from backend.audit import approval_gate
    from backend.orchestrator import action_resolver, document_agent

    J.reset_for_tests()
    monkeypatch.setattr(document_agent, "build_document_spec", lambda *a, **k: DOC_SPEC)
    monkeypatch.setattr(document_agent, "build_spreadsheet_spec", lambda *a, **k: SHEET_SPEC)

    class Gate(approval_gate.ApprovalGate):
        def __init__(self, *a, **k):
            super().__init__(requests_file=tmp_path / "requests.jsonl")

    monkeypatch.setattr(approval_gate, "ApprovalGate", Gate)
    monkeypatch.setattr(action_resolver, "OUTPUT_DIR", tmp_path / "outputs")
    import backend.api.state as state

    monkeypatch.setattr(state, "get_state", lambda: type("S", (), {
        "ensure_corpus": lambda self: (object(), [])})())
    return Gate


@pytest.mark.parametrize("kind, tool, suffix", [
    ("docx", "draft_docx", ".docx"),
    ("pdf", "generate_pdf", ".pdf"),
])
def test_a_document_job_asks_for_approval_of_what_it_wrote(doc_stubs, kind, tool, suffix):
    job = J.run(J.OutputJob(job_id=f"{kind}-t", request="Draft a report on CCR-1 cycle 18",
                            session_id="s", kind=kind))
    assert job.status == "awaiting_approval", job.error
    req = doc_stubs().get(job.approval["id"])
    assert req.tool_name == tool
    assert req.arguments["output_path"].endswith(suffix)
    section = req.arguments["sections"][0]
    # Source IDS are for the model; the file prints DOCUMENT NAMES.
    assert section["sources"] == ["Inspection_Report_CCR1.pdf"]
    assert "34 hours" in section["body"]
    assert any("1 section(s) written" in line for line in job.approval["preview"])
    assert any("1 dropped for lack of a source" in line for line in job.approval["preview"])
    # The approval screen names the file it writes. Without a target it read
    # "Target not resolved by the system" above that very file name.
    assert job.approval["target"] == req.arguments["output_path"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    # The file is named after its subject, not the deployment: a summary of
    # a cyber-security textbook was saved as "MRPL_Understanding_Cyber…pdf".
    assert not job.approval["target"].startswith("MRPL_")
    # Nothing is written before approval, so the preview must not say it was.
    assert not any(line.startswith("Written to") for line in job.approval["preview"])


def test_a_spreadsheet_job_keeps_unsourced_cells_empty(doc_stubs):
    job = J.run(J.OutputJob(job_id="xlsx-t", request="Build an Excel comparison of batch MFI",
                            session_id="s", kind="xlsx"))
    assert job.status == "awaiting_approval", job.error
    req = doc_stubs().get(job.approval["id"])
    assert req.tool_name == "draft_xlsx"
    assert req.arguments["output_path"].endswith(".xlsx")
    rows = req.arguments["sheets"][0]["rows"]
    assert [r["cells"] for r in rows] == [["H030SG", "3.4"], ["H110F", ""]]
    assert any("1 cell(s) left EMPTY" in line for line in job.approval["preview"])


def test_the_approved_document_call_writes_the_file(doc_stubs, tmp_path):
    from backend.tools.documents.draft_docx import draft_docx

    job = J.run(J.OutputJob(job_id="docx-w", request="Draft a report on CCR-1", session_id="s", kind="docx"))
    args = doc_stubs().get(job.approval["id"]).arguments
    result = draft_docx(**args)
    assert Path(result.file_path).exists()


@pytest.mark.parametrize("request_text, kind", [
    ("Create a presentation on the CCR-1 findings", "deck"),
    ("Build an Excel comparison table of batch MFI values", "xlsx"),
    ("Draft a PDF report on the Hassan incident", "pdf"),
    ("Draft an approval note on the inspection findings and save it", "docx"),
])
def test_the_request_decides_the_deliverable(request_text, kind, monkeypatch):
    from backend.orchestrator import action_resolver

    assert action_resolver.output_kind_for(request_text) == kind
    started = []
    monkeypatch.setattr(J, "start", lambda request, session_id="default", kind="deck":
                        started.append(kind)
                        or J.OutputJob(job_id=f"{kind}-x", request=request, session_id=session_id, kind=kind))
    resolved = action_resolver.resolve(request_text, "file write")
    assert started == [kind] and resolved.job_id == f"{kind}-x"


# ── an approved file is where the Outputs page looks ────────────────────────


def test_an_approved_file_appears_in_the_outputs_listing(stubs, tmp_path, monkeypatch):
    """MEASURED: approvals wrote to outputs/ while /api/outputs listed
    storage/outputs/, so the Outputs page never showed anything the
    operator had approved."""
    from fastapi.testclient import TestClient

    from backend.orchestrator.slide_agent import generate_deck
    from backend.main import app

    job = J.run(J.OutputJob(job_id="deck-out", request="Make a presentation on CCR-1", session_id="s"))
    written = generate_deck(**stubs["gate"]().get(job.approval["id"]).arguments)
    name = Path(written["deck_path"]).name

    listed = TestClient(app).get("/api/outputs").json()["files"]
    assert any(f["filename"] == name for f in listed), (
        f"{name} was approved and written, but the Outputs page does not list it")
    assert TestClient(app).get(f"/api/outputs/{name}/download").status_code == 200


def test_a_download_cannot_escape_the_outputs_directory():
    from fastapi.testclient import TestClient

    from backend.main import app

    assert TestClient(app).get("/api/outputs/..%2F..%2Fmodels%2Fmodels.yaml/download").status_code == 404


def test_the_outputs_listing_shows_deliverables_not_working_files(tmp_path, monkeypatch):
    """The approval ledger and audit log sit beside the documents as .jsonl;
    listing them as generated outputs invites opening a log as a report."""
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.orchestrator import action_resolver

    out = tmp_path / "outputs"
    out.mkdir()
    (out / "report.docx").write_bytes(b"x")
    (out / "requests.jsonl").write_text("{}")
    (out / "audit.jsonl").write_text("{}")
    monkeypatch.setattr(action_resolver, "OUTPUT_DIR", out)
    monkeypatch.chdir(tmp_path)

    names = {f["filename"] for f in TestClient(app).get("/api/outputs").json()["files"]}
    assert names == {"report.docx"}


@pytest.mark.parametrize("kind", ["deck", "docx", "pdf", "xlsx"])
def test_every_kind_files_arguments_its_tool_actually_takes(kind):
    """MEASURED: an approved PDF failed at execution with "generate_pdf does
    not take ['subtitle']" — the operator had authorised a document that
    could not be written. The gate cannot catch this; the signature can."""
    import inspect

    from backend.tools import catalog  # noqa: F401 — importing registers every tool
    from backend.tools.registry import get_tool

    name = J.KINDS[kind][1]
    tool = get_tool(name)
    assert tool is not None, f"{name} is not registered, so approving it could never execute"
    accepted = set(inspect.signature(tool.func).parameters)
    filed = ({"deck_spec", "output_path"} if kind == "deck"
             else {"title", "subtitle", "sections", "output_path"} if kind in ("docx", "pdf")
             else {"title", "sheets", "output_path"})
    assert filed <= accepted, f"{J.KINDS[kind][1]} does not take {sorted(filed - accepted)}"


@pytest.mark.parametrize("state, expected", [("executed", "written"), ("refused", "declined"), ("pending", "awaiting_approval")])
def test_a_job_follows_its_approval_to_written_or_declined(monkeypatch, state, expected):
    """After the file was approved and written, the Artifacts tab still
    listed the job as 'Waiting for your approval'."""
    from backend.audit import approval_gate as G

    class FakeGate:
        def get(self, request_id):
            assert request_id == "req-1"
            return type("R", (), {"state": G.ApprovalState(state)})()

    monkeypatch.setattr(G, "ApprovalGate", FakeGate)
    job = J.OutputJob(job_id="xlsx-t", request="r", session_id="s", kind="xlsx")
    job.status = "awaiting_approval"
    job.approval = {"id": "req-1", "target": "Sheet.xlsx"}
    assert job.public()["status"] == expected
    if expected == "written":
        assert "Sheet.xlsx" in job.detail
