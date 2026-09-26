"""Which model does this request need? Chosen per task, from the registry.

THE PROBLEM STATEMENT ASKS FOR THIS BY NAME: "automatically pick the right
one for a given task based on what that task needs, a coding request
handled differently from a document summary request", and the expected
demo is "model auto selection across at least two different task types".

The LLM router (router.classify_task, CARD 03) was taken out of the chat
path because it cost ~37 s a turn, and nothing replaced it: every chat
turn ran on the same model. This decides from the request's own wording
-- the same deterministic approach path_router uses -- and then asks the
REGISTRY which model is tagged for that task. No model is named here
(hard constraint #2): adding a better coder is an edit to models.yaml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# A request that asks for a program to be written, fixed or run.
_CODE = re.compile(
    r"\b(write|create|generate|build|implement|fix|debug|refactor|run|execute)\b[^.?!]{0,60}"
    r"\b(code|script|program|function|class|snippet|algorithm|regex|query|python|javascript|"
    r"node|sql|unit test|tests?)\b"
    r"|\b(python|javascript|typescript|sql|bash|powershell)\s+(code|script|program|function)\b"
    r"|```",
    re.I,
)


@dataclass(frozen=True)
class Selection:
    task: str          # a models.yaml task tag
    model_id: str      # the registry id tagged for it
    model: str         # the real tag it resolves to, for the trace and the UI
    reason: str


def _registry():
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    return load_registry(os.environ.get("MODELS_REGISTRY_PATH", _DEFAULT_REGISTRY_PATH))


def model_for_task(task: str, *, default: str = "reasoning-model") -> str:
    """The first chat-capable registry entry tagged for `task`, else `default`.

    Chat-capable means served by Ollama: an in-process model (the image
    model, the page reviewer) is not something a chat turn can run on.
    """
    for model_id, cfg in _registry().items():
        if cfg.backend == "ollama" and task in cfg.task_tags:
            return model_id
    return default


def task_of(request: str) -> tuple[str, str]:
    """The task a request is, and why."""
    if _CODE.search(request or ""):
        return "code_generation", "asks for a program to be written and run"
    return "summarization", "a question or document task, answered from the sources"


def select(request: str) -> Selection:
    from backend.models.registry import resolve_model_name

    task, why = task_of(request)
    model_id = model_for_task(task)
    return Selection(task=task, model_id=model_id, model=resolve_model_name(model_id),
                     reason=f"{task.replace('_', ' ')}: {why}")
