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
from backend.models.ollama_client import short_prompt_options
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


def build_verification_prompt(
    original_request: str, draft_output: str, sources: list[dict] | None = None
) -> str:
    """§5's template with its fields substituted, plus the SOURCES.

    THE VERIFIER COULD NOT SEE WHAT IT WAS VERIFYING.

    §5's template supplies only the request and the draft. So the
    verifier was asked whether an answer is complete and supported,
    while being shown nothing to support it against. Its verdicts were
    exactly what that permits -- judgements of style, not of grounding.
    On a correct, correctly-cited answer it returned:

        "The produced output provides the value of the average Melt Flow
         Index (MFI) but lacks a clear statement about whether this
         figure pertains specifically to Homopolymer H030SG and does not
         include any supporting evidence or sources."

    The answer was "The average MFI for Homopolymer H030SG is 3.4
    g/10min [2]." It named the grade, gave the value, and cited. The
    verifier called it unsupported because "[2]" is meaningless without
    the source list, and it had never been given one.

    That made the self-check fail on every real answer, which is the
    same outcome as the hardcoded satisfied:true it replaced -- a
    verdict uncorrelated with the answer's quality, just inverted. A
    banner that is always on carries no information.

    Passing the retrieved chunks makes the question answerable: the
    verifier can now check that a cited number actually appears in the
    source it is attributed to, which is what §5 is for.

    `sources` is optional so every existing caller and test keeps
    working; without it the behaviour is exactly as before.

    Done by replace() rather than .format() because the template's own
    JSON example contains braces that .format() would read as fields —
    the same bug entity_extraction.py documents.
    """
    prompt = _VERIFICATION_PROMPT_TEMPLATE.replace(
        "{original_request}", original_request
    ).replace("{draft_output}", draft_output)

    if not sources:
        return prompt

    lines = ["", "", "SOURCES THE ANSWER WAS DRAWN FROM:"]
    for i, chunk in enumerate(sources, 1):
        text = (chunk.get("text") or "").strip().replace("\n", " ")
        doc = chunk.get("source_document", "?")
        # Truncated per source: the verifier needs enough to confirm a
        # cited value appears, not the whole chunk. Sending everything
        # would push this prompt past the context window that keeps this
        # model resident alongside the generation model.
        lines.append(f"[{i}] ({doc}) {text[:700]}")
    lines += [
        "",
        "A claim is supported if the cited source contains it. A bracketed "
        "number refers to the source with that number above; an answer that "
        "cites correctly is NOT missing its sources.",
    ]
    return prompt + "\n".join(lines)


def _call_verifier_model(prompt: str, model_name: str) -> str:
    
    # Routed through ollama_client so the GPU placement option
    # (num_gpu) applies here too. It previously did not: each of
    # the four call sites built its own request body, so an option
    # added in one place silently missed the others.
    return ollama_generate(
        model_name,
        prompt,
        options=short_prompt_options(),
        timeout=180,
    )


def _first_json_object(text: str) -> dict | None:
    """The first complete JSON object in `text`, or None.

    WHY A WHOLE-STRING json.loads WAS NOT ENOUGH.

    This node reported "the verifier did not return a readable verdict"
    on EVERY answer, which made the self-check look permanently broken
    and trained the reader to ignore its warning banner. The verifier
    was in fact working perfectly. phi3.5 returns:

        ```json
        {
          "satisfied": true,
          "reason": "...",
          "missing": []
        }
        ```

        Instruction much more difficult by adding **at least {5} more
        constraints**:

    Valid JSON, correct verdict -- followed by a fragment of training
    boilerplate the model appended unprompted. strip_code_fences removed
    the fence, json.loads then choked on the trailing prose, and a
    correct verdict became "unreadable".

    Scanning for the first balanced object is the right repair rather
    than a lenient one: it accepts a verdict the model genuinely gave
    and still returns None when there is no object at all. The
    fail-closed property is untouched -- None means NOT verified, as
    before, and a `satisfied` key that is missing is still rejected
    downstream. What changed is only that surrounding chatter no longer
    destroys a verdict that was actually produced.

    Deliberately NOT a regex. Brace counting respects nesting, so a
    "reason" string containing braces cannot truncate the object -- the
    same brace-collision hazard that prompted every prompt-builder in
    this codebase to avoid str.format().
    """
    if not text:
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(candidate, dict):
                        return candidate
                    break
        start = text.find("{", start + 1)
    return None


def parse_verification(raw: str) -> VerificationResult:
    """Read the verifier's JSON, failing CLOSED.

    Any output that cannot be parsed as a clear verdict is treated as NOT
    verified. The alternative — defaulting to satisfied when the verifier
    is unintelligible — means a malformed response silently becomes a
    pass, which is the one direction this node must never fail in.
    """
    parsed = _first_json_object(strip_code_fences(raw))
    if parsed is None:
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
        build_verification_prompt(
            state.original_request,
            state.draft_output,
            # The chunks the answer was actually generated from. Without
            # these the verifier can only judge style -- see the
            # docstring above.
            sources=state.retrieved_context,
        ),
        model_name,
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
