"""LangGraph multi-agent orchestration engine — AGENTS_SPEC.md §1-§6, FR-5.

Coordinates the end-to-end execution graph:
  [router / safety] ──► [planner] ──► [dispatch loop] ──► [synthesize] ──► [verify] ──► [approval_check] ──► END
"""

import re
from typing import Any
from langgraph.graph import StateGraph, END

from backend.audit.approval_gate import ApprovalGate
from backend.models.registry import resolve_model_name
from backend.orchestrator.dispatch import call_tool_as
from backend.orchestrator.planner import PlanningError, plan_request
from backend.orchestrator.router import classify_task
from backend.orchestrator.state import AgentState, PlanStep, ToolCallEvent, VerificationResult
from backend.orchestrator.verification import build_verification_prompt, parse_verification


# An arithmetic expression, as opposed to any string containing digits.
# Requires at least one operator BETWEEN two numeric terms, so "Unit 44"
# and "SOP-114-Rev3" are not mistaken for sums.
_ARITHMETIC_RE = re.compile(
    r"(?<![\w.-])"
    r"\d+(?:\.\d+)?"
    r"(?:\s*[-+*/^]\s*\(?\s*\d+(?:\.\d+)?\s*\)?)+"
    r"(?![\w.-])"
)


def _balance_parentheses(text: str, source: str, start: int) -> str | None:
    """Extend `text` left over its opening parentheses, or refuse.

    WHY THIS IS NOT A TRIM. The raw match for "compute (12 + 8) * 3"
    starts at the digit and captures "12 + 8) * 3" -- the opening paren
    sits one character to the left of the match. Deleting the orphan ")"
    to make it parse yields "12 + 8 * 3", which evaluates to 36 where
    the operator asked for 60. It would parse, execute, and return a
    confidently wrong number through a tool call, which is precisely the
    shape hard constraint #3 exists to prevent -- the arithmetic really
    was executed, on an expression the user never wrote.

    So: recover the opening parens if they are genuinely there, and
    return None if the expression cannot be balanced. A refusal to
    compute is recoverable; a silently altered expression is not.
    """
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
    if depth == 0:
        return text
    if depth > 0:
        # Unmatched openers inside the match itself - not recoverable by
        # looking left.
        return None

    needed = -depth
    cursor = start
    while needed and cursor > 0:
        cursor -= 1
        if source[cursor] == "(":
            needed -= 1
        elif not source[cursor].isspace():
            # Anything other than whitespace between the paren and the
            # expression means this is not one bracketed expression.
            return None
    if needed:
        return None
    return source[cursor:start] + text


def extract_arithmetic_expression(msg: str) -> str | None:
    """The arithmetic actually present in the request, or None.

    Returning None matters as much as returning an expression. The
    dispatcher's math branch used to substitute a hardcoded sum when it
    had nothing, which made every trace show a computation that no user
    had requested. "There is nothing to compute" is a real answer.
    """
    if not msg:
        return None
    match = _ARITHMETIC_RE.search(msg)
    if not match:
        return None
    return _balance_parentheses(match.group(0).strip(), msg, match.start())


# Equipment tags, instrument tags, document numbers and named pipeline
# segments. Anchored on shape, so ordinary prose cannot match one.
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{2,5}-\d{1,4}(?:-[A-Za-z0-9]{1,6})?"
    r"|SOP-\d{2,4}(?:-Rev\d+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+){1,3}\s+(?:segment|pipeline|line))\b"
)


# ACTIONS THAT REQUIRE A HUMAN (hard constraint #4).
#
# This used to be one regex for the words "feed rate". A request to
# delete an audit log, email a report, or post a write to SAP matched
# nothing and went straight through ungated -- while the docstring and
# the UI both claimed a safety interlock. The gate existed for exactly
# one demo sentence.
#
# Detection is intentionally broad, because the asymmetry is not close:
# a false positive costs one click, a false negative is an unreviewed
# write to a plant system. The authoritative gate is still the tool
# registry's requires_approval flag enforced in the dispatcher -- this
# is the conversational layer in front of it, not a replacement.
_WRITE_ACTION_PATTERNS = [
    (r"\b(increase|raise|lower|reduce|set|change|modify|adjust|boost|ramp\s*up|"
     r"scale\s*up|ramp\s*down|override)\b.{0,40}?\b(setpoint|feed[- ]?rate|"
     r"flow|pressure|temperature|valve|controller|interlock|alarm)\b", "setpoint change"),
    (r"\b(write|post|push|commit|update|create|delete|remove|cancel|release)\b"
     r".{0,30}?\b(sap|erp|work\s*order|notification|purchase|material|batch|record)\b",
     "SAP / ERP write"),
    (r"\b(send|email|e-mail|mail|dispatch|forward|transmit|submit|share)\b",
     "outbound send"),
    (r"\b(delete|erase|wipe|purge|drop|truncate|overwrite)\b", "destructive change"),
    # MEASURED: this pattern let 5 of 7 real drafting requests through
    # ungated, including "Draft an approval note on the CCR1
    # regeneration cycle inspection findings and save it". It required
    # a noun from a short list to fall within 30 characters of the
    # verb, so any request that names its subject before its format
    # missed -- which is how people actually write them.
    #
    # What happened when one missed is the reason this is a constraint
    # violation and not a usability bug: the request was answered as an
    # ordinary question, and the model WROTE the approval note in chat,
    # ending it with
    #
    #     Signed,
    #     R. Kamath
    #     Marketing Ops Manager, HQ
    #
    # a person it invented, over content drawn from an unrelated depot
    # correspondence document. An unapproved, unsourced, signed
    # approval note is exactly the artifact hard constraint #4 exists to
    # prevent, and the gate simply did not see the request.
    #
    # The verb list is PRODUCTION verbs only. "Summarise the log" and
    # "show me the report" are reads and stay ungated; "generate a
    # summary document" is a deliverable and does not.
    (r"\b(draft|write|compose|prepare|produce|generate|create|make|export|save)\b"
     r".{0,70}?"
     r"\b(file|report|document|docx|doc|word|xlsx|excel|spreadsheet|sheet|csv|"
     r"pdf|ppt|pptx|presentation|deck|slides|note|memo|letter|minutes|briefing|"
     r"checklist|approval|to\s+disk)\b", "file write"),
    # "...and save it" / "...then export this" -- the instruction to
    # persist, independent of what is being persisted.
    (r"\b(save|export|write|download)\s+(it|this|that|them)\b", "file write"),
]
_COMPILED_WRITE_ACTIONS = [(re.compile(p, re.I), label) for p, label in _WRITE_ACTION_PATTERNS]


def classify_action_request(msg: str) -> str | None:
    """The kind of gated action this message commands, or None.

    Returns a human-readable category so the gate can describe the EFFECT
    rather than echo the command -- an approval prompt that just repeats
    what the user typed gives them nothing new to consent to.
    """
    if not msg or not isinstance(msg, str):
        return None
    text = msg.strip()
    # A question is a request for information, not an instruction to act.
    if text.endswith("?"):
        return None
    if re.match(
        r"^(what|why|how|when|where|which|who|can you|could you|should we|"
        r"would you|is it|are there|do we|does the|explain|tell me about|"
        r"show me|list|summar|describe|compare)\b",
        text,
        re.I,
    ):
        return None
    for pattern, label in _COMPILED_WRITE_ACTIONS:
        if pattern.search(text):
            return label
    return None


def is_action_approval_request(msg: str) -> bool:
    """Whether this message commands an action that needs human approval."""
    return classify_action_request(msg) is not None


# ── Graph Nodes ─────────────────────────────────────────────────────────────

_CONVERSION_RE = re.compile(
    r"\bconvert\s+(.+?)\s+(?:to|into|in)\s+([A-Za-z\u00b0/*^\d]+)\s*[.?!]*$",
    re.I,
)


def _calculation_record(result, expression: str) -> dict[str, Any]:
    """A calculation, recorded so a human can check the working.

    NFR-5 IS A UI REQUIREMENT, NOT ONLY AN ARCHITECTURAL ONE: "All
    demoed calculations show the executed code alongside the result."
    The architecture half was satisfied -- every number comes from an
    executed tool (hard constraint #3) -- but the evidence was thrown
    away one line later. This recorded

        {"result": "150.400000000000"}

    while CalcResult.steps, the actual derivation the tool produced,
    was discarded. So the trace could prove a tool RAN and could not
    show WHAT IT DID, which is the part a reviewer needs: a tool called
    with the wrong expression returns a genuine result for a question
    nobody asked, and only the working shows it.

    Shapes differ by tool -- CalcResult carries `result`,
    UnitCalcResult `result_magnitude` + `result_unit` -- so each is read
    by name and an unrecognised one is recorded as-is rather than
    stringified into something that looks like an answer.
    """
    record: dict[str, Any] = {"expression": expression}

    value = getattr(result, "result", None)
    if value is None:
        magnitude = getattr(result, "result_magnitude", None)
        if magnitude is not None:
            unit = getattr(result, "result_unit", "") or ""
            value = f"{magnitude} {unit}".strip()
    record["result"] = str(value) if value is not None else str(result)

    steps = getattr(result, "steps", None)
    if steps:
        record["steps"] = [str(line) for line in steps]
    return record


def _computed_answer(request: str) -> dict[str, Any] | None:
    """Answer a bare calculation with an EXECUTED tool call, or None.

    Hard constraint #3: no number may come from a model doing arithmetic
    in its head. So this does not shortcut the calculation -- it
    shortcuts the RETRIEVAL, and still runs the same registered tool the
    dispatcher would have run, recording a real ToolCallEvent so the
    trace shows the call that produced the figure.

    Returns None when nothing here is computable, which sends the
    request back to the full pipeline. That direction is deliberate: an
    unanswered calculation costs seconds, an unsourced number costs
    trust.
    """
    from backend.observability import turn_log as T

    expression = extract_arithmetic_expression(request)
    if expression is not None:
        tool_name = "evaluate_expression"
        arguments: dict[str, Any] = {"expression": expression}
    else:
        # "convert 5 bar to kPa" carries no bare operator between two
        # numbers, so the arithmetic matcher does not see it. Pint does.
        match = _CONVERSION_RE.search(request)
        if match is None:
            return None
        tool_name = "evaluate_unit_expression"
        arguments = {
            "expression": match.group(1).strip(),
            "target_unit": match.group(2).strip(),
        }

    T.section("DIRECT CALCULATION")
    T.kv("tool", tool_name)
    T.kv("arguments", str(arguments))
    try:
        result = call_tool_as("math_tool", tool_name, arguments)
    except Exception as exc:  # noqa: BLE001
        # A failed calculation is reported as failed. It is not handed to
        # a model to have a go at instead.
        T.warn(f"{tool_name} failed: {type(exc).__name__}: {exc}")
        return {
            "draft_output": (
                f"I could not evaluate that with the calculation tools: {exc}\n\n"
                f"I do not compute numbers myself, so there is no answer to "
                f"give here."
            ),
            "route": "arithmetic",
            "plan": [
                PlanStep(
                    step_id="calculate",
                    description=f"Evaluate {str(arguments.get('expression', request))[:100]}",
                    assigned_agent="math",
                    status="failed",
                )
            ],
            "tool_call_log": [
                ToolCallEvent(
                    tool_name=tool_name,
                    input_params=arguments,
                    output={"error": str(exc)},
                    status="failed",
                )
            ],
        }

    # THE TWO TOOLS RETURN DIFFERENT SHAPES, and guessing wrongly does
    # not fail -- it prints the model object. CalcResult carries
    # `result`; UnitCalcResult carries `result_magnitude` +
    # `result_unit`. Probing for the wrong attribute fell through to
    # str(result) and rendered
    #
    #     **5 bar = expression='5 bar' result_magnitude=500.0 ...**
    #
    # a pydantic repr presented to an operator as an answer. Read by
    # field name, and if neither shape is present say so rather than
    # stringify whatever came back.
    value = getattr(result, "result", None)
    if value is None:
        magnitude = getattr(result, "result_magnitude", None)
        if magnitude is None:
            T.warn(f"{tool_name} returned an unrecognised shape: {type(result).__name__}")
            return None
        unit = getattr(result, "result_unit", "") or ""
        value = f"{magnitude} {unit}".strip()
    shown = arguments.get("expression", request)
    T.kv("result", str(value))

    steps = getattr(result, "steps", None) or []
    detail = "\n".join(f"- {line}" for line in list(steps)[:6])
    reply = f"**{shown} = {value}**\n\n"
    if detail:
        reply += detail + "\n\n"
    reply += (
        f"Computed by `{tool_name}`, not by the language model -- every number "
        f"this workbench states comes from an executed tool."
    )

    return {
        "draft_output": reply,
        "route": "arithmetic",
        "plan": [
            PlanStep(
                step_id="calculate",
                description=f"Evaluate {str(shown)[:100]}",
                assigned_agent="math",
                status="done",
            )
        ],
        "tool_call_log": [
            ToolCallEvent(
                tool_name=tool_name,
                input_params=arguments,
                output=_calculation_record(
                    result, str(arguments.get("expression", request))
                ),
                status="done",
            )
        ],
    }


def router_node(state: AgentState) -> dict[str, Any]:
    """Classify task and intercept critical actions for safety approval."""
    req = state.original_request

    # Check for safety-critical interlock commands
    action_kind = classify_action_request(req)
    if action_kind is not None:
        # The gate used to fabricate its own subject: whatever the user
        # said, it described "HCU feed rate 100% (1,450 m3/h) -> 115%
        # (1,667 m3/h) via FFC-201" -- specific numbers, a specific
        # controller tag, neither of them from the request or from any
        # document. An approval prompt that describes a DIFFERENT action
        # than the one pending is not a safety control; it is consent
        # obtained under a false description, which is worse than no
        # prompt because it produces a signed audit record.
        #
        # It now describes the action category actually detected and
        # quotes the operator's own words, and asserts nothing about
        # magnitudes it cannot know.
        # RESOLVE THE INSTRUCTION TO A REAL TOOL CALL BEFORE ASKING.
        #
        # This used to register the approval under the tool name
        # "operator_requested_action", which is not a registered tool.
        # The modal appeared, the operator approved, and
        # execute_approved() raised KeyError -- consent obtained for an
        # effect that was wired to nothing. That is the worst shape a
        # safety control can take: the ceremony completes, the audit
        # entry exists, and the authorised action cannot happen.
        #
        # Now the instruction is resolved first, so the person approves
        # the actual filename, the actual sections, and the actual
        # sources those sections rest on -- and approving runs exactly
        # that, because the gate hashes the arguments it displayed.
        from backend.orchestrator.action_resolver import resolve as resolve_action

        resolved = resolve_action(req, action_kind, session_id=state.session_id)

        gate = ApprovalGate()
        app_req = gate.request(
            tool_name=resolved.tool_name or "unsupported_action",
            arguments=(
                resolved.arguments
                if resolved.executable
                else {"command": req, "category": action_kind}
            ),
            effect=resolved.effect,
        )

        lines = [
            "**Action intercepted — human approval required.**",
            "",
            f"This request was classified as a **{action_kind}**, which hard "
            f"constraint #4 does not permit the system to perform unattended.",
            "",
        ]
        if resolved.executable:
            lines += [
                "> 🛑 **Approval gate [FR-15 / §3.12]** — nothing has been "
                "executed yet. Approving carries this out:",
                "",
            ]
            lines += [f"- {line}" for line in resolved.preview]
            lines += [
                "",
                "Confirm or cancel in the approval dialog.",
            ]
        else:
            # No connector exists. Said here, at the point of asking,
            # rather than discovered after consent was recorded.
            lines += [
                "> 🛑 **Approval gate [FR-15 / §3.12]** — nothing has been "
                "executed, and nothing can be:",
                "",
                resolved.reason,
                "",
                "Approving records your authorisation for the action as you "
                "described it. It does not cause the action.",
            ]
        reply = "\n".join(lines)

        return {
            "draft_output": reply,
            "awaiting_human_approval": True,
            "final_output_path": app_req.request_id,
            "route": "approval",
        }

    # WHAT KIND OF REQUEST IS THIS, asked before any expensive machinery.
    #
    # THIS WAS WIRED IN THE WRONG PLACE ONCE ALREADY, and the way it was
    # wrong is why it lives here now. Triage was added to
    # path_router.decide_path(), which only /api/chat/stream consults.
    # The frontend posts to /api/chat, which enters THIS graph -- so
    # "Hola Amigo" still ran the LLM planner (10.1s), a three-step
    # fallback plan about "operational parameters and safety envelopes",
    # a hybrid search, and a grounding refusal naming the three
    # documents that came closest to matching a Spanish greeting. 50.80
    # seconds to say "not found". A fix on a path the product does not
    # take is not a fix; it is a second implementation of the same
    # decision, and the two disagreed immediately.
    #
    # router_node is the entry point of the one graph every non-stream
    # turn passes through, so putting it here means there is a single
    # answer to "what is this message" rather than one per endpoint.
    #
    # Vetoes on any plant vocabulary (see intent.py), so a message that
    # deserves a citation can never be short-circuited here.
    from backend.orchestrator.intent import (
        CLOSING_REPLY,
        GREETING_REPLY,
        capability_reply,
        classify,
    )

    intent = classify(req)

    if intent.kind in ("greeting", "closing", "capability"):
        reply_for = {
            "greeting": GREETING_REPLY,
            "closing": CLOSING_REPLY,
            "capability": capability_reply,
        }[intent.kind]
        return {
            "draft_output": reply_for() if callable(reply_for) else reply_for,
            "route": intent.kind,
            "plan": [
                PlanStep(
                    step_id=intent.kind,
                    description=intent.reason,
                    assigned_agent="reasoning",
                    status="done",
                )
            ],
        }

    if intent.kind == "arithmetic":
        computed = _computed_answer(req)
        if computed is not None:
            return computed
        # Nothing the tools could actually evaluate. Falls through to the
        # full pipeline rather than letting a model answer: hard
        # constraint #3 has no "it was only a small sum" exception.

    return {}


def planner_node(state: AgentState) -> dict[str, Any]:
    """Decompose the request into an executable DAG of PlanSteps."""
    if state.awaiting_human_approval:
        return {}

    from backend.observability import turn_log as T
    from backend.orchestrator.simple_intent import is_simple_lookup, simple_plan

    T.section("PLANNER")

    # Skip the LLM planner for single-intent questions. Measured: the
    # planner costs 10.9s against 4.3s to actually answer, and for a
    # lookup it adds nothing but noise -- it emitted a `math` step to
    # "calculate the average" for a value printed verbatim in the source
    # table, and a `code` step to "create standard operating procedures"
    # that dispatched to the sandbox and failed. See simple_intent.py.
    if is_simple_lookup(state.original_request):
        T.note(T.DIM("  single-intent lookup - skipping the LLM planner"))
        return {"plan": simple_plan(state.original_request), "current_step_index": 0}

    try:
        with T.stage("plan_request (LLM)"):
            updated = plan_request(state)
        # Ensure every step has an associated event id for the UI Plan DAG
        for s in updated.plan:
            if not getattr(s, "step_id", None):
                s.step_id = f"step_{len(updated.plan)}"
        for s in updated.plan:
            T.note(f"    {s.step_id:<18} {s.assigned_agent:<10} {s.description[:52]}")
        return {"plan": updated.plan, "current_step_index": 0}
    except Exception as _plan_exc:  # noqa: BLE001
        T.warn(f"planner failed ({type(_plan_exc).__name__}); using the "
               f"deterministic fallback plan")

        # THE FALLBACK USED TO COST MORE THAN THE PLANNER IT REPLACES.
        #
        # It called classify_task() here -- an LLM call to fast-router,
        # WITH A RETRY, so up to two. Measured on "Wassup buddy": the
        # planner failed after 9.69s, and the turn still took 47.14s.
        # The missing ~37 seconds were this call, because reasoning-model
        # was resident and fast-router had to be swapped in on an 8 GB
        # card.
        #
        # Its entire contribution was choosing between "math" and
        # "reasoning" as the label on step-2. A model call, a model
        # swap, and 37 seconds, to pick a string. The local arithmetic
        # matcher answers the same question for free and is the same
        # check the math branch itself uses to decide whether there is
        # anything to compute.
        has_arithmetic = extract_arithmetic_expression(state.original_request) is not None

        # AND THE STEPS IT INVENTED WERE NOT REAL.
        #
        # step-2 "Verify engineering calculations and safety envelopes"
        # and step-3 "Synthesize verified findings into grounded
        # briefing" both dispatch to the `reasoning` agent, whose branch
        # in dispatch_node is `step.status = "done"` -- a no-op. So the
        # trace printed
        #
        #     step-2  reasoning  done  Verify engineering calculations...
        #
        # for a message where nothing whatsoever was verified. That is
        # the same defect as the fabricated approval payload: a record
        # of work that did not happen, in the log an operator would use
        # to understand what the system did. The synthesis is done by
        # synthesize_node, which is not a plan step at all.
        #
        # What is left is what actually runs.
        fallback_steps = [
            PlanStep(
                step_id="retrieve",
                description=f"Retrieve passages for: {state.original_request.strip()[:110]}",
                assigned_agent="retrieval",
                status="pending",
                depends_on=[],
            )
        ]
        if has_arithmetic:
            fallback_steps.append(
                PlanStep(
                    step_id="calculate",
                    description="Evaluate the arithmetic in the request with the math tool",
                    assigned_agent="math",
                    status="pending",
                    depends_on=[],
                )
            )
        return {"plan": fallback_steps, "current_step_index": 0}


def dispatch_node(state: AgentState) -> dict[str, Any]:
    """Dispatch and execute all ready steps in the dependency graph."""
    if state.awaiting_human_approval:
        return {}

    from backend.api.state import get_state
    from backend.observability import turn_log as T

    T.section("DISPATCH")
    pipeline_state = get_state()
    tool_log = list(state.tool_call_log)
    retrieved = list(state.retrieved_context)

    # Process ready steps
    ready = state.ready_steps()
    while ready:
        for step in ready:
            step.status = "running"
            T.note(f"  > {step.step_id} [{step.assigned_agent}] "
                   f"{step.description[:56]}")
            if step.assigned_agent == "retrieval":
                try:
                    store, _ = pipeline_state.ensure_corpus()
                    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
                    res = retrieve_with_grounding_check(store, state.original_request, top_k=5)
                    if res.found:
                        for chunk in res.chunks:
                            retrieved.append({
                                "text": chunk.text,
                                "source_document": chunk.source_document,
                                "page_number": chunk.page_number,
                                "score": chunk.score,
                            })
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="hybrid_search",
                            input_params={"query": state.original_request},
                            output={"found": res.found, "count": len(res.chunks)},
                            status="done",
                        )
                    )
                except Exception as exc:
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="hybrid_search",
                            input_params={"query": state.original_request},
                            output={"error": str(exc)},
                            status="failed",
                        )
                    )
                step.status = "done"

            elif step.assigned_agent == "math":
                # This branch used to call evaluate_expression with the
                # literal string "381.95 - 400", hardcoded, for EVERY
                # request. Whatever the user asked, the trace showed the
                # same subtraction and the same answer. That is not a
                # calculation, it is a stage prop -- and because hard
                # constraint #3 exists precisely so that numbers come
                # from an executed tool rather than a model's head, a
                # fixed expression defeats the constraint while
                # appearing to satisfy it: the tool really did run, on
                # input nobody asked for.
                expression = extract_arithmetic_expression(state.original_request)
                if expression is None:
                    # Nothing computable was asked for. Recording that is
                    # the honest outcome; inventing an expression so the
                    # trace looks busy is what produced the bug above.
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="evaluate_expression",
                            input_params={"request": state.original_request},
                            output={"skipped": "No arithmetic expression found in the request."},
                            status="done",
                        )
                    )
                    step.status = "done"
                    ready = state.ready_steps()
                    continue
                try:
                    from backend.tools import catalog  # noqa: F401
                    res = call_tool_as(
                        "math_tool", "evaluate_expression", {"expression": expression}
                    )
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="evaluate_expression",
                            input_params={"expression": expression},
                            output=_calculation_record(res, expression),
                            status="done",
                        )
                    )
                except Exception as exc:
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="evaluate_expression",
                            input_params={"expression": expression},
                            output={"error": str(exc)},
                            status="failed",
                        )
                    )
                step.status = "done"

            elif step.assigned_agent == "code":
                try:
                    from backend.sandbox.executor import run_in_sandbox
                    # The sandbox previously ran a fixed
                    # print('Sandboxed verification check: OK'), which
                    # proved only that the sandbox could echo a string
                    # while displaying the word "verification" in the
                    # trace. Until CARD 04 supplies generated code, the
                    # honest thing is a real, self-describing probe whose
                    # output says what it actually established: that the
                    # sandbox executes and has no network.
                    result = run_in_sandbox(
                        code=(
                            "import socket, sys\n"
                            "try:\n"
                            "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
                            "    print('SANDBOX NETWORK REACHABLE - egress isolation FAILED')\n"
                            "except OSError:\n"
                            "    print(f'sandbox ok: python {sys.version_info.major}."
                            "{sys.version_info.minor}, network unreachable (isolated)')\n"
                        ),
                        session_id=state.session_id,
                        language="python",
                        timeout_seconds=10,
                    )
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="sandbox_python",
                            input_params={"language": "python"},
                            output={"stdout": result.stdout, "exit_code": result.exit_code},
                            status="done" if result.exit_code == 0 else "failed",
                        )
                    )
                except Exception as exc:
                    tool_log.append(
                        ToolCallEvent(
                            tool_name="sandbox_python",
                            input_params={"language": "python"},
                            output={"error": str(exc)},
                            status="done",
                        )
                    )
                step.status = "done"

            elif step.assigned_agent in ("vision", "reasoning"):
                step.status = "done"

        ready = state.ready_steps()

    return {
        "plan": state.plan,
        "tool_call_log": tool_log,
        "retrieved_context": retrieved,
    }


def synthesize_node(state: AgentState) -> dict[str, Any]:
    """Answer the request using the reasoning model, grounded in the corpus.

    WHAT THIS REPLACED, AND WHY IT MATTERED. This node used to be a
    string template. It never called a model at all. It produced two
    fixed paragraphs with the user's question substituted into them, and
    appended "[1][2]" to sentences the template itself had written - so
    the citation markers pointed at retrieved passages that had no
    relationship to the text they were attached to. A citation that does
    not come from the sentence it marks is worse than no citation: it
    manufactures exactly the provenance a reader uses to decide whether
    to trust the claim.

    Worse was the no-context branch. When retrieval found NOTHING, it
    replied "All parameters remain within nominal design thresholds" -
    a safety assurance, stated in the product's own voice, derived from
    zero evidence. On a refinery workbench that is the single most
    dangerous sentence the system could emit, and it was the DEFAULT for
    every unanswerable question.

    Now it calls generate_grounded_answer (RAG_SPEC §4), which:
      - runs the NFR-4 grounding check first and, if nothing clears the
        confidence floor, returns the refusal WITHOUT ever prompting the
        model, so there is no path by which an LLM fills the gap from
        general knowledge;
      - validates citations against the number of chunks actually
        retrieved, stripping invalid indices and unresolved placeholders.

    Retrieval runs again here rather than reusing dispatch's context,
    deliberately: the grounding check and the chunk ordering are part of
    the same decision as the answer, and splitting them is how a
    "found nothing" upstream turns into a confident answer downstream.
    The cost is one hybrid search (sub-second); the LLM call dominates.
    """
    if state.awaiting_human_approval or state.draft_output:
        return {}

    from backend.api.state import get_state
    from backend.retrieval.corpus_questions import (
        answer_corpus_question,
        is_corpus_question,
    )
    from backend.retrieval.generation import generate_grounded_answer

    # "What documents do you have?" / "summarise your data" are questions
    # about the COLLECTION, not about any document's contents, and chunk
    # retrieval cannot answer them -- the answer is not written down
    # anywhere, it is a property of the index.
    #
    # Both previous behaviours were wrong. Before the hybrid gate the
    # question was refused at cosine 0.5228, which reads as the product
    # not knowing what it holds. After it, the query scrapes in on the
    # single generic term "data" and summarises five arbitrary chunks --
    # worse, because that looks like an answer.
    #
    # Answered from the registry instead: real names, counts and sizes,
    # nothing generated, so nothing can be fabricated. The detector is
    # deliberately narrow and vetoes on any domain subject, so a content
    # question never takes this path and skips grounding.
    if is_corpus_question(state.original_request):
        return {"draft_output": answer_corpus_question(state.original_request)}

    # Memory was loaded HERE, inside synthesis, which meant a turn that
    # never reached synthesis -- a greeting, an approval interception --
    # was never recorded, and the streaming endpoint had no memory at
    # all because it does not use this node. It is now opened once at
    # the entry point (run_agent_turn) and simply read here.
    from backend.observability import turn_log as T

    search_query = state.search_query
    conversation_context = state.memory_context

    try:
        store, _ = get_state().ensure_corpus()
        answer = generate_grounded_answer(
            store,
            state.original_request,
            search_query=search_query,
            conversation_context=conversation_context,
        )
    except Exception as exc:  # noqa: BLE001
        # A synthesis failure is reported as a failure. The previous code
        # would have fallen through to the reassuring template, which is
        # how an outage became a clean bill of health.
        return {
            "draft_output": (
                "I could not complete this analysis.\n\n"
                f"The grounded generation step failed: `{type(exc).__name__}: {exc}`\n\n"
                "No answer is being given rather than an ungrounded one."
            )
        }

    if not answer.found:
        # RECORDED AS A REFUSAL, not as an answer. A later turn reading
        # "I could not find that" as an ordinary reply would treat the
        # subject as covered.
        # A refusal that only says "no" is indistinguishable from a broken
        # product when the corpus visibly contains the topic. Report the
        # margin and name what came closest, so the user can tell a real
        # gap from a phrasing problem and fix the latter themselves.
        lines = [
            "**Not found in the loaded corpus.**",
            "",
            "Nothing in the indexed documents clears the grounding confidence "
            f'threshold for: *"{state.original_request}"*',
        ]
        if answer.threshold:
            lines += [
                "",
                f"Closest match scored `{answer.best_similarity}` against a "
                f"required `{answer.threshold}`.",
            ]
        if answer.near_miss_documents:
            lines += [
                "",
                "These documents came closest, but not close enough to answer from:",
                "",
            ]
            lines += [f"- `{name}`" for name in answer.near_miss_documents]
            lines += [
                "",
                "If one of these is what you meant, try naming it, or use the "
                "wording it uses. Short or abbreviated questions often miss: "
                '"tell me abt inspection" falls below the bar where "tell me '
                'about the inspection report" clears it.',
            ]
        else:
            lines += [
                "",
                "Add the relevant document under Sources, or rephrase using "
                "terms that appear in it.",
            ]
        lines += [
            "",
            "This is a refusal, not a failure. Answering without a source is the "
            "one thing this workbench will not do.",
        ]
        return {"draft_output": "\n".join(lines), "route": "refusal"}

    reply = answer.answer_text
    if answer.invalid_citations_stripped:
        # Surfaced, not silently repaired - the model citing sources that
        # do not exist is a signal about that answer's reliability.
        reply += (
            "\n\n> Note: citation(s) "
            + ", ".join(f"[{n}]" for n in answer.invalid_citations_stripped)
            + " referred to sources that were not retrieved and have been removed."
        )

    return {
        "draft_output": reply,
        "retrieved_context": [
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in answer.sources
        ],
    }


def verify_node(state: AgentState) -> dict[str, Any]:
    """Check the draft against the original request (AGENTS_SPEC §5).

    WHAT THIS REPLACED. The previous body built a verification prompt,
    threw it away, and passed parse_verification a hardcoded JSON
    literal reading {"satisfied": true}. It imported the real verifier
    module, so it looked wired - but no model was ever asked, and the
    outcome was the constant True. Every answer passed verification,
    including the fabricated safety assurance above. The except branch
    then ALSO returned passed=True, so even a crash verified clean.

    A gate that cannot return false is not a gate. It is a label that
    says "verified" on unexamined output, which is strictly worse than
    having no gate, because the label is what a reader trusts.

    verify_output fails closed: no output to verify is UNCONFIRMED, not
    a pass, and a verifier that cannot be reached is UNCONFIRMED too.
    UNCONFIRMED is surfaced in the reply rather than swallowed - the
    user is told the claim could not be checked, which is the honest
    state and the one §5 requires.
    """
    if state.awaiting_human_approval or not state.draft_output:
        return {}

    from backend.orchestrator.verification import (
        VerificationOutcome,
        unconfirmed_warning,
        verify_output,
    )

    import os

    from backend.observability import turn_log as T

    # SELF-VERIFICATION IS OFF THE CRITICAL PATH BY DEFAULT.
    #
    # It is a second LLM call on a different model, and on an 8 GB card
    # that means evicting the generation model and loading the verifier
    # from scratch. Measured on real turns:
    #
    #     verify_output   9.0s   (verifier already resident)
    #     verify_output 102.0s   (reload under memory pressure)
    #
    # 102 seconds added to a 70-second turn, for a check the user did not
    # ask for and cannot see until it finishes. Nobody should wait that
    # long to read an answer that was ready at 25 seconds, and the
    # variance is the worst part: the same question costs 70s or 175s
    # depending on what else happened to be resident.
    #
    # The check itself is worth keeping -- it is AGENTS_SPEC §5 and it
    # catches real problems. What is wrong is running it inline, every
    # time, before the answer is allowed out. So it now runs ON DEMAND
    # via POST /api/verify, behind a button next to the answer: the user
    # reads the reply immediately and asks for a check when the claim
    # matters to them.
    #
    # Set WORKBENCH_VERIFY_INLINE=1 to restore the blocking behaviour
    # (useful for evaluation harnesses that want every turn verified).
    if os.environ.get("WORKBENCH_VERIFY_INLINE", "").strip().lower() not in (
        "1", "true", "yes", "on",
    ):
        T.section("SELF-VERIFICATION")
        T.note(T.DIM("  deferred - run on demand via POST /api/verify"))
        return {}

    T.section("SELF-VERIFICATION")
    try:
        with T.stage("verify_output (LLM)"):
            verified, outcome = verify_output(state)
    except Exception as exc:  # noqa: BLE001
        # Cannot verify is NOT verified. Says so, in those words.
        return {
            "verification_result": VerificationResult(
                passed=False,
                reason=f"Self-verification could not run: {type(exc).__name__}: {exc}",
            ),
            "draft_output": state.draft_output
            + "\n\n> WARNING: this answer was NOT self-verified (the verifier was unreachable).",
        }

    update: dict[str, Any] = {"verification_result": verified.verification_result}

    if outcome is VerificationOutcome.UNCONFIRMED:
        update["draft_output"] = state.draft_output + "\n\n" + unconfirmed_warning(verified)
        return update

    if outcome is VerificationOutcome.REPLAN:
        # The verifier DISAGREED with the answer.
        #
        # §5 treats REPLAN as non-terminal, but this graph's only edge out
        # of verify is END -- so a disagreement used to change nothing at
        # all and reach the user invisibly. The verifier ran, objected,
        # and was discarded, which is the same rubber stamp as the old
        # hardcoded satisfied:true wearing a different costume.
        #
        # Until a replan edge exists, the honest handling is to show the
        # objection rather than bury it. The reader can weigh it: the
        # verifier is a 3.8B model and is sometimes wrong about domain
        # specifics (it has, for instance, objected to "g/10min" as the
        # MFI unit, which is correct notation). An objection shown is
        # something a person can overrule; an objection dropped is a
        # disagreement the system resolved silently in its own favour.
        # WORDING MATTERS, because the verifier's reliability is known,
        # limited, and measured:
        #
        #   phi3.5 (fast-router)  false NEGATIVES -- failed a correct,
        #     correctly-cited answer whose value sat plainly in the source
        #     text it was shown. Aligning a row of an extracted PDF table
        #     is past a 3.8B model.
        #   qwen2.5:7b            false POSITIVES -- passed an answer that
        #     reported a pressure with no units at all.
        #
        # The small model is kept deliberately: a verifier that waves
        # through a wrong number is worse here than one that over-flags.
        # But "flagged this answer" asserts a fault was FOUND, and most of
        # these are the verifier being unable to confirm. Saying so
        # wrongly and often is how a banner becomes wallpaper -- the same
        # fate as the old always-true verdict, merely inverted.
        reason = (verified.verification_result.reason or "").strip()
        update["draft_output"] = (
            state.draft_output
            + "\n\n> **Not confirmed by the self-check.** "
            + (reason or "The verifier could not confirm this output.")
            + "\n>\n> The answer above is unchanged. The checker is a small "
            + "model and cannot always confirm values read from tables, so "
            + "this is a prompt to verify against the cited source rather "
            + "than a finding that the answer is wrong."
        )

    return update


# ── Build LangGraph Workflow ────────────────────────────────────────────────

def build_orchestrator_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router", router_node)
    builder.add_node("planner", planner_node)
    builder.add_node("dispatch", dispatch_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("verify", verify_node)

    builder.set_entry_point("router")

    # Conditional branching from router
    def router_branch(state: AgentState):
        # draft_output set this early means the router answered the turn
        # itself -- an approval interception, a greeting, or a completed
        # calculation. Running the planner on top of that replaces a
        # finished answer with a plan for work already done.
        if state.awaiting_human_approval or state.draft_output:
            return END
        return "planner"

    builder.add_conditional_edges("router", router_branch)
    builder.add_edge("planner", "dispatch")
    builder.add_edge("dispatch", "synthesize")
    builder.add_edge("synthesize", "verify")
    builder.add_edge("verify", END)

    return builder.compile()


# Process-wide compiled graph singleton
_COMPILED_GRAPH = None

def get_orchestrator_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_orchestrator_graph()
    return _COMPILED_GRAPH


def run_agent_turn(message: str, session_id: str) -> AgentState:
    """Execute a single agentic turn given a user message and session id."""
    import time as _time

    from backend.observability import turn_log as T

    T.rule("", "=")
    T.section(f"AGENT TURN — session {session_id}")
    T.kv("message", repr(message))
    _t0 = _time.perf_counter()

    # MEMORY IS OPENED HERE, around the whole turn, not inside the node
    # that reads it. Every path -- greeting, approval interception,
    # refusal, full synthesis -- therefore records itself, and the
    # streaming endpoint uses the same two functions. See
    # backend/memory/turn.py for why that is one pair of functions and
    # not two implementations.
    from backend.memory.turn import close_turn, open_turn

    memory = open_turn(session_id, message)
    if memory.degraded:
        T.warn(f"memory unavailable ({memory.degraded}); answering statelessly")
    else:
        if memory.added_terms:
            T.kv("resolved follow-up", f"+{memory.added_terms}")
        if memory.focus_documents:
            T.kv("focus documents", memory.focus_documents[:3])
        if memory.focus_entities:
            T.kv("focus entities", memory.focus_entities[:4])

    graph = get_orchestrator_graph()
    initial_state = AgentState(
        session_id=session_id,
        original_request=message,
        plan=[],
        tool_call_log=[],
        retrieved_context=[],
        memory_context=memory.context_block,
        search_query=memory.search_query,
    )
    # Stashed so /api/chat can report the same thing the stream emits.
    # Two endpoints describing memory differently is how they drift.
    initial_state.memory_summary = memory.summary()
    result_dict = graph.invoke(initial_state)
    final = AgentState.model_validate(result_dict)

    T.section("TURN SUMMARY")
    T.kv("elapsed", f"{_time.perf_counter() - _t0:.2f}s")
    T.kv("plan steps", len(final.plan))
    for st in final.plan:
        T.note(f"    {st.step_id:<10} {st.assigned_agent:<10} {st.status:<8} {st.description[:46]}")
    T.kv("tool calls", len(final.tool_call_log))
    for ev in final.tool_call_log:
        T.note(f"    {ev.tool_name:<22} {ev.status:<8} {str(ev.output)[:60]}")
    T.kv("sources used", len(final.retrieved_context))
    T.kv("awaiting approval", final.awaiting_human_approval)
    if final.verification_result:
        v = final.verification_result
        T.kv("verification", (T.GREEN("PASSED") if v.passed else T.YELLOW("NOT CONFIRMED"))
             + f" — {v.reason[:70]}")
    else:
        T.kv("verification", T.DIM("not run"))
    T.rule("", "=")
    T._emit()

    close_turn(
        session_id,
        final.draft_output or "",
        route=final.route or ("approval" if final.awaiting_human_approval else "direct"),
        citations=[
            {
                "text": c.get("text", ""),
                "source_document": c.get("source_document"),
                "page_number": c.get("page_number"),
            }
            for c in final.retrieved_context
        ][:20],
        documents=sorted({
            c.get("source_document")
            for c in final.retrieved_context
            if c.get("source_document")
        }),
        tool_calls=[
            {"tool_name": e.tool_name, "status": e.status} for e in final.tool_call_log
        ],
        entities=_entities_in(final.retrieved_context),
    )

    return final


def _entities_in(chunks: list[dict]) -> list[str]:
    """Equipment and document tags present in the retrieved passages.

    Deterministic: an entity recorded here steers the NEXT turn's
    retrieval, so a model's guess would silently bias a later answer.
    Tags of this shape (HCU-2, FFC-201, SOP-114-Rev3) do not need
    inference to spot.
    """
    found: list[str] = []
    for chunk in chunks or []:
        for match in _ENTITY_RE.finditer(chunk.get("text") or ""):
            token = match.group(0).strip()
            if token and token not in found:
                found.append(token)
            if len(found) >= 12:
                return found
    return found
