"""Write code for a plan step, then run it in the sandbox.

THE MISSING LINK, AND IT WAS SMALLER THAN IT LOOKED.

The problem statement names "a coding task run and verified in a
sandbox" as one of five demonstrations. Both halves already existed:

  - `backend/sandbox/` runs untrusted code with --network none, and its
    egress isolation is PROVEN by test rather than configured.
  - `dispatch.run_code_step(step, code, ...)` executes it and returns a
    real ToolCallEvent.

Nothing connected them. `run_code_step` takes `code: str` and no caller
ever produced one: the graph's `code` branch ran a FIXED probe that
verified the sandbox worked, which is a genuine thing to check and is
not a coding task.

WHY THIS IS A SEPARATE MODULE. Generation and execution are different
trust levels. What comes back from a model is a string; it becomes
behaviour only inside the sandbox. Keeping the boundary explicit means
the one place code is written is also the one place it is read before
being run, and nothing else in the codebase can hand a string to the
sandbox by accident.

NO GPU IS NEEDED TO WORK ON THIS. The sandbox is Docker and CPU-only;
`run_code_step` takes the code as a parameter, so the whole
dispatch -> execute -> report path can be built and tested with a fixed
string. The model runs wherever the workbench runs. That matters because
CARD 04's owner does not have a GPU, and none of the work that is
actually his requires one.

VERIFIED MEANS THE OUTPUT WAS CHECKED, NOT THAT IT RAN. A sandbox
returning exit code 0 says the code did not crash. The PS says "run and
verified", so the step reports stdout, exit code, and whether the code
produced any output at all -- a program that runs and prints nothing has
not demonstrated anything, and reporting that as success is the same
mistake as the fixed probe.
"""

from __future__ import annotations

import re

from backend.models.registry import resolve_model_name

# Fenced code, with or without a language tag. Models wrap code in
# fences far more often than not, and feeding the fence markers to a
# Python interpreter is an immediate SyntaxError that looks like the
# model failing when it did not.
_FENCE = re.compile(r"```(?:python|py|javascript|js|node)?\s*\n(.*?)```", re.S | re.I)

_PROMPT = (
    "Write a short, complete {language} program that does exactly this:\n\n"
    "{task}\n\n"
    "Rules:\n"
    "- Output ONLY the program. No explanation before or after.\n"
    "- It must PRINT its result. A program that computes silently has "
    "shown nothing.\n"
    "- It runs with NO NETWORK ACCESS and no third-party packages. "
    "Standard library only.\n"
    "- It must terminate on its own. No input(), no servers, no waiting.\n"
)


class CodeGenerationError(RuntimeError):
    """The model did not return usable code."""


def extract_code(raw: str) -> str:
    """The program inside a model's reply.

    Returns the first fenced block if there is one, otherwise the reply
    stripped. Raises rather than returning something unrunnable: handing
    prose to an interpreter produces a SyntaxError that reads as the
    sandbox failing.
    """
    if not raw or not raw.strip():
        raise CodeGenerationError("The model returned nothing.")

    match = _FENCE.search(raw)
    code = match.group(1) if match else raw

    code = code.strip()
    if not code:
        raise CodeGenerationError("The model returned an empty code block.")

    # A reply with no code-shaped line at all is prose, and running it
    # wastes a sandbox round-trip to produce a misleading error.
    if not re.search(r"^\s*(?:import |from |def |class |print\(|[\w\[\]]+\s*=)", code, re.M):
        raise CodeGenerationError(
            f"The model replied with prose rather than code: {code[:160]!r}"
        )
    return code


# A request for a FILE TO READ, not a program to run. Measured 27 Sep: "Write a
# single self-contained HTML page ... with a button that counts clicks" went
# down the run-it-in-the-sandbox path, the model correctly returned an html
# block, and extract_code() rejected it as "prose rather than code" -- the
# user got a failure for a correct answer. Pages, markup, config, SQL and
# multi-file projects are written and returned; they are not executed.
_SOURCE_ONLY = re.compile(
    r"\b(html|css|web ?page|landing page|svg|ya?ml|json|toml|ini|dockerfile|docker[- ]compose|compose file|"
    r"kubernetes|k8s|manifest|nginx|config(?:uration)? file|\.env|requirements\.txt|sql|schema|"
    r"separate files|multiple files|several files|project structure|as files)\b",
    re.I,
)


def wants_source_only(task: str) -> bool:
    """Is this a request for source to read (a page, config, a project), not a program to run?"""
    return bool(task and _SOURCE_ONLY.search(task))


_SOURCE_PROMPT = (
    "Write exactly what is asked:\n\n{task}\n\n"
    "Rules:\n"
    "- Give each file as its own fenced code block with the right language tag.\n"
    "- When there is more than one file, put the line 'File: relative/path/name.ext' "
    "directly above each file's block.\n"
    "- A web page must be self-contained: inline CSS and JavaScript, no external "
    "links, fonts, images or CDNs (it is shown offline).\n"
    "- One short sentence before the code saying what it is. No other prose.\n"
)


def write_source(task: str, model_id: str = "coder-model") -> str:
    """The code model's files for `task`, as markdown with fenced blocks. Not executed."""
    from backend.models.ollama_client import generate as ollama_generate

    raw = ollama_generate(resolve_model_name(model_id), _SOURCE_PROMPT.format(task=task.strip()))
    if not raw or "```" not in raw:
        raise CodeGenerationError("The model returned no code block.")
    return raw.strip()


def generate_code(task: str, language: str = "python", model_id: str = "coder-model") -> str:
    """Ask the code model for a program that performs `task`.

    `model_id` is a REGISTRY ID, not a model name (hard constraint #2):
    the tag is resolved through models.yaml so the orchestration layer
    never names a model.
    """
    from backend.models.ollama_client import generate as ollama_generate

    prompt = _PROMPT.format(language=language, task=task.strip())
    raw = ollama_generate(resolve_model_name(model_id), prompt)
    return extract_code(raw)


def run_generated_code(
    step,
    task: str,
    session_id: str = "default",
    language: str = "python",
    model_id: str = "coder-model",
):
    """Generate code for `task`, execute it in the sandbox, return the event.

    The returned ToolCallEvent carries the code that ran in its
    input_params, deliberately: an execution record that does not
    include what was executed cannot be reviewed, and "the sandbox
    returned 0" is not evidence of anything on its own.
    """
    from backend.observability import turn_log as T
    from backend.orchestrator.dispatch import run_code_step

    T.section("CODE GENERATION")
    T.kv("task", task[:90])
    T.kv("language", language)

    code = generate_code(task, language=language, model_id=model_id)
    T.block("GENERATED CODE", code)

    event = run_code_step(step, code, session_id=session_id, language=language)

    # The code is part of the record. Without it the audit trail says a
    # program ran and cannot say which.
    event.input_params = {**(event.input_params or {}), "code": code, "task": task}

    output = event.output or {}
    stdout = (output.get("stdout") or "").strip()
    if event.status == "done" and not stdout:
        # Ran cleanly and printed nothing. Reporting that as success is
        # the same mistake as the fixed probe it replaced.
        event.status = "failed"
        event.output = {
            **output,
            "verification": "The program exited cleanly but printed nothing, so "
                            "it demonstrated no result.",
        }
        step.status = "failed"
    elif event.status == "done":
        event.output = {**output, "verification": f"Produced output: {stdout[:200]}"}

    return event
