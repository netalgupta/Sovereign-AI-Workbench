"""Model auto-selection: the task decides the model, and the registry names it.

The problem statement's expected demo is "model auto selection across at
least two different task types". Before this, every chat turn on the
streaming path ran on the same model.
"""

from __future__ import annotations

import pytest

from backend.orchestrator import model_select as M


@pytest.mark.parametrize("request_text, task", [
    ("Write a Python function that returns the first 10 Fibonacci numbers", "code_generation"),
    ("Fix this script so it reads the CSV properly", "code_generation"),
    ("Run a SQL query to count the batches", "code_generation"),
    ("Summarise the CCR-1 inspection findings", "summarization"),
    ("What does SOP-114 say about nitrogen blanketing?", "question_answering"),
    ("Draft an approval note on the Hassan incident", "drafting"),
    ("Make an Excel sheet comparing the average MFI of each grade", "drafting"),
    # Measured in the chat UI: this was labelled "summarization" on screen.
    ("Convert a flow of 1450 cubic metres per hour to barrels per day and show the working.", "calculation"),
    ("How much hydrogen does 12 t/h of feed need at 1.8 wt%?", "calculation"),
    ("What is the plot of Pride and Prejudice?", "question_answering"),
    ("Summarise the Cyber Security book into a 10 to 20 page PDF report.", "summarization"),
])
def test_the_request_decides_the_task(request_text, task):
    assert M.task_of(request_text)[0] == task


def test_two_task_types_get_two_different_models_from_the_registry():
    code = M.select("Write a Python script that prints the primes below 50")
    doc = M.select("Summarise the CCR-1 inspection findings")
    assert code.model_id != doc.model_id, "a coding request must not run on the document model"
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    registry = load_registry(_DEFAULT_REGISTRY_PATH)
    assert "code_generation" in registry[code.model_id].task_tags


def test_no_model_name_is_written_in_the_selector():
    """Hard constraint #2: only models.yaml names a model."""
    import inspect

    src = inspect.getsource(M)
    import re

    # Real model tags, not the word "llama" inside "ollama".
    assert not re.search(r"qwen|llama3|phi3|mistral|:\d+b\b", src.lower())


def test_a_task_no_model_is_tagged_for_falls_back_to_the_default(tmp_path, monkeypatch):
    registry = tmp_path / "models.yaml"
    registry.write_text("- id: reasoning-model\n  backend: ollama\n  model: some-model\n"
                        "  task_tags: [summarization]\n", encoding="utf-8")
    monkeypatch.setenv("MODELS_REGISTRY_PATH", str(registry))
    assert M.model_for_task("code_generation") == "reasoning-model"


def test_an_in_process_model_is_never_chosen_for_a_chat_turn(tmp_path, monkeypatch):
    registry = tmp_path / "models.yaml"
    registry.write_text(
        "- id: page-reviewer\n  backend: transformers\n  model: org/vl\n  task_tags: [code_generation]\n"
        "  placement: {gpu_memory_gib: 4, cpu_memory_gib: 2}\n"
        "- id: coder-model\n  backend: ollama\n  model: some-coder\n  task_tags: [code_generation]\n",
        encoding="utf-8")
    monkeypatch.setenv("MODELS_REGISTRY_PATH", str(registry))
    assert M.model_for_task("code_generation") == "coder-model"


# ── the streaming turn says which model it chose, and uses it ───────────────


def test_a_code_request_is_routed_written_run_and_reported(monkeypatch):
    from backend.orchestrator import agent_loop, code_generation
    from backend.orchestrator.state import ToolCallEvent

    used = {}

    def fake_run(step, task, session_id="default", language="python", model_id="x"):
        used["model_id"] = model_id
        return ToolCallEvent(tool_name="run_in_sandbox", status="done",
                             input_params={"code": "print([0, 1, 1, 2, 3])", "task": task},
                             output={"stdout": "[0, 1, 1, 2, 3]\n", "verification": "Produced output"})

    monkeypatch.setattr(code_generation, "run_generated_code", fake_run)
    events = list(agent_loop.run_turn("Write a Python function that prints the first 5 Fibonacci numbers",
                                      session_id="t-select"))
    route = next(e for e in events if e["type"] == "route")
    assert route["task"] == "code_generation" and route["model_id"] == used["model_id"]
    done = next(e for e in events if e["type"] == "done")
    assert "Verified" in done["reply"] and "[0, 1, 1, 2, 3]" in done["reply"]
    assert route["model"] in done["reply"], "the reply names the model that wrote the code"


def test_a_document_question_is_routed_to_the_document_model():
    from backend.orchestrator.path_router import decide_path

    s = M.select("Summarise the CCR-1 inspection findings")
    assert s.task == "summarization" and s.model_id == M.model_for_task("summarization")
    assert decide_path("Summarise the CCR-1 inspection findings").path != "approval"


def test_every_task_the_selector_names_has_a_model_tagged_for_it():
    """A task no model is tagged for silently falls back to the default --
    the label on screen would then name a task the registry never chose for."""
    tagged = {t for cfg in M._registry().values() for t in cfg.task_tags}
    for request in ("Convert 5 bar to kPa", "What is PSA?", "Draft a memo on the outage",
                    "Summarise the SOP", "Write a Python script that adds two numbers"):
        assert M.task_of(request)[0] in tagged, request
