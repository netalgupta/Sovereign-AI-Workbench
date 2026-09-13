"""Generate code, run it in the sandbox, and check it showed something.

The problem statement names "a coding task run and verified in a
sandbox" as one of five demonstrations. Both halves existed and nothing
connected them: run_code_step(step, code) executes untrusted code with
--network none, and no caller ever produced a `code` string. The graph's
code branch ran a FIXED socket probe instead -- honest about what it
proved, and not a coding task.

NONE OF THESE TESTS NEED A GPU, which is the point: the sandbox is
Docker and CPU-only, and generation is stubbed here. CARD 04's owner can
build and verify the whole dispatch -> execute -> report path without
one.
"""

import pytest

from backend.orchestrator.code_generation import (
    CodeGenerationError,
    extract_code,
)


def test_a_fenced_block_is_unwrapped():
    """Models wrap code in fences far more often than not, and feeding
    the fence markers to an interpreter is an immediate SyntaxError that
    reads as the model failing when it did not."""
    raw = "Here you go:\n\n```python\nprint(6 * 7)\n```\n\nThat prints 42."
    assert extract_code(raw) == "print(6 * 7)"


def test_an_untagged_fence_works_too():
    assert extract_code("```\nimport math\nprint(math.pi)\n```") == (
        "import math\nprint(math.pi)"
    )


def test_bare_code_with_no_fence_is_accepted():
    assert extract_code("print('hello')") == "print('hello')"


def test_prose_is_refused_rather_than_executed():
    """Running prose produces a SyntaxError inside the sandbox, which
    looks like the sandbox failing. Refusing here names the real
    problem."""
    with pytest.raises(CodeGenerationError) as exc:
        extract_code("I'm sorry, I can't help with that request.")
    assert "prose" in str(exc.value)


def test_an_empty_reply_is_refused():
    with pytest.raises(CodeGenerationError):
        extract_code("")
    with pytest.raises(CodeGenerationError):
        extract_code("```python\n\n```")


def test_the_registry_supplies_the_model_name_not_the_code():
    """Hard constraint #2: only models.yaml names a model. The
    orchestration layer passes a registry id."""
    import inspect

    from backend.orchestrator import code_generation

    source = inspect.getsource(code_generation)
    assert 'model_id: str = "coder-model"' in source
    assert "resolve_model_name" in source
    # No literal Ollama tag anywhere in the module.
    assert "qwen" not in source.lower()


# ---------------------------------------------------------------------
# The verification half. "Ran" is not "verified".
# ---------------------------------------------------------------------


class _Step:
    def __init__(self):
        self.status = "pending"
        self.description = "print the first five square numbers"


def _fake_event(stdout, exit_code=0):
    from backend.orchestrator.state import ToolCallEvent

    return ToolCallEvent(
        tool_name="sandbox_python",
        input_params={"language": "python"},
        output={"stdout": stdout, "exit_code": exit_code},
        status="done" if exit_code == 0 else "failed",
    )


def test_code_that_runs_but_prints_nothing_is_not_a_success(monkeypatch):
    """A sandbox returning exit code 0 says the code did not crash. The
    PS says "run AND verified", and a program that prints nothing has
    demonstrated nothing -- reporting that as success is the same
    mistake as the fixed probe this replaced."""
    from backend.orchestrator import code_generation

    monkeypatch.setattr(code_generation, "generate_code", lambda *a, **k: "x = 1")
    monkeypatch.setattr(
        "backend.orchestrator.dispatch.run_code_step",
        lambda step, code, **kw: _fake_event(""),
    )

    step = _Step()
    event = code_generation.run_generated_code(step, step.description)

    assert event.status == "failed"
    assert step.status == "failed"
    assert "printed nothing" in event.output["verification"]


def test_code_that_prints_a_result_is_reported_with_that_result(monkeypatch):
    from backend.orchestrator import code_generation

    monkeypatch.setattr(
        code_generation, "generate_code", lambda *a, **k: "print([i*i for i in range(1,6)])"
    )
    monkeypatch.setattr(
        "backend.orchestrator.dispatch.run_code_step",
        lambda step, code, **kw: _fake_event("[1, 4, 9, 16, 25]"),
    )

    step = _Step()
    event = code_generation.run_generated_code(step, step.description)

    assert event.status == "done"
    assert "[1, 4, 9, 16, 25]" in event.output["verification"]


def test_the_executed_code_is_part_of_the_record(monkeypatch):
    """An execution record that does not include what was executed
    cannot be reviewed. "The sandbox returned 0" is not evidence."""
    from backend.orchestrator import code_generation

    program = "print(6 * 7)"
    monkeypatch.setattr(code_generation, "generate_code", lambda *a, **k: program)
    monkeypatch.setattr(
        "backend.orchestrator.dispatch.run_code_step",
        lambda step, code, **kw: _fake_event("42"),
    )

    event = code_generation.run_generated_code(_Step(), "multiply six by seven")

    assert event.input_params["code"] == program
    assert event.input_params["task"] == "multiply six by seven"
