"""The `verify` node — AGENTS_SPEC.md §3/§5, TOOLS.md row 23 (🟡),
Aryan.md Day 8.

Checks whether the output actually satisfies the request before it
reaches a human. The prompt is §5 verbatim.

THE FAILURE PATH IS THE DESIGN. §5 is explicit: on `satisfied: false`,
re-plan with the `missing` list appended — to a MAXIMUM OF 2 CYCLES.
After that, halt and surface it to the human with an explicit
"verification could not confirm this output is complete" flag, "rather
than looping indefinitely or silently shipping an unverified result".

Both halves of that matter and they fail in opposite directions:

  * Looping indefinitely burns an afternoon of local inference on a task
    the model cannot complete, with the user watching a spinner.
  * Silently shipping is worse. An output that failed verification and
    is presented identically to one that passed makes the verification
    step actively harmful — it creates confidence it did not earn.

So the cap produces a THIRD state, not a pass or a fail:
`VerificationOutcome.UNCONFIRMED`, which the approval gate must surface
to the human as such.

WHY A SMALL MODEL VERIFIES A LARGE MODEL'S WORK. phi-3.5-mini (models.yaml's
fast-router tier) checks qwen2.5:14b's output. That is not a weaker model
marking a stronger one's homework: the task is much easier than the one
being checked — "does this output address this request, and what is
missing" is a comparison, not a generation. It is also fast enough to run
on every output, and a verifier nobody can afford to run is not a
verifier.
"""

import json
from enum import Enum

from backend.models.ollama_client import generate as ollama_generate
from backend.models.registry import resolve_model_name
from backend.orchestrator.state import AgentState, VerificationResult
from backend.utils.llm_output import strip_code_fences

MAX_REPLAN_CYCLES = 2

# AGENTS_SPEC.md §5, verbatim. Concatenated rather than .format()-ed:
# the prompt contains literal { } in its JSON-shape description.
_VERIFICATION_PROMPT_TEMPLATE = (
    "You are checking whether an AI assistant's output actually satisfies the "
    'original request. Answer with a JSON object: {"satisfied": true/false, '
    '"reason": "one sentence explanation", "missing": ["list of anything missing, '
    'empty if satisfied is true"]}.\n\n'
    "ORIGINAL REQUEST:\n"
    "{original_request}\n\n"
    "PRODUCED OUTPUT:\n"
    "{draft_output}\n"
)


class VerificationOutcome(str, Enum):
    PASSED = "passed"
    REPLAN = "replan"
    # Failed verification twice. NOT a pass, and must never be presented
    # as one — this is the state §5 requires be surfaced explicitly.
    UNCONFIRMED = "unconfirmed"


def build_verification_prompt(original_request: str, draft_output: str) -> str:
    """§5's template with the two fields substituted.

    Done by replace() rather than .format() because the template's own
    JSON example contains braces that .format() would read as fields —
    the same bug entity_extraction.py documents. Kept as one function so
    the substitution is testable against the spec text.
    """
    return _VERIFICATION_PROMPT_TEMPLATE.replace(
        "{original_request}", original_request
    ).replace("{draft_output}", draft_output)


def _call_verifier_model(prompt: str, model_name: str) -> str:
    
    # Routed through ollama_client so the GPU placement option
    # (num_gpu) applies here too. It previously did not: each of
    # the four call sites built its own request body, so an option
    # added in one place silently missed the others.
    return ollama_generate(
        model_name,
        prompt,
        timeout=180,
    )


def parse_verification(raw: str) -> VerificationResult:
    """Read the verifier's JSON, failing CLOSED.

    Any output that cannot be parsed as a clear verdict is treated as NOT
    verified. The alternative — defaulting to satisfied when the verifier
    is unintelligible — means a malformed response silently becomes a
    pass, which is the one direction this node must never fail in.
    """
    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return VerificationResult(
            passed=False,
            reason="The verifier did not return a readable verdict, so this output is unverified.",
        )
    if not isinstance(parsed, dict) or "satisfied" not in parsed:
        return VerificationResult(
            passed=False,
            reason="The verifier's response did not contain a verdict, so this output is unverified.",
        )

    missing = parsed.get("missing") or []
    if not isinstance(missing, list):
        missing = [str(missing)]

    return VerificationResult(
        passed=bool(parsed.get("satisfied")),
        reason=str(parsed.get("reason", "")).strip(),
        checked_claims=[str(m) for m in missing],
    )


def verify_output(
    state: AgentState, model_id: str = "fast-router", verifier_fn=None
) -> tuple[AgentState, VerificationOutcome]:
    """The `verify` node: check the draft, and decide what happens next.

    Args:
        state: shared agent state; `draft_output` must be populated.
        model_id: registry id, never a raw model name (hard constraint #2).
        verifier_fn: injection point for tests, (prompt, model_name) -> raw text.

    Returns the state and the outcome. The outcome is returned rather
    than inferred from `state.verification_result`, because PASSED and
    UNCONFIRMED are both terminal while REPLAN is not, and a caller
    reading only `passed` would treat unconfirmed as a plain failure and
    loop on it.
    """
    if not state.draft_output:
        # Nothing to verify is not a pass. A step that produced no output
        # reaching the gate as "verified" is precisely the silent-ship
        # failure §5 names.
        state.verification_result = VerificationResult(
            passed=False, reason="There is no output to verify."
        )
        return state, VerificationOutcome.UNCONFIRMED

    caller = verifier_fn or _call_verifier_model
    model_name = resolve_model_name(model_id)
    raw = caller(
        build_verification_prompt(state.original_request, state.draft_output), model_name
    )
    result = parse_verification(raw)
    state.verification_result = result

    if result.passed:
        return state, VerificationOutcome.PASSED

    if state.replan_count >= MAX_REPLAN_CYCLES:
        return state, VerificationOutcome.UNCONFIRMED

    state.replan_count += 1
    return state, VerificationOutcome.REPLAN


def replan_context(state: AgentState) -> str:
    """The request plus what verification said was missing, for the
    re-plan cycle §5 specifies.

    The missing list is appended to the ORIGINAL request rather than
    replacing it: a re-plan that sees only the gaps plans to fill the
    gaps, and loses the task they were gaps in.
    """
    missing = state.verification_result.checked_claims if state.verification_result else []
    if not missing:
        return state.original_request
    return (
        f"{state.original_request}\n\n"
        "A previous attempt was checked and found incomplete. It was missing:\n"
        + "\n".join(f"- {m}" for m in missing)
    )


def unconfirmed_warning(state: AgentState) -> str:
    """The flag §5 requires be shown to the human on an unconfirmed output.

    Worded to be usable verbatim in the approval UI: it says what was
    checked, what was missing, and that the output is not being vouched
    for — rather than a status code the interface would have to
    interpret and might interpret as a failure to hide.
    """
    result = state.verification_result
    missing = result.checked_claims if result else []
    lines = [
        "Verification could not confirm this output is complete after "
        f"{MAX_REPLAN_CYCLES} attempts.",
    ]
    if result and result.reason:
        lines.append(f"The checker said: {result.reason}")
    if missing:
        lines.append("Reported as missing: " + "; ".join(missing))
    lines.append("Review it against the original request before acting on it.")
    return " ".join(lines)
