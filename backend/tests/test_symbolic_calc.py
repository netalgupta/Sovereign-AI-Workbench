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
