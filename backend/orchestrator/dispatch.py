"""The `dispatch` node and the sub-agent nodes — AGENTS_SPEC.md §3/§6,
TOOLS.md row 22 (🔴).

`dispatch` reads the plan and routes every step whose dependencies are
satisfied to its assigned sub-agent. §6 gives each sub-agent an explicit
allowed/forbidden contract, and this module is where those contracts are
CODE rather than prose — a sub-agent that can technically reach any tool
in the registry is not constrained by a table in a document.

THE CONTRACTS, AND HOW THEY ARE ENFORCED

Each sub-agent is given a restricted tool set (`_ALLOWED_TOOLS`), and
`run_step` refuses a call outside it. That is what makes §6's "Forbidden"
column real: `vision_agent` cannot write a file because `draft_docx` is
not in its set, not because we trust it not to try.

    vision_agent     extraction from any non-text-native modality.
                     §6 broadens this beyond images deliberately: audio
                     transcription lives here rather than getting its own
                     enum value for one tool.
    math_tool        NOT AN LLM CALL AT ALL. Per NFR-5 this node is a
                     direct function dispatch, and there is no code path
                     from it to a model. See the module-level assertion
                     below and its test.
    retrieval_agent  hybrid search only, and it must be able to return
                     "not found" — fabricating a chunk when retrieval is
                     empty is the specific failure RAG_SPEC §3 exists to
                     prevent.
    reasoning_agent  drafting, grounded in retrieval.
    code_agent       sandbox execution only. Not implemented here —
                     that is Aditya's module (CARD 04), and this node
                     fails loudly rather than silently doing nothing,
                     because a step that reports success without running
                     is worse than one that reports failure.

WHY dispatch RETURNS READY STEPS RATHER THAN ONE STEP: `depends_on`
exists so independent work can proceed together. Three retrievals with
no dependencies between them should be dispatchable at once; collapsing
that to a sequence throws away the only thing the dependency graph buys.
"""

from datetime import datetime, timezone

from backend.orchestrator.state import AgentState, PlanStep, ToolCallEvent

# §6's contracts, as the closed sets the dispatcher actually enforces.
# A tool absent from a sub-agent's set is not reachable by that
# sub-agent, whatever its step description asks for.
_ALLOWED_TOOLS: dict[str, set[str]] = {
    "vision_agent": {"extract_printed_text", "describe_chart_image", "transcribe_voice_note"},
    "math_tool": {
        "evaluate_expression",
        "evaluate_unit_expression",
        "lookup_thermophysical_property",
        "analyse_trend",
        "project_to_threshold",
        "describe_series",
        "plot_series",
    },
    "retrieval_agent": {"select_images_for_request"},
    "reasoning_agent": set(),  # drafts text; reaches retrieval through the retrieval agent
    "code_agent": set(),  # sandbox only, and the sandbox is not this module's
}

# PlanStep.assigned_agent uses the short names; the graph nodes use the
# long ones. Kept as an explicit map rather than string-concatenating
# "_agent", because math_tool does not follow that pattern and a silent
# mismatch there would route arithmetic to a model — the exact thing
# NFR-5 forbids.
_AGENT_TO_NODE = {
    "vision": "vision_agent",
    "code": "code_agent",
    "reasoning": "reasoning_agent",
    "math": "math_tool",
    "retrieval": "retrieval_agent",
}


class ContractViolation(Exception):
    """A sub-agent attempted a tool outside its §6 contract."""


class SubAgentError(Exception):
    """A sub-agent could not complete its step."""


def node_for(step: PlanStep) -> str:
    return _AGENT_TO_NODE[step.assigned_agent]


def allowed_tools(node_name: str) -> set[str]:
    return _ALLOWED_TOOLS.get(node_name, set())


def dispatch(state: AgentState) -> list[PlanStep]:
    """The `dispatch` node: every step that can start right now.

    Marks them running before returning, so two dispatch calls cannot
    hand the same step out twice — the state object is shared, and a
    caller that dispatches, awaits, then dispatches again would otherwise
    re-issue work already in flight.
    """
    ready = state.ready_steps()
    for step in ready:
        step.status = "running"
    return ready


def call_tool_as(node_name: str, tool_name: str, arguments: dict, approved: bool = False):
    """Call a tool ON BEHALF of a sub-agent, enforcing its §6 contract.

    This is the only path a sub-agent has to a tool. Going through the
    registry directly would bypass the contract, which is why sub-agent
    implementations below call this rather than `call_tool`.

    Raises:
        ContractViolation: the tool is outside this sub-agent's allowed
            set. Raised rather than returning an error value, because a
            contract breach is a bug in the plan or the agent, not a
            recoverable runtime condition.
    """
    from backend.tools import catalog  # noqa: F401 — registers everything
    from backend.tools.registry import call_tool

    permitted = allowed_tools(node_name)
    if tool_name not in permitted:
        raise ContractViolation(
            f"{node_name} may not call {tool_name!r}. AGENTS_SPEC §6 allows it: "
            f"{sorted(permitted) or 'no tools'}."
        )
    return call_tool(tool_name, arguments, approved=approved)


def run_math_step(step: PlanStep, tool_name: str, arguments: dict) -> ToolCallEvent:
    """The `math_tool` node — a DIRECT FUNCTION CALL, never an LLM call.

    NFR-5 is an architectural guarantee, not a behaviour: there is no
    code path from this function to a model. It does not import the
    router, does not resolve a model name, and does not construct a
    request to Ollama. A test asserts that by inspection, per
    AGENTS_SPEC §8's explicit instruction to grep/mock-assert it rather
    than trust it.

    The reason it matters: an LLM asked for a trend slope will produce a
    confident number, and a number that looks computed but was not is
    indistinguishable downstream from one that was.
    """
    event = ToolCallEvent(
        tool_name=tool_name,
        input_params=arguments,
        status="running",
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    try:
        result = call_tool_as("math_tool", tool_name, arguments)
    except Exception as exc:
        event.status = "failed"
        event.output = {"error": f"{type(exc).__name__}: {exc}"}
        step.status = "failed"
        raise SubAgentError(str(exc)) from exc

    event.status = "done"
    event.output = result.model_dump() if hasattr(result, "model_dump") else {"value": result}
    step.status = "done"
    return event


def run_retrieval_step(step: PlanStep, query: str, store) -> ToolCallEvent:
    """The `retrieval_agent` node — hybrid search, with "not found" as a
    real answer.

    §6: "Cannot fabricate a chunk if retrieval returns nothing — must
    return the explicit not-found signal per RAG_SPEC §3." So a refusal
    completes the step as DONE with an empty result, rather than failing
    it: "the corpus does not contain this" is a successful retrieval,
    and marking it failed would trigger a re-plan chasing something that
    is not there.
    """
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    event = ToolCallEvent(tool_name="hybrid_search", input_params={"query": query}, status="running")
    result = retrieve_with_grounding_check(store, query)

    event.status = "done"
    event.output = {
        "found": result.found,
        "reason": result.reason,
        "chunks": [
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in result.chunks
        ],
    }
    step.status = "done"
    return event


def run_vision_step(step: PlanStep, tool_name: str, arguments: dict) -> ToolCallEvent:
    """The `vision_agent` node — extraction from a non-text-native input.

    §6 forbids this agent from executing code or writing files; that is
    enforced by `_ALLOWED_TOOLS`, not by convention.

    A chart reading returned here carries `is_estimate` from the
    registry, so a downstream drafting step can mark it in its output
    rather than rediscovering that a vision model produced it.
    """
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import get_tool

    event = ToolCallEvent(tool_name=tool_name, input_params=arguments, status="running")
    try:
        result = call_tool_as("vision_agent", tool_name, arguments)
    except Exception as exc:
        event.status = "failed"
        event.output = {"error": f"{type(exc).__name__}: {exc}"}
        step.status = "failed"
        raise SubAgentError(str(exc)) from exc

    spec = get_tool(tool_name)
    payload = result.model_dump() if hasattr(result, "model_dump") else {"value": result}
    payload["is_estimate"] = bool(spec and spec.is_estimate)

    event.status = "done"
    event.output = payload
    step.status = "done"
    return event


def run_code_step(step: PlanStep, code: str) -> ToolCallEvent:
    """The `code_agent` node — sandbox execution only (CARD 04).

    Not implemented here: the sandbox is Aditya's module, and
    Aryan.md lists sandbox mechanics under "explicitly not your job".

    It raises rather than returning an empty success, because a step that
    reports done without running is worse than one that reports failure —
    the plan would continue on an output that does not exist, and the
    verification node would then be asked to check nothing.
    """
    step.status = "failed"
    raise SubAgentError(
        "code_agent requires the sandbox execution wrapper (CARD 04, backend/sandbox), "
        "which is not implemented yet. Refusing rather than reporting a step done "
        "without running it. Owner: Aditya."
    )
