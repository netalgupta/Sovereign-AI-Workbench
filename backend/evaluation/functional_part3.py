"""Functional checks: the orchestrator nodes, the API surface, and the
graph — the parts that need a live model or a live database.

Anything whose dependency is down is SKIPPED with the reason, never
silently passed. A green report that only went green because the thing
under test was unreachable is worse than a red one.
"""

import json
import time

from backend.evaluation.functional_suite import Suite


def _model_available(model_id: str) -> tuple[bool, str]:
    """Is the model this check needs actually PULLED, not just Ollama up?

    Checking only that Ollama responds was a flaw in this harness, caught
    by its own run: the router check FAILED with a 404 because
    phi-3.5-mini is not pulled on this machine, and reported as a broken
    router. A missing dependency must skip with the reason, never fail as
    if the code were wrong — a red mark that means "you did not install
    this" trains people to ignore red marks.
    """
    import requests

    from backend.models.registry import resolve_model_name

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        if not response.ok:
            return False, "Ollama is not responding"
    except Exception:  # noqa: BLE001
        return False, "Ollama is unreachable"

    try:
        wanted = resolve_model_name(model_id)
    except Exception as exc:  # noqa: BLE001
        return False, f"{model_id} is not in models.yaml: {exc}"

    pulled = {m["name"] for m in response.json().get("models", [])}
    # Ollama reports "name:tag"; a registry entry may omit the tag.
    if wanted in pulled or any(p.split(":")[0] == wanted.split(":")[0] for p in pulled):
        return True, wanted
    return False, f"{wanted} is not pulled on this Ollama (run: ollama pull {wanted})"


def _neo4j_up() -> bool:
    try:
        from backend.graph.neo4j_client import GraphClient

        client = GraphClient("bolt://localhost:7687", "neo4j", "testpassword123")
        client.verify_connectivity()
        client.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def run(suite: Suite) -> None:
    # ------------------------------------------------------- planner

    from backend.orchestrator.planner import PlanningError, plan_request, validate_plan
    from backend.orchestrator.state import AgentState

    def _fake(payload):
        def call(prompt, model_name):
            return json.dumps(payload) if not isinstance(payload, str) else payload
        return call

    def planner_handles_model_garbage():
        """Local models return prose instead of JSON often enough that
        this is a normal case, not an exotic one."""
        try:
            plan_request(AgentState(session_id="s", original_request="r"),
                         planner_fn=_fake("Sure! I'd be happy to help you plan that."))
            return False, "accepted prose as a plan"
        except PlanningError as exc:
            return True, f"rejected: {str(exc)[:60]}"

    suite.run("Planner", "model returns prose instead of JSON", "adversarial",
              "PlanningError — an empty plan would be executed as 'nothing to do'",
              planner_handles_model_garbage, severity="high")

    def planner_repairs_a_tangled_plan():
        plan = validate_plan([
            {"step_id": "a", "description": "x", "assigned_agent": "math", "depends_on": ["b"]},
            {"step_id": "b", "description": "y", "assigned_agent": "math", "depends_on": ["c"]},
            {"step_id": "c", "description": "z", "assigned_agent": "math", "depends_on": ["b"]},
        ])
        state = AgentState(session_id="s", original_request="r", plan=plan)
        return (len(plan) == 3 and bool(state.ready_steps()),
                f"{len(plan)} steps kept, {len(state.ready_steps())} able to start")

    suite.run("Planner", "every step depends on another (cycle)", "adversarial",
              "repaired into a runnable plan without discarding steps — a hang is "
              "indistinguishable from slow inference",
              planner_repairs_a_tangled_plan, severity="high")

    def planner_handles_ghost_dependencies():
        plan = validate_plan([
            {"step_id": "a", "description": "x", "assigned_agent": "retrieval", "depends_on": []},
            {"step_id": "b", "description": "y", "assigned_agent": "reasoning",
             "depends_on": ["a", "step_that_was_never_emitted"]},
        ])
        return plan[1].depends_on == ["a"], f"deps after repair: {plan[1].depends_on}"

    suite.run("Planner", "a dependency on a step the model never emitted", "adversarial",
              "dropped — otherwise the step waits forever on an id nobody completes",
              planner_handles_ghost_dependencies, severity="high")

    def planner_caps_a_runaway():
        from backend.orchestrator.planner import MAX_PLAN_STEPS

        plan = validate_plan([
            {"step_id": f"s{i}", "description": "x", "assigned_agent": "reasoning",
             "depends_on": []} for i in range(60)
        ])
        return len(plan) == MAX_PLAN_STEPS, f"60 proposed -> {len(plan)} kept"

    suite.run("Planner", "a 60-step plan", "edge",
              "capped — each step is tens of seconds of local inference",
              planner_caps_a_runaway)

    def planner_rejects_an_empty_plan():
        try:
            validate_plan([])
            return False, "accepted an empty plan"
        except PlanningError:
            return True, "rejected"

    suite.run("Planner", "the model returns zero steps", "edge",
              "rejected — an empty plan reports success having done nothing",
              planner_rejects_an_empty_plan, severity="high")

    # -------------------------------------------------- verification

    from backend.orchestrator.verification import (
        MAX_REPLAN_CYCLES,
        VerificationOutcome,
        parse_verification,
        unconfirmed_warning,
        verify_output,
    )

    def verification_fails_closed_on_garbage():
        result = parse_verification("Looks good to me, I'd say that's satisfied!")
        return not result.passed, f"passed={result.passed}; reason='{result.reason[:60]}'"

    suite.run("Self-verification", "verifier returns prose, not JSON", "adversarial",
              "treated as UNVERIFIED — defaulting to satisfied makes a malformed "
              "response a silent pass",
              verification_fails_closed_on_garbage, severity="high")

    def verification_empty_output_is_not_a_pass():
        state = AgentState(session_id="s", original_request="Draft a note.", draft_output=None)
        state, outcome = verify_output(state, verifier_fn=_fake({"satisfied": True}))
        return (outcome is VerificationOutcome.UNCONFIRMED,
                f"outcome={outcome.value} even though the verifier said satisfied")

    suite.run("Self-verification", "nothing was produced to verify", "edge",
              "UNCONFIRMED — a step that produced nothing must not reach the gate as verified",
              verification_empty_output_is_not_a_pass, severity="high")

    def verification_halts_after_two_cycles():
        state = AgentState(session_id="s", original_request="r", draft_output="x")
        outcomes = []
        for _ in range(4):
            state, outcome = verify_output(
                state,
                verifier_fn=_fake({"satisfied": False, "reason": "no citation",
                                   "missing": ["a citation"]}),
            )
            outcomes.append(outcome.value)
        replans = outcomes.count("replan")
        return (replans == MAX_REPLAN_CYCLES and outcomes[-1] == "unconfirmed",
                f"outcomes: {outcomes}")

    suite.run("Self-verification", "verification fails four times running", "adversarial",
              "exactly 2 re-plans then UNCONFIRMED — never loops, never silently ships",
              verification_halts_after_two_cycles, severity="high")

    def unconfirmed_warning_is_readable():
        state = AgentState(session_id="s", original_request="r", draft_output="x")
        state.replan_count = MAX_REPLAN_CYCLES
        state, _ = verify_output(
            state,
            verifier_fn=_fake({"satisfied": False, "reason": "No source given.",
                               "missing": ["a citation"]}),
        )
        warning = unconfirmed_warning(state)
        return (all(s in warning for s in ("could not confirm", "No source given.", "Review it")),
                f"'{warning[:110]}'")

    suite.run("Self-verification", "the message shown to a human", "normal",
              "says what was checked, what was missing, and that it is not vouched for",
              unconfirmed_warning_is_readable)

    # ------------------------------------------ sub-agent contracts

    from backend.orchestrator.dispatch import ContractViolation, call_tool_as, dispatch
    from backend.orchestrator.state import PlanStep

    def vision_agent_cannot_write_a_file():
        try:
            call_tool_as("vision_agent", "draft_docx",
                         {"title": "x", "sections": [], "output_path": "x.docx"})
            return False, "vision_agent reached a file-writing tool"
        except ContractViolation as exc:
            return True, f"refused: {str(exc)[:70]}"

    suite.run("Sub-agent contracts", "vision_agent attempts a file write", "adversarial",
              "refused by the closed tool set, not by convention",
              vision_agent_cannot_write_a_file, severity="high")

    def math_tool_cannot_reach_a_vision_model():
        try:
            call_tool_as("math_tool", "describe_chart_image", {"image_path": "x.png"})
            return False, "math_tool reached an estimate-producing tool"
        except ContractViolation:
            return True, "refused — an estimate must not enter where a computed number is expected"

    suite.run("Sub-agent contracts", "math_tool attempts a chart reading", "adversarial",
              "refused", math_tool_cannot_reach_a_vision_model, severity="high")

    def dispatch_does_not_double_issue():
        state = AgentState(session_id="s", original_request="r", plan=[
            PlanStep(step_id="a", description="x", assigned_agent="math"),
        ])
        first, second = dispatch(state), dispatch(state)
        return (len(first) == 1 and second == [],
                f"first={len(first)}, second={len(second)}")

    suite.run("Sub-agent contracts", "dispatch called twice before any step finishes", "edge",
              "the same step is never handed out twice", dispatch_does_not_double_issue)

    # -------------------------------------------------------- API

    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)

    def api_health_reports_dependencies():
        body = client.get("/api/health").json()
        keys = {"graph_available", "corpus_loaded", "images_stored", "documents_registered"}
        return keys <= set(body), f"health keys: {sorted(set(body) & keys)}"

    suite.run("API", "GET /api/health", "normal",
              "reports each dependency, so a UI can explain an empty screen",
              api_health_reports_dependencies)

    def api_docs_disabled():
        return (client.get("/docs").status_code == 404,
                "FastAPI's CDN-backed Swagger page is disabled")

    suite.run("API", "GET /docs", "normal",
              "404 — the default page fetches JS from a CDN, violating hard constraint #1",
              api_docs_disabled, severity="high")

    def api_unknown_tool_is_404():
        r = client.post("/api/tools/call", json={"name": "nope", "arguments": {}})
        return r.status_code == 404, f"status {r.status_code}"

    suite.run("API", "call a tool that does not exist", "adversarial",
              "404, correctable by the caller", api_unknown_tool_is_404)

    def api_gated_tool_without_approval_is_403():
        r = client.post("/api/tools/call", json={
            "name": "draft_docx",
            "arguments": {"title": "x", "sections": [{"heading": "h", "body": "b"}],
                          "output_path": "should_not_exist.docx"},
        })
        from pathlib import Path

        return (r.status_code == 403 and not Path("should_not_exist.docx").exists(),
                f"status {r.status_code}, file written: {Path('should_not_exist.docx').exists()}")

    suite.run("API", "call a gated tool over HTTP with no approval", "adversarial",
              "403 AND no file written", api_gated_tool_without_approval_is_403, severity="high")

    def api_bad_arguments_are_400():
        r = client.post("/api/tools/call",
                        json={"name": "analyse_trend", "arguments": {"values": [1.0]}})
        return r.status_code == 400, f"status {r.status_code}"

    suite.run("API", "a tool called with invalid arguments", "adversarial",
              "400 with the tool's own message", api_bad_arguments_are_400)

    def api_approval_flow_over_http():
        import tempfile
        from pathlib import Path

        out = Path(tempfile.mkdtemp()) / "api_note.docx"
        args = {"title": "Note",
                "sections": [{"heading": "Limit", "body": "1 ppm.", "sources": ["HSE.docx"]}],
                "output_path": str(out)}
        req = client.post("/api/approvals/request",
                          json={"tool_name": "draft_docx", "arguments": args}).json()
        leaked = "token" in req
        blocked = client.post("/api/approvals/execute",
                              json={"request_id": req["request_id"], "token": "guess"})
        approved = client.post("/api/approvals/approve",
                               json={"request_id": req["request_id"],
                                     "decided_by": "aryan"}).json()
        done = client.post("/api/approvals/execute",
                           json={"request_id": req["request_id"], "token": approved["token"]})
        replay = client.post("/api/approvals/execute",
                             json={"request_id": req["request_id"], "token": approved["token"]})
        return (not leaked and blocked.status_code == 403 and done.status_code == 200
                and replay.status_code == 403 and out.exists(),
                f"token leaked={leaked}, pre-approval={blocked.status_code}, "
                f"execute={done.status_code}, replay={replay.status_code}, written={out.exists()}")

    suite.run("API", "full approval flow over HTTP", "normal",
              "no token leak, 403 before approval, 200 once, 403 on replay",
              api_approval_flow_over_http, severity="high")

    def api_metrics_carry_timestamps():
        body = client.get("/api/metrics").json()
        present = {k: v for k, v in body.items() if v}
        ok = all("measured_at" in v for v in present.values())
        return ok and bool(present), f"{len(present)} metric sets, all timestamped: {ok}"

    suite.run("API", "GET /api/metrics", "normal",
              "every result carries when it was measured", api_metrics_carry_timestamps)

    def api_search_refuses_off_topic():
        r = client.post("/api/search", json={"query": "What is the plot of Pride and Prejudice?"})
        body = r.json()
        return (not body["found"], f"found={body['found']}, reason='{body.get('reason')}'")

    suite.run("API", "POST /api/search with an off-topic question", "adversarial",
              "found=false with an explicit reason", api_search_refuses_off_topic,
              severity="high")

    def api_contradictions_runs():
        body = client.get("/api/contradictions").json()
        return ("contradictions" in body and "checked_chunks" in body,
                f"checked {body.get('checked_chunks')} chunks, "
                f"{len(body.get('contradictions', []))} findings")

    suite.run("API", "GET /api/contradictions", "normal",
              "sweeps the corpus and reports", api_contradictions_runs)

    def api_graph_declares_provenance():
        r = client.get("/api/graph")
        if r.status_code == 503:
            return True, "503 with a reason (Neo4j down and no snapshot) — honest"
        body = r.json()
        return (body.get("source") in ("live", "snapshot"),
                f"source={body.get('source')}, nodes={len(body.get('nodes', []))}, "
                f"warning={(body.get('warning') or 'none')[:60]}")

    suite.run("API", "GET /api/graph with Neo4j down", "edge",
              "falls back to the snapshot and SAYS so, rather than serving an empty graph",
              api_graph_declares_provenance, severity="high")

    # -------------------------------------------------------- graph

    if not _neo4j_up():
        suite.skip("Knowledge graph", "signature query for Mangalore-Hassan",
                   "Neo4j unreachable — Docker Desktop is not running on this machine")
        suite.skip("Knowledge graph", "relationship domain/range validity",
                   "Neo4j unreachable — Docker Desktop is not running on this machine")
    else:
        def signature_query():
            from backend.graph.neo4j_client import GraphClient

            client = GraphClient("bolt://localhost:7687", "neo4j", "testpassword123")
            result = client.signature_pipeline_segment_query("Mangalore-Hassan")
            client.close()
            return (result.segment_found and len(result.related_documents) >= 2,
                    f"found={result.segment_found}, docs={result.related_documents}")

        suite.run("Knowledge graph", "signature query for Mangalore-Hassan", "normal",
                  "segment found with both referencing documents", signature_query)

        def relationships_are_spec_valid():
            from backend.graph.neo4j_client import GraphClient

            client = GraphClient("bolt://localhost:7687", "neo4j", "testpassword123")
            with client._driver.session() as session:
                rows = list(session.run(
                    "MATCH (a)-[r]->(b) RETURN labels(a)[0] AS f, type(r) AS t, labels(b)[0] AS o"
                ))
            client.close()
            from backend.graph.entity_extraction import RELATIONSHIP_DOMAIN_RANGE

            bad = [
                f"({r['f']})-[{r['t']}]->({r['o']})"
                for r in rows
                if r["t"] in RELATIONSHIP_DOMAIN_RANGE
                and not (r["f"] in RELATIONSHIP_DOMAIN_RANGE[r["t"]][0]
                         and r["o"] in RELATIONSHIP_DOMAIN_RANGE[r["t"]][1])
            ]
            return not bad, f"{len(rows)} edges, {len(bad)} violating GRAPH_SPEC §4: {bad[:3]}"

        suite.run("Knowledge graph", "every stored edge against GRAPH_SPEC §4", "normal",
                  "no edge violates its own domain/range table",
                  relationships_are_spec_valid, severity="high")

    # ------------------------------------------- live model (router)

    available, detail = _model_available("fast-router")
    if not available:
        suite.skip("Live model", "router classifies a real request", detail)
    else:
        def router_classifies():
            from backend.orchestrator.router import classify_task

            started = time.time()
            result = classify_task("Calculate the hydrogen balance for CCR-1 in Nm3/h")
            return (result is not None,
                    f"classified in {time.time() - started:.0f}s -> {result}")

        suite.run("Live model", "router classifies a real request", "normal",
                  "returns a classification from the live model", router_classifies)
