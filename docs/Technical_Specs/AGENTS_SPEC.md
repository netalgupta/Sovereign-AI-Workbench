# AGENTS_SPEC.md — Complete Multi-Agent Orchestration Specification

## 1. Framework
LangGraph (Python). The orchestrator is an explicit state graph, not a single long prompt loop — this is what makes the plan visible and inspectable in the frontend (FRONTEND.md §3.4), and what makes FR-5 demoable rather than just claimed.

## 2. State Object (exact shape, shared across all nodes)

```python
class AgentState(BaseModel):
    session_id: str
    original_request: str
    plan: list[PlanStep]
    current_step_index: int
    tool_call_log: list[ToolCallEvent]
    retrieved_context: list[RetrievedChunk]   # from RAG_SPEC.md
    draft_output: str | None
    verification_result: VerificationResult | None
    awaiting_human_approval: bool
    final_output_path: str | None

class PlanStep(BaseModel):
    step_id: str
    description: str
    assigned_agent: Literal["vision", "code", "reasoning", "math", "retrieval"]
    status: Literal["pending", "running", "done", "failed"]
    depends_on: list[str]   # step_ids that must complete first

class ToolCallEvent(BaseModel):
    tool_name: str
    input_params: dict
    output: dict | None
    status: Literal["pending", "running", "done", "failed"]
    timestamp: str
```

## 3. Graph Nodes (exact node names — the frontend's plan graph reads these directly, keep them stable)

```
[router] → [planner] → [dispatch] → {vision_agent | code_agent | reasoning_agent | math_tool | retrieval_agent}
                                              │
                                              ▼
                                    [verify] → [approval_gate] → [output_writer] → [END]
                                              │
                                    (if verification fails)
                                              ▼
                                         [planner] (re-plan, max 2 retries)
```

- **`router`**: calls CARD 03's `classify_task`, populates `AgentState.original_request`'s task tags
- **`planner`**: given task tags + `original_request`, calls the reasoning sub-agent with a plan-decomposition prompt (exact template below), populates `AgentState.plan` as a `PlanStep` list
- **`dispatch`**: reads `AgentState.plan`, for each step whose `depends_on` are all `done`, routes to the matching sub-agent node — this enables parallel execution of independent steps, not strictly sequential
- **`verify`**: calls the self-verification agent (phi-3.5-mini) with the exact prompt below
- **`approval_gate`**: sets `awaiting_human_approval = True`, halts graph execution (LangGraph's interrupt mechanism) until the frontend posts a confirm/cancel back to the backend
- **`output_writer`**: calls the relevant output-generation tool (CARD 06 etc.), sets `final_output_path`

## 4. Exact Planner Prompt

```
You are a task planner for an industrial AI assistant. Given the request below, produce a JSON list of steps. Each step must have: "step_id" (short unique string), "description" (one sentence), "assigned_agent" (one of "vision", "code", "reasoning", "math", "retrieval"), "depends_on" (list of step_ids that must complete first, empty list if none).

Only include steps that are actually necessary. Do not add speculative steps beyond what the request requires.

REQUEST:
{original_request}
```

## 5. Exact Verification Prompt

```
You are checking whether an AI assistant's output actually satisfies the original request. Answer with a JSON object: {"satisfied": true/false, "reason": "one sentence explanation", "missing": ["list of anything missing, empty if satisfied is true"]}.

ORIGINAL REQUEST:
{original_request}

PRODUCED OUTPUT:
{draft_output}
```

If `satisfied: false`, route back to `planner` with the `missing` list appended to context, up to a **maximum of 2 re-plan cycles** — after 2 failed verifications, halt and surface the issue to the human via the approval gate UI with an explicit "verification could not confirm this output is complete" flag, rather than looping indefinitely or silently shipping an unverified result.

## 6. Sub-Agent Contracts (what each node is allowed and forbidden to do)

| Sub-agent | Allowed | Forbidden |
|---|---|---|
| `vision_agent` | Call OCR/VLM tools (CARD 05 etc.), return extracted text/structure | Cannot call code execution or write files directly |
| `code_agent` | Call CARD 04 sandbox execution, iterate on failure up to 3 attempts | Cannot execute outside the sandbox under any circumstance |
| `reasoning_agent` | Draft text, call retrieval for grounding | Cannot state a fact without a citation if retrieval was available for that domain (enforced per RAG_SPEC.md §4) |
| `math_tool` | Call SymPy/NumPy/etc. directly (not an LLM call at all — a direct function call node) | N/A — this node never invokes an LLM, by design, per NFR-5 |
| `retrieval_agent` | Call hybrid_search (CARD 09) | Cannot fabricate a chunk if retrieval returns nothing — must return the explicit "not found" signal per RAG_SPEC.md §3 |

## 7. Human Approval Gate — Exact Trigger Conditions

The `approval_gate` node is mandatory (cannot be bypassed by any config flag) before:
1. Any `output_writer` call that writes a file to a persistent location
2. Any action that would constitute a "send" (email, external system call) — though no such action is in scope for the 10-day build per REQUIREMENTS.md §4, the gate exists in the architecture so this is a config addition later, not a redesign
3. Any SAP write action (out of scope for this build, but the gate is architecturally where it would attach)

## 8. Checkpointing (🟡 tier)
LangGraph's built-in checkpointer (SQLite backend) persists `AgentState` after every node transition, so a long-running task can be resumed after a pause without replaying completed steps. Implement this once the core graph (§3) is stable — do not let checkpointing complexity block the core loop's Day 1-2 delivery.

## 9. Testing Requirements
- A test that runs a full graph execution for a mocked multi-step request and asserts: plan has ≥2 steps, dispatch correctly parallelizes independent steps, verify triggers a re-plan when the mocked output is deliberately incomplete, approval_gate correctly halts execution until an external confirm signal is sent
- A test asserting the `math_tool` node never constructs an LLM API call — grep/mock-assert this directly, since it's a hard architectural guarantee (NFR-5), not just an expected behavior
