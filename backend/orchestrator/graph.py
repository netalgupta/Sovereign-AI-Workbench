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
    (r"\b(save|write|export|generate|draft)\b.{0,30}?\b(file|report|document|docx|"
     r"xlsx|pdf|to\s+disk)\b", "file write"),
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
        gate = ApprovalGate()
        app_req = gate.request(
            tool_name="operator_requested_action",
            arguments={"command": req, "category": action_kind},
            effect=(
                f"Operator-requested {action_kind}, from the instruction: "
                f"\"{req.strip()}\". The concrete target and magnitude have NOT "
                f"been resolved by the system and must be confirmed by the operator."
            ),
        )
        reply = (
            f"**Action intercepted — human approval required.**\n\n"
            f"This request was classified as a **{action_kind}**, which hard "
            f"constraint #4 does not permit the system to perform unattended.\n\n"
            f"> 🛑 **Approval gate [FR-15 / §3.12]** — nothing has been executed. "
            f"The workbench has not resolved a target device, value, or file for "
            f"this instruction; approving records your authorisation for the "
            f"action as you described it.\n\n"
            f"Confirm or cancel in the approval dialog."
        )
        return {
            "draft_output": reply,
            "awaiting_human_approval": True,
            "final_output_path": app_req.request_id,
        }

    return {}


def planner_node(state: AgentState) -> dict[str, Any]:
    """Decompose the request into an executable DAG of PlanSteps."""
    if state.awaiting_human_approval:
        return {}

    try:
        updated = plan_request(state)
        # Ensure every step has an associated event id for the UI Plan DAG
        for s in updated.plan:
            if not getattr(s, "step_id", None):
                s.step_id = f"step_{len(updated.plan)}"
        return {"plan": updated.plan, "current_step_index": 0}
    except Exception:
        # Fallback to standard deterministic multi-step plan if offline/Ollama unavailable
        try:
            task_type = classify_task(state.original_request)
        except Exception:
            task_type = "reasoning"
        fallback_steps = [
            PlanStep(
                step_id="step-1",
                description="Retrieve operational parameters and technical specifications",
                assigned_agent="retrieval",
                status="pending",
                depends_on=[],
            ),
            PlanStep(
                step_id="step-2",
                description="Verify engineering calculations and safety envelopes",
                assigned_agent="math" if task_type == "math" else "reasoning",
                status="pending",
                depends_on=["step-1"],
            ),
            PlanStep(
                step_id="step-3",
                description="Synthesize verified findings into grounded briefing",
                assigned_agent="reasoning",
                status="pending",
                depends_on=["step-2"],
            ),
        ]
        return {"plan": fallback_steps, "current_step_index": 0}


def dispatch_node(state: AgentState) -> dict[str, Any]:
    """Dispatch and execute all ready steps in the dependency graph."""
    if state.awaiting_human_approval:
        return {}

    from backend.api.state import get_state

    pipeline_state = get_state()
    tool_log = list(state.tool_call_log)
    retrieved = list(state.retrieved_context)

    # Process ready steps
    ready = state.ready_steps()
    while ready:
        for step in ready:
            step.status = "running"
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
                            output={"result": str(res)},
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

    try:
        store, _ = get_state().ensure_corpus()
        answer = generate_grounded_answer(store, state.original_request)
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
        return {"draft_output": "\n".join(lines)}

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

    try:
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
        reason = (verified.verification_result.reason or "").strip()
        update["draft_output"] = (
            state.draft_output
            + "\n\n> **Self-check flagged this answer.** "
            + (reason or "The verifier did not confirm this output.")
            + "\n>\n> The answer above is shown unchanged. Treat it as "
            + "unconfirmed until checked against the cited source."
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
        if state.awaiting_human_approval:
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

    graph = get_orchestrator_graph()
    initial_state = AgentState(
        session_id=session_id,
        original_request=message,
        plan=[],
        tool_call_log=[],
        retrieved_context=[],
    )
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

    return final
