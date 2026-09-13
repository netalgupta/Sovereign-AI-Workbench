"""Tests for CARD 08's evaluate_expression.

Teaching note on the last test in this file: CARD 08's own "definition of
done" says to grep the file for the literal string "eval(" as a lint
check. A naive substring grep is fragile in both directions here — this
very file's module docstring *talks about* eval() as the exact thing to
avoid, so a dumb grep would false-positive on its own documentation. The
correct tool for "does this code call the eval() builtin" is Python's own
`ast` module: parse the source, walk it, and check whether any Call node's
function is literally named `eval`. That's immune to comments, docstrings,
and string literals, and it's the same technique a real linter (e.g.
bandit's B307 rule) uses under the hood.
"""

import ast
import inspect

import pytest

from backend.tools.math import symbolic_calc
from backend.tools.math.symbolic_calc import evaluate_expression


def test_evaluate_expression_with_variables():
    result = evaluate_expression("2*x + 3", {"x": 5})

    assert result.result == "13"
    assert len(result.steps) >= 1
    assert result.expression == "2*x + 3"


def test_evaluate_expression_preserves_exact_symbolic_form():
    # 1/3 must stay a fraction, never lossy float rounding (0.333...) —
    # this is the whole point of using SymPy instead of just eval()-ing
    # into a Python float.
    result = evaluate_expression("1/3")

    assert result.result == "1/3"


def test_malformed_expression_raises_exact_message():
    bad_expression = "2 * x +"
    with pytest.raises(ValueError) as exc_info:
        evaluate_expression(bad_expression)

    assert str(exc_info.value) == f"Could not parse expression: {bad_expression!r}"


def test_no_eval_call_anywhere_in_the_module():
    """AST-based check, not a string grep — see module docstring."""
    source = inspect.getsource(symbolic_calc)
    tree = ast.parse(source)

    eval_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "eval"
    ]

    assert eval_calls == [], "symbolic_calc.py must never call the eval() builtin"


def test_a_statistical_call_is_redirected_to_the_tool_that_can_do_it():
    """MEASURED on a real turn: asked for mean, median, variance and
    standard deviation of two spreadsheet columns, the model called this
    tool TWELVE times with mean([...]), median([...]), variance([...]),
    stddev([...]). Every one raised "Could not parse expression", which
    told it nothing, so it tried the same shape again -- burning all
    eight iterations and 237 seconds and returning no answer.

    The calls were not unreasonable. Statistics over a list IS something
    this workbench does, in describe_series. Nothing told the one place
    that could say so.
    """
    import pytest

    from backend.tools.math.symbolic_calc import evaluate_expression

    for expression in (
        "mean([99.914, 99.872, 99.939])",
        "median([1, 2, 3])",
        "variance([1, 2, 3])",
        "stddev([1, 2, 3])",
        "mode([1, 1, 2])",
    ):
        with pytest.raises(ValueError) as exc:
            evaluate_expression(expression)
        message = str(exc.value)
        assert "describe_series" in message, (
            f"{expression} failed without naming the tool that can do it: {message}"
        )
        # The correct call SHAPE, not just the tool name -- the failure
        # mode was the model not knowing what to type next.
        assert "values=" in message


def test_ordinary_algebra_is_untouched_by_the_redirect():
    """The redirect matches a statistical call at the START of the
    expression, so algebra that merely contains such a word is not
    hijacked."""
    from backend.tools.math.symbolic_calc import evaluate_expression

    assert evaluate_expression("(12 + 8) * 3").result == "60"
    assert evaluate_expression("2*x + 3", variables={"x": 5}).result == "13"
