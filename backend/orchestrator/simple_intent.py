"""Recognise requests that need no plan, and skip the planner for them.

WHY. Measured on a warm process, a single factual question costs:

    planner (LLM)        10.9s
    retrieval             0.2s
    generation (LLM)      4.3s
    self-verification     7.5s
    ------------------------------
    total                23.0s

The planner costs more than twice what it takes to ACTUALLY ANSWER the
question, and for a single-intent lookup it contributes nothing. Worse,
it contributes noise: asked "What is the average MFI for Homopolymer
H030SG?" it emitted a `math` step to "calculate the average" -- there is
nothing to calculate, the value is printed in the source table, and the
step ran evaluate_expression which correctly reported "no arithmetic
expression found". Asked "Give sops for Hydrocrackers" it emitted a
`code` step to "create standard operating procedures", which dispatched
to the sandbox and failed. A planner inventing work that does not exist
is not neutral overhead; it produces failed steps in the trace and
tempts the dispatcher into running tools nobody needed.

There is a second, less obvious cost. The planner runs on
reasoning-model (~5.5 GB resident) and the verifier on fast-router
(~4.0 GB). That is 9.5 GB on an 8.2 GB card, so Ollama evicts and
reloads a model twice per turn. Removing the planner call for simple
questions removes one of those swaps as a side effect.

WHAT COUNTS AS SIMPLE. One question, one intent, answerable by
retrieving and reading. That is the overwhelming majority of what this
workbench is asked. Anything with conjoined asks ("and then", "also",
"compare X with Y"), an action verb, or a computation gets the real
planner -- those are the cases a DAG is actually for.

FAILS TOWARDS THE PLANNER. If the shape is not clearly simple, the LLM
planner runs. A missed simple case costs 11 seconds; a complex request
wrongly treated as simple loses steps silently, which is far worse.
"""

from __future__ import annotations

import re

# Conjunction or enumeration implying more than one deliverable.
_MULTI_PART = re.compile(
    r"\b(and then|then also|after that|followed by|as well as|"
    r"in addition|additionally|also,|plus,|,\s*and\s+(also|then))\b"
    r"|\band\s+(compare|calculate|compute|draft|write|generate|create|plot|"
    r"chart|export|send|summarise|summarize)\b",
    re.I,
)

# Genuinely needs a tool step beyond retrieve-and-read.
_NEEDS_WORK = re.compile(
    r"\b(calculate|compute|convert|plot|chart|graph|draft|write|generate|"
    r"create|produce|export|save|send|email|update|delete|modify|set|"
    r"increase|decrease|adjust|simulate|model|estimate|project|forecast|"
    r"trend|extrapolate|interpolate)\b",
    re.I,
)

# Comparison across items usually benefits from an explicit plan.
_COMPARATIVE = re.compile(
    r"\b(compare|versus|vs\.?|difference between|differences between|"
    r"which of|rank|correlat)\b",
    re.I,
)

# Arithmetic present in the text itself.
_ARITHMETIC = re.compile(r"\d\s*[-+*/^]\s*\(?\s*\d")

# A plain informational request.
_QUESTION_OPENER = re.compile(
    r"^\s*(what|which|who|whom|whose|when|where|why|how|is|are|was|were|"
    r"does|do|did|can|could|should|would|has|have|had|list|show|tell|give|"
    r"find|explain|describe|summari[sz]e|define|name)\b",
    re.I,
)

# Length guard. A long request usually carries more than one ask even
# when it dodges every pattern above, so it goes to the planner.
_MAX_SIMPLE_WORDS = 40


def is_simple_lookup(request: str) -> bool:
    """True when this needs one retrieval and one answer, nothing else."""
    if not request or not request.strip():
        return False
    text = request.strip()

    if len(text.split()) > _MAX_SIMPLE_WORDS:
        return False
    if _MULTI_PART.search(text):
        return False
    if _COMPARATIVE.search(text):
        return False
    if _ARITHMETIC.search(text):
        return False

    # Multiple sentences that are each a question or instruction.
    sentences = [s for s in re.split(r"[.?!]+\s+", text) if s.strip()]
    if len(sentences) > 1:
        return False

    if _NEEDS_WORK.search(text):
        # "give"/"show"/"list"/"tell" are retrieval verbs that also
        # appear in _QUESTION_OPENER; only treat the request as work if
        # the work verb is not merely the opener. "Give me the SOP" is a
        # lookup; "Generate a report" is not.
        opener = _QUESTION_OPENER.match(text)
        opener_word = opener.group(1).lower() if opener else ""
        work = {m.group(0).lower() for m in _NEEDS_WORK.finditer(text)}
        if work - {opener_word}:
            return False

    return bool(_QUESTION_OPENER.match(text))


def simple_plan(request: str):
    """The one-step plan a simple lookup needs.

    Built directly rather than asked for, because the answer to "what
    should I do for this question" is already known: retrieve, then
    answer. Spending an LLM call to be told that is the cost this
    module exists to remove.
    """
    from backend.orchestrator.state import PlanStep

    return [
        PlanStep(
            step_id="retrieve",
            description=f"Retrieve the passages that answer: {request.strip()[:120]}",
            assigned_agent="retrieval",
            status="pending",
            depends_on=[],
        )
    ]
