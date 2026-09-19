from __future__ import annotations

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

import re

from sympy import simplify
from sympy.parsing.sympy_parser import parse_expr
from pydantic import BaseModel


class CalcResult(BaseModel):
    expression: str
    result: str
    steps: list[str]


# Statistical function names a model reaches for when it wants
# describe_series. Matched at the START of the expression so an
# ordinary algebraic use of a variable called `mode` is untouched.
_STATISTICAL_CALL = re.compile(
    r"^(mean|average|avg|median|mode|variance|var|stddev|std|stdev|"
    r"standard_deviation|percentile|quartile|sum|count)\s*\(",
    re.I,
)


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
        # AN ERROR THAT DOES NOT SAY WHAT TO DO INSTEAD BECOMES A LOOP.
        #
        # Measured on a real turn: asked for the mean, median, variance
        # and standard deviation of two spreadsheet columns, the model
        # called this tool twelve times with mean([...]), median([...]),
        # variance([...]), stddev([...]) -- every one a ValueError
        # reading "Could not parse expression". With nothing in the
        # message to correct against, it tried the same shape again,
        # burned all eight iterations and 237 seconds, and returned no
        # answer.
        #
        # These are not unreasonable calls. Statistics over a list IS a
        # thing this workbench does -- in describe_series, a different
        # tool. The gap was never told to the one place that could say
        # so. SymPy is a SYMBOLIC engine: `mean` is not one of its
        # functions, and it never will be.
        statistic = _STATISTICAL_CALL.match(expression.strip())
        if statistic:
            raise ValueError(
                f"{statistic.group(1)}() is not a symbolic function, so this tool "
                f"cannot evaluate {expression!r}. Statistics over a list of "
                f"readings are computed by the describe_series tool, which returns "
                f"mean, median, standard deviation, variance, min, max and "
                f"quartiles in one call. Call it with the numbers as a plain list: "
                f'describe_series(values=[99.914, 99.872, ...]). Use this tool for '
                f"arithmetic and algebra instead, e.g. '(12 + 8) * 3'."
            ) from exc

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
