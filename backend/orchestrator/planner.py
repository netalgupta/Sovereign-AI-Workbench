from __future__ import annotations

"""The planner node — AGENTS_SPEC.md §3/§4, TOOLS.md row 20 (🔴), FR-5.

Decomposes a request into a dependency graph of steps, each assigned to
a sub-agent. This is the node that makes FR-5 "demoable rather than just
claimed": the plan it produces is the thing the frontend draws.

THE PROMPT IS §4 VERBATIM. Unlike GRAPH_SPEC §5's extraction prompt —
which this session changed, with measurement, because it offered the
model three structurally impossible options — this one has no such
defect, so it stays exactly as specified.

WHAT THIS MODULE ADDS AROUND THE MODEL, and why each piece exists rather
than trusting the output:

  * The model names its own step_ids and dependencies, and it gets them
    wrong in specific, recurring ways: a dependency on a step it never
    emitted, two steps sharing an id, a step depending on itself, and
    cycles. Every one of those produces a plan that LOOKS fine and then
    hangs at dispatch, because no step is ever ready. A hang is the
    worst possible failure mode here — it is indistinguishable from slow
    local inference. So the plan is validated into something executable
    or rejected outright, never handed on in a state that can stall.

  * An unknown `assigned_agent` is repaired rather than dropped. The
    spec's five agents are a closed set, but a model asked for
    "retrieval" will occasionally answer "rag" or "search". Dropping the
    step loses real work the request needed; defaulting it to
    "reasoning" keeps the step and lets the dispatcher route it
    somewhere that can at least attempt it.
"""

import json
import logging
import re

from backend.models.ollama_client import generate as ollama_generate
from backend.models.registry import resolve_model_name
from backend.orchestrator.state import AgentState, PlanStep
from backend.utils.llm_output import strip_code_fences

# AGENTS_SPEC.md §4, verbatim. Built by concatenation rather than
# str.format() for the same reason entity_extraction.py does: the prompt
# contains literal { } characters in its JSON-shape description, which
# .format() would try to interpret as placeholders.
_PLANNER_PROMPT_PREFIX = (
    "You are a task planner for an industrial AI assistant. Given the request "
    'below, produce a JSON list of steps. Each step must have: "step_id" (short '
    'unique string), "description" (one sentence), "assigned_agent" (one of '
    '"vision", "code", "reasoning", "math", "retrieval"), "depends_on" (list of '
    "step_ids that must complete first, empty list if none).\n\n"
    "Only include steps that are actually necessary. Do not add speculative steps "
    "beyond what the request requires.\n\n"
    "REQUEST:\n"
)

VALID_AGENTS = {"vision", "code", "reasoning", "math", "retrieval"}

# A plan longer than this is a planning failure, not an ambitious plan.
# Each step costs a sub-agent call measured in tens of seconds on this
# hardware, so a 40-step plan is half an hour before the user sees
# anything — and in practice a runaway plan is repetitive rather than
# thorough.
MAX_PLAN_STEPS = 12


logger = logging.getLogger("backend.orchestrator.planner")


class PlanningError(Exception):
    """The model's output could not be made into an executable plan."""


def _call_planner_model(prompt: str, model_name: str) -> str:
    
    # Routed through ollama_client so the GPU placement option
    # (num_gpu) applies here too. It previously did not: each of
    # the four call sites built its own request body, so an option
    # added in one place silently missed the others.
    return ollama_generate(
        model_name,
        prompt,
        timeout=300,
    )


# WORK THAT ACTUALLY REQUIRES EACH SPECIALIST AGENT.
#
# validate_plan checked that assigned_agent was a MEMBER of VALID_AGENTS
# and nothing more, so any step could claim any agent as long as the
# name was spelled right. Observed consequences, both real:
#
#   "Give sops for Hydrocrackers"
#     -> step assigned_agent="code", description="Create standard
#        operating procedures for hydrocrackers"
#     -> dispatched to the sandbox, which cannot write an SOP, and the
#        step failed in the trace.
#
#   "What is the average MFI for Homopolymer H030SG?"
#     -> step assigned_agent="math", description="Calculate the average
#        MFI value from the retrieved data"
#     -> evaluate_expression ran and correctly reported "no arithmetic
#        expression found in the request". There was nothing to
#        calculate: the average is printed verbatim in the source table.
#
# Neither is harmless. A mis-assigned step runs a tool nobody needed,
# fails, and puts a failure in a trace the user is being asked to trust
# -- while the work the step described never happens.
#
# So the description has to corroborate the agent. When it does not, the
# step is REASSIGNED rather than dropped: the work it describes is still
# needed, it just needs a different worker. Dropping it would produce an
# answer missing a piece nobody knows is missing, which is the failure
# mode validate_plan's existing repair comment already warns about.
_CODE_WORK = re.compile(
    r"\b(code|script|program|execute|run|compile|debug|parse|regex|"
    r"algorithm|function|api call|query the database|sql)\b",
    re.I,
)
_MATH_WORK = re.compile(
    r"\b(calculate|compute|sum|average|mean|median|integrate|"
    r"differentiate|solve|convert|percentage|ratio|deviation|"
    r"interpolat|extrapolat|regression|projection|forecast)\b",
    re.I,
)
_VISION_WORK = re.compile(
    r"\b(image|diagram|chart|photo|scan|p&id|schematic|figure|ocr|"
    r"visual|picture|drawing)\b",
    re.I,
)


def _agent_fits_description(agent: str, description: str) -> bool:
    """Does the described work actually need this specialist?

    Only the three specialist agents are gated. "retrieval" and
    "reasoning" are the general cases and are always acceptable -- being
    strict about those would reject correct plans for no benefit, and
    the cost of a wrong specialist (a failed tool call) is much higher
    than the cost of a step that reasons when it could have retrieved.
    """
    if agent == "code":
        return bool(_CODE_WORK.search(description))
    if agent == "math":
        return bool(_MATH_WORK.search(description))
    if agent == "vision":
        return bool(_VISION_WORK.search(description))
    return True


def _fallback_agent(description: str) -> str:
    """Where a mis-assigned step should go instead."""
    if re.search(r"\b(retrieve|find|look up|search|gather|locate|"
                 r"fetch|get|identify)\b", description, re.I):
        return "retrieval"
    return "reasoning"


def validate_plan(raw_steps: list[dict]) -> list[PlanStep]:
    """Turn the model's proposed steps into an executable plan, or refuse.

    Every repair below is for a failure actually seen from local models
    asked to emit a dependency graph. The unifying rule: a plan that
    cannot make progress must fail LOUDLY here, because at dispatch it is
    indistinguishable from slow inference.

    Raises:
        PlanningError: on no steps, or a dependency structure with no
            possible starting point.
    """
    if not raw_steps:
        raise PlanningError("The planner returned no steps.")
    if len(raw_steps) > MAX_PLAN_STEPS:
        raw_steps = raw_steps[:MAX_PLAN_STEPS]

    steps: list[PlanStep] = []
    seen_ids: set[str] = set()

    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        step_id = str(raw.get("step_id") or f"step_{index + 1}").strip()
        # Duplicate ids make `depends_on` ambiguous — a dependency on
        # "step_2" cannot be satisfied when there are two of them, and
        # the dispatcher would treat whichever it found first as
        # authoritative.
        while step_id in seen_ids:
            step_id = f"{step_id}_{index + 1}"
        seen_ids.add(step_id)

        agent = str(raw.get("assigned_agent", "")).strip().lower()
        if agent not in VALID_AGENTS:
            # Repaired, not dropped: the step represents work the request
            # needed, and losing it silently produces an answer missing a
            # piece nobody knows is missing.
            agent = "reasoning"

        description = str(raw.get("description", "")).strip()
        if not description:
            description = f"Step {index + 1}"

        # The agent must be corroborated by the work, not just spelled
        # correctly. See _agent_fits_description for the two real
        # mis-assignments this catches.
        if not _agent_fits_description(agent, description):
            replacement = _fallback_agent(description)
            logger.info(
                "plan step %s: reassigned %r -> %r; the description %r does "
                "not describe work that agent can do",
                step_id, agent, replacement, description[:80],
            )
            agent = replacement

        raw_deps = raw.get("depends_on") or []
        deps = [str(d).strip() for d in raw_deps if isinstance(d, (str, int))]

        steps.append(
            PlanStep(
                step_id=step_id,
                description=description,
                assigned_agent=agent,
                status="pending",
                depends_on=deps,
            )
        )

    known = {s.step_id for s in steps}
    for step in steps:
        # A self-dependency can never be satisfied: the step waits for
        # itself to finish before it may start.
        # A dangling dependency names a step the model never emitted.
        # Both are dropped rather than failing the plan, because the step
        # itself is usually sound and only its stated ordering is wrong.
        step.depends_on = [d for d in step.depends_on if d in known and d != step.step_id]

    _break_cycles(steps)

    # Backstop, and deliberately kept even though the repairs above make
    # it unreachable: once dangling and self dependencies are dropped and
    # cycles are broken, the remaining graph is a finite DAG, and a finite
    # DAG always has at least one node with no outgoing edges — a step
    # with an empty depends_on. So this cannot fire today.
    #
    # It stays because it is the invariant the dispatcher depends on, and
    # the cheapest place to catch a future change to _break_cycles that
    # quietly stops guaranteeing it. The failure it guards against is a
    # HANG, which at dispatch is indistinguishable from slow local
    # inference — worth an unreachable three lines to never debug.
    if not any(not s.depends_on for s in steps):
        raise PlanningError(
            "Every step depends on another, so nothing can start. The planner "
            "produced a plan that would hang rather than run."
        )
    return steps


def _break_cycles(steps: list[PlanStep]) -> None:
    """Remove dependency edges that form a cycle.

    A cycle deadlocks dispatch: each step waits on another that is
    waiting on it. Detected with a depth-first walk; the edge that closes
    a cycle is dropped, which keeps every step in the plan and only
    loosens an ordering constraint the model got wrong. Dropping whole
    steps instead would silently discard requested work.
    """
    by_id = {s.step_id: s for s in steps}
    state: dict[str, int] = {}  # 0 unvisited, 1 in progress, 2 finished

    def visit(step_id: str) -> None:
        state[step_id] = 1
        step = by_id[step_id]
        for dep in list(step.depends_on):
            if state.get(dep, 0) == 1:
                step.depends_on.remove(dep)  # this edge closes a cycle
            elif state.get(dep, 0) == 0:
                visit(dep)
        state[step_id] = 2

    for step in steps:
        if state.get(step.step_id, 0) == 0:
            visit(step.step_id)


def plan_request(
    state: AgentState, model_id: str = "reasoning-model", planner_fn=None
) -> AgentState:
    """The `planner` node: populate state.plan from state.original_request.

    Args:
        state: the shared agent state.
        model_id: registry id, never a raw model name (hard constraint
            #2) — resolved through models.yaml.
        planner_fn: injection point for tests, taking (prompt, model_name)
            and returning raw model text. Real calls go to Ollama.

    Returns the SAME state object, mutated — LangGraph nodes are
    state-in/state-out, and returning a copy here would silently discard
    anything a concurrent node wrote.
    """
    caller = planner_fn or _call_planner_model
    model_name = resolve_model_name(model_id)
    raw = caller(_PLANNER_PROMPT_PREFIX + state.original_request, model_name)

    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError as exc:
        raise PlanningError(f"Planner did not return JSON: {raw[:200]!r}") from exc

    # Models wrap the list in an object about as often as they return it
    # bare, and both are reasonable readings of "produce a JSON list".
    if isinstance(parsed, dict):
        for key in ("steps", "plan", "tasks"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        raise PlanningError(f"Planner returned {type(parsed).__name__}, not a list of steps.")

    state.plan = validate_plan(parsed)
    state.current_step_index = 0
    return state
