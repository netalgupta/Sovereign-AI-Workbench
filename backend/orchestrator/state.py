"""The shared agent state — AGENTS_SPEC.md §2, verbatim shape.

Every node in the graph reads and writes this one object. The shape is
copied exactly from the spec rather than adapted, for a specific reason:
FRONTEND.md §3.4's plan graph reads these field names directly, so a
rename here is a silent break in a component owned by a different person
on a different branch. The spec is the contract between us.

WHY A SINGLE STATE OBJECT rather than passing arguments between nodes:
the plan has to be inspectable mid-run. FR-5 is demoable only if a
frontend can poll one structure and see which step is running, what each
step is waiting on, and every tool call made so far. Threading that
through function arguments would mean the visible plan is a
reconstruction, and reconstructions drift from what actually happened.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["vision", "code", "reasoning", "math", "retrieval"]
StepStatus = Literal["pending", "running", "done", "failed"]


class PlanStep(BaseModel):
    step_id: str
    description: str
    assigned_agent: AgentName
    status: StepStatus = "pending"
    # step_ids that must reach "done" before this step may run. Empty
    # means it can start immediately — which is what makes independent
    # steps parallelisable rather than merely ordered.
    depends_on: list[str] = Field(default_factory=list)


class ToolCallEvent(BaseModel):
    tool_name: str
    input_params: dict
    output: dict | None = None
    status: StepStatus = "pending"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class VerificationResult(BaseModel):
    passed: bool
    reason: str = ""
    checked_claims: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    session_id: str
    original_request: str
    plan: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    tool_call_log: list[ToolCallEvent] = Field(default_factory=list)
    retrieved_context: list[dict] = Field(default_factory=list)
    draft_output: str | None = None
    verification_result: VerificationResult | None = None
    awaiting_human_approval: bool = False
    final_output_path: str | None = None
    # Not in the spec's listing, but required by its own §3 note that
    # re-planning is capped at 2 retries: a cap needs somewhere to count.
    # Without it the failure path is "re-plan forever", which is how an
    # agent burns an afternoon of local inference on an impossible task.
    replan_count: int = 0
    # Also not in the spec's listing. Memory is opened ONCE per turn, at
    # the entry point, rather than inside the node that happens to need
    # it -- otherwise a turn answered before synthesis (a greeting, an
    # approval interception) never records itself, and the session grows
    # holes. Carried on the state so every node sees the same context.
    memory_context: str = ""
    # The query RETRIEVAL should run, which may differ from what the
    # user typed once a follow-up is resolved. Never changes the request
    # shown to the model.
    search_query: str | None = None
    # How this turn was answered. Recorded with the message so a later
    # turn can tell "I refused for lack of sources" from "I answered
    # from a constant" -- the two look identical in the text and mean
    # opposite things when interpreting what came before.
    route: str | None = None
    # What memory contributed, for the UI. Counts and names only -- the
    # context block itself stays off screen (see TurnMemory.summary()).
    memory_summary: dict = Field(default_factory=dict)

    def ready_steps(self) -> list[PlanStep]:
        """Steps whose dependencies are all satisfied and which have not run.

        This is what `dispatch` consumes. Returning a LIST rather than
        the next single step is deliberate and is the whole point of
        `depends_on`: three independent retrieval steps should be able to
        run together rather than queue behind each other.
        """
        done = {s.step_id for s in self.plan if s.status == "done"}
        return [
            step
            for step in self.plan
            if step.status == "pending" and all(dep in done for dep in step.depends_on)
        ]

    def is_blocked(self) -> bool:
        """Work remains, but nothing can start.

        Distinct from "finished" and it must not be confused with it: a
        plan with an unsatisfiable dependency (a step waiting on one that
        failed, or on an id that does not exist) would otherwise look
        complete and be reported as success.
        """
        return bool(
            [s for s in self.plan if s.status == "pending"] and not self.ready_steps()
        )

    def is_complete(self) -> bool:
        return bool(self.plan) and all(s.status in ("done", "failed") for s in self.plan)
