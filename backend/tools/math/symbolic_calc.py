"""SymPy verified calculation tool — VIBECODING_SPEC.md CARD 08.

WHY THIS FILE EXISTS AT ALL (read this before touching anything below):
CLAUDE.md hard constraint #3 says no numeric result may come from an LLM
"doing arithmetic in its head." An LLM predicts the *next likely token* —
it has no arithmetic circuit, so for anything beyond trivial sums it will
occasionally produce a plausible-looking wrong number with full
confidence, and nothing in its output distinguishes a correct answer from
a hallucinated one. The fix isn't "use a smarter model" — it's structural:
the agent is never allowed to state a number that didn't come out of an
executed, deterministic function. This module IS that function for
algebra/calculus. AGENTS_SPEC.md §6 encodes this as a hard rule: the
`math_tool` graph node is forbidden from ever constructing an LLM call at
all — it's a direct Python function call, full stop.

WHY sympy.parsing.sympy_parser.parse_expr AND NEVER eval():
`eval("2*x+3")` on a string that ultimately traces back to an LLM's output
is arbitrary code execution — an LLM (or a prompt-injected document) could
just as easily produce "os.system('rm -rf /')" as "2*x+3" and eval() would
run it. parse_expr only ever builds a SymPy expression tree; it cannot
execute arbitrary Python. This is a security boundary, not a style choice.
"""

from sympy import simplify
from sympy.parsing.sympy_parser import parse_expr
from pydantic import BaseModel


class CalcResult(BaseModel):
    expression: str
    result: str
    steps: list[str]


def evaluate_expression(
    expression: str,
    variables: dict[str, float] | None = None,
) -> CalcResult:
    """Symbolically parse, substitute, and simplify `expression`.

    Args:
        expression: a math expression as a string, e.g. "2*x + 3".
            Never passed through eval() — see module docstring.
        variables: optional {name: value} substitutions, e.g. {"x": 5}.

    Returns:
        CalcResult with the original expression, the final result as a
        string (not a float — this preserves exact fractions/symbolic
        forms like `3/4` or `sqrt(2)` instead of lossy decimal rounding,
        which matters when an engineering calc gets quoted verbatim into
        an approval note), and the intermediate `steps` shown so a human
        reviewer can actually check the work, not just trust a number.

    Raises:
        ValueError: exactly f"Could not parse expression: {expression!r}"
            if `expression` isn't valid SymPy syntax. No "best guess"
            fallback — a calculation tool that silently guesses at a
            malformed expression is worse than one that refuses.
    """
    try:
        parsed = parse_expr(expression)
    except Exception as exc:
        # SymPy raises several different exception types depending on
        # *how* the string fails to parse (SyntaxError, TokenError,
        # AttributeError for some malformed inputs, etc.) — CARD 08 wants
        # one predictable exception type for callers, so we normalize all
        # of them here rather than making every caller know SymPy's
        # internal parser error taxonomy.
        raise ValueError(f"Could not parse expression: {expression!r}") from exc

    steps: list[str] = [str(parsed)]
    current = parsed

    if variables:
        current = current.subs(variables)
        steps.append(str(current))

    simplified = simplify(current)
    if str(simplified) != steps[-1]:
        steps.append(str(simplified))

    return CalcResult(
        expression=expression,
        result=str(simplified),
        steps=steps,
    )
