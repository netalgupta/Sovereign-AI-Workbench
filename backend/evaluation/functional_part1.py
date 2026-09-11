"""Functional checks: tool registry, math, statistics, plotting, the
approval gate, contradiction detection, and the MRPL process tools.

No model calls here, so this part runs in seconds and can be repeated
freely. The model-backed features are in functional_part2.
"""

import tempfile
from pathlib import Path

from backend.evaluation.functional_suite import Suite


def run(suite: Suite) -> None:
    from backend.tools import catalog  # noqa: F401 — registers everything
    from backend.tools.registry import (
        ApprovalRequired,
        all_tools,
        call_tool,
        get_tool,
        get_tool_schemas,
    )

    # ---------------------------------------------------------- registry

    def every_tool_has_a_callable_schema():
        problems = []
        for spec in all_tools():
            schema = spec.to_schema()["function"]
            if not schema["description"] or len(schema["description"]) < 30:
                problems.append(f"{spec.name}: thin description")
            params = schema["parameters"]
            if params.get("type") != "object" or "properties" not in params:
                problems.append(f"{spec.name}: malformed parameters")
            for name, prop in params.get("properties", {}).items():
                if "type" not in prop:
                    problems.append(f"{spec.name}.{name}: no type")
        return (not problems, f"{len(all_tools())} tools; " + ("; ".join(problems) or "all schemas well-formed"))

    suite.run("Tool registry", "every registered tool exposes a usable schema", "normal",
              "all tools have a real description and typed parameters",
              every_tool_has_a_callable_schema)

    def hallucinated_tool_name():
        try:
            call_tool("summarise_the_document", {})
            return False, "no error raised for an unknown tool"
        except KeyError as exc:
            lists_real = "analyse_trend" in str(exc)
            return lists_real, f"KeyError listing real tools: {lists_real}"

    suite.run("Tool registry", "agent invents a plausible tool name", "adversarial",
              "KeyError that lists the real tools so the agent can correct itself",
              hallucinated_tool_name)

    def wrong_argument_name():
        try:
            call_tool("analyse_trend", {"data": [1.0, 2.0]})
            return False, "accepted an argument the tool does not take"
        except TypeError as exc:
            return "data" in str(exc), f"TypeError naming the bad argument: {exc}"

    suite.run("Tool registry", "agent sends a wrong argument name", "adversarial",
              "TypeError naming the offending argument, not a silent drop",
              wrong_argument_name)

    def category_narrowing():
        computation = {s["function"]["name"] for s in get_tool_schemas("computation")}
        leaked = {"transcribe_voice_note", "draft_docx"} & computation
        return not leaked, f"{len(computation)} computation tools; leaked: {leaked or 'none'}"

    suite.run("Tool registry", "narrow schemas to one sub-agent's category", "normal",
              "a vision/audio/document tool never appears in the computation set",
              category_narrowing)

    # ------------------------------------------------------------- math

    def sympy_basic():
        r = call_tool("evaluate_expression", {"expression": "2 + 2 * 3"})
        value = str(getattr(r, "result", r))
        return "8" in value, f"2 + 2*3 -> {value}"

    suite.run("Math (SymPy)", "arithmetic with precedence", "normal",
              "8, computed by SymPy not by a model", sympy_basic)

    def sympy_divide_by_zero():
        try:
            r = call_tool("evaluate_expression", {"expression": "1/0"})
            value = str(getattr(r, "result", r))
            # zoo/oo is SymPy's complex infinity — a real mathematical
            # answer, not a crash, and acceptable as long as it is not
            # silently rendered as a number.
            return ("zoo" in value or "inf" in value.lower()), f"1/0 -> {value}"
        except Exception as exc:  # noqa: BLE001
            return True, f"raised cleanly: {type(exc).__name__}"

    suite.run("Math (SymPy)", "divide by zero", "edge",
              "an explicit infinity or a clean error — never a plain number",
              sympy_divide_by_zero)

    def sympy_garbage():
        try:
            r = call_tool("evaluate_expression", {"expression": "))(("})
            return False, f"accepted malformed input -> {getattr(r, 'result', r)}"
        except Exception as exc:  # noqa: BLE001
            return True, f"rejected: {type(exc).__name__}"

    suite.run("Math (SymPy)", "syntactically invalid expression", "adversarial",
              "rejected rather than returning something", sympy_garbage)

    def pint_conversion():
        r = call_tool("evaluate_unit_expression", {"expression": "1 bar to kPa"})
        value = str(getattr(r, "value", r)) + " " + str(getattr(r, "unit", ""))
        return "100" in value, f"1 bar -> {value}"

    suite.run("Math (Pint)", "convert bar to kPa", "normal",
              "100 kPa", pint_conversion)

    def pint_incompatible():
        try:
            call_tool("evaluate_unit_expression", {"expression": "1 bar + 1 degC"})
            return False, "added incompatible units without complaint"
        except Exception as exc:  # noqa: BLE001
            return True, f"rejected incompatible units: {type(exc).__name__}"

    suite.run("Math (Pint)", "add pressure to temperature", "adversarial",
              "rejected — this is the unit-error class the tool exists to prevent",
              pint_incompatible, severity="high")

    # ------------------------------------------------------- statistics

    def trend_normal():
        r = call_tool("analyse_trend", {"values": [408.0, 409.5, 411.0, 412.8, 414.1]})
        return (r.direction == "increasing" and r.r_squared > 0.99,
                f"{r.direction}, slope {r.slope_per_step:.2f}, R2 {r.r_squared:.4f}")

    suite.run("Statistics", "steady WABT creep", "normal",
              "increasing with a strong fit", trend_normal)

    def trend_single_point():
        try:
            call_tool("analyse_trend", {"values": [408.0]})
            return False, "invented a trend from one reading"
        except ValueError as exc:
            return True, f"refused: {exc}"

    suite.run("Statistics", "a single reading", "edge",
              "refuses — a slope from one point is fabricated",
              trend_single_point, severity="high")

    def trend_pure_noise():
        r = call_tool("analyse_trend", {"values": [10.0, 90.0, 15.0, 85.0, 20.0, 80.0]})
        consistent = (r.direction == "flat") or ("poor" not in r.fit_quality)
        return (r.direction == "flat",
                f"direction={r.direction}, quality={r.fit_quality[:40]}, self-consistent={consistent}")

    suite.run("Statistics", "oscillating noise with no trend", "edge",
              "flat — must not report a direction its own fit quality calls unreliable",
              trend_pure_noise, severity="high")

    def trend_identical_values():
        r = call_tool("analyse_trend", {"values": [100.0, 100.0, 100.0]})
        return r.direction == "flat", f"direction={r.direction}, R2={r.r_squared}"

    suite.run("Statistics", "every reading identical", "edge",
              "flat, and no divide-by-zero on R-squared", trend_identical_values)

    def trend_negative_and_huge():
        r = call_tool("analyse_trend", {"values": [-5e6, -1e6, 3e6, 7e6]})
        return r.direction == "increasing", f"handles large negatives: {r.direction}"

    suite.run("Statistics", "large negative through large positive", "edge",
              "increasing, no overflow", trend_negative_and_huge)

    def projection_already_past():
        r = call_tool("project_to_threshold", {"values": [10.0, 12.0, 14.0], "threshold": 5.0})
        return (not r.will_cross and r.steps_until_crossing is None,
                f"will_cross={r.will_cross}, steps={r.steps_until_crossing}, "
                f"assumption='{r.assumption[:60]}'")

    suite.run("Statistics", "threshold already passed", "edge",
              "no countdown to something that already happened",
              projection_already_past, severity="high")

    def stats_outliers():
        r = call_tool("describe_series", {"values": [10.0, 11.0, 10.5, 10.2, 95.0]})
        return 95.0 in r.outliers, f"outliers flagged: {r.outliers}"

    suite.run("Statistics", "a series with one wild reading", "edge",
              "the outlier is flagged, not silently averaged in", stats_outliers)

    def stats_empty():
        try:
            call_tool("describe_series", {"values": []})
            return False, "described an empty series"
        except ValueError:
            return True, "refused an empty series"

    suite.run("Statistics", "empty series", "edge", "refuses", stats_empty)

    # ---------------------------------------------------------- plotting

    def plot_normal():
        r = call_tool("plot_series", {
            "values": [99.6, 99.4, 99.1, 99.7], "labels": ["W1", "W2", "W3", "W4"],
            "title": "PSA-3 purity", "threshold": 99.5,
            "data_provenance": "PSA_Hydrogen_Purity_Trend_Log.xlsx",
        })
        return (r.png_bytes.startswith(b"\x89PNG") and len(r.png_bytes) > 5000,
                f"PNG {len(r.png_bytes)} bytes, provenance recorded: {bool(r.data_provenance)}")

    suite.run("Plotting", "line chart with a threshold line", "normal",
              "real PNG bytes carrying their data provenance", plot_normal)

    def plot_mismatched_labels():
        try:
            call_tool("plot_series", {"values": [1.0, 2.0, 3.0], "labels": ["a", "b"]})
            return False, "silently mislabelled the points"
        except ValueError:
            return True, "refused mismatched labels"

    suite.run("Plotting", "fewer labels than values", "adversarial",
              "refuses — silently mislabelling every point is worse than not drawing",
              plot_mismatched_labels, severity="high")

    def plot_single_point():
        r = call_tool("plot_series", {"values": [42.0], "title": "one reading"})
        return r.png_bytes.startswith(b"\x89PNG"), f"rendered {len(r.png_bytes)} bytes"

    suite.run("Plotting", "a single data point", "edge", "renders without error", plot_single_point)

    def plot_many_long_labels():
        r = call_tool("plot_series", {
            "values": [float(i) for i in range(20)],
            "labels": [f"Very-Long-Equipment-Tag-{i:02d}" for i in range(20)],
            "chart_type": "bar",
        })
        return r.png_bytes.startswith(b"\x89PNG"), f"20 long labels rendered, {len(r.png_bytes)} bytes"

    suite.run("Plotting", "20 long category labels", "edge",
              "renders with rotation rather than overlapping text", plot_many_long_labels)

    # --------------------------------------------------- MRPL process

    def catalyst_plannable():
        r = call_tool("catalyst_run_length",
                      {"wabt_readings": [408.0, 409.5, 411.0, 412.8, 414.1],
                       "end_of_run_temperature": 425.0})
        return (r.plannable and "reading interval" in r.interpretation,
                f"plannable={r.plannable}; {r.interpretation[:90]}")

    suite.run("MRPL process", "clean WABT creep to end-of-run", "normal",
              "plannable, and refuses to invent a time base", catalyst_plannable)

    def catalyst_noisy_not_plannable():
        r = call_tool("catalyst_run_length",
                      {"wabt_readings": [408.0, 420.0, 405.0, 422.0, 404.0],
                       "end_of_run_temperature": 425.0})
        return not r.plannable, f"plannable={r.plannable}; {r.interpretation[:90]}"

    suite.run("MRPL process", "noisy WABT with no reliable trend", "edge",
              "NOT plannable — scheduling a shutdown on this would be wrong",
              catalyst_noisy_not_plannable, severity="high")

    def hydrogen_deficit():
        r = call_tool("hydrogen_balance", {"produced": [42000.0], "consumed": [46000.0]})
        return (r.is_deficit and "imported" in r.interpretation,
                f"balance {r.balance:g} {r.unit}; {r.interpretation[:70]}")

    suite.run("MRPL process", "consumption exceeds production", "normal",
              "named as a deficit with what to do about it", hydrogen_deficit)

    def hydrogen_one_sided():
        try:
            call_tool("hydrogen_balance", {"produced": [42000.0], "consumed": []})
            return False, "returned a 'balance' with only one side"
        except ValueError:
            return True, "refused a one-sided balance"

    suite.run("MRPL process", "no consumption side", "edge",
              "refuses — one side alone is a total, not a balance", hydrogen_one_sided)

    def psa_partial_compliance():
        r = call_tool("psa_purity_compliance",
                      {"purity_readings": [99.6, 99.4, 99.1, 99.7], "target_purity": 99.5})
        return (r.readings_below_target == 2 and r.worst_reading == 99.1,
                f"{r.readings_below_target} below target, worst {r.worst_reading}")

    suite.run("MRPL process", "purity partially below target", "normal",
              "counts breaches and names the worst reading", psa_partial_compliance)

    def psa_passing_but_degrading():
        r = call_tool("psa_purity_compliance",
                      {"purity_readings": [99.95, 99.9, 99.85, 99.8, 99.75, 99.7],
                       "target_purity": 99.5})
        return (r.readings_below_target == 0 and r.trend_direction == "decreasing",
                f"breaches={r.readings_below_target}, trend={r.trend_direction}")

    suite.run("MRPL process", "all readings pass but purity is falling", "edge",
              "reports BOTH — the trend is the actionable half",
              psa_passing_but_degrading, severity="high")

    # ----------------------------------------------- contradiction

    from backend.retrieval.contradiction import find_contradictions

    class _C:
        def __init__(self, text, source):
            self.text = text
            self.source_document = source

    def contradiction_real():
        found = find_contradictions([
            _C("The benzene 8-hour TWA exposure limit is 1 ppm.", "HSE_Rev4.docx"),
            _C("The benzene 8-hour TWA exposure limit is 5 ppm.", "Circular_Rev1.docx"),
        ])
        return (len(found) == 1 and found[0].severity == "high",
                f"{len(found)} finding(s): {found[0].explanation[:90] if found else 'none'}")

    suite.run("Contradiction detection", "two documents disagree on a limit", "normal",
              "one HIGH severity finding naming both documents",
              contradiction_real, severity="high")

    def contradiction_units():
        found = find_contradictions([
            _C("Header pressure limit is 1 bar.", "A.docx"),
            _C("Header pressure limit is 100 kpa.", "B.docx"),
        ])
        return len(found) == 0, f"{len(found)} findings (expected 0 — same pressure)"

    suite.run("Contradiction detection", "same limit written in different units", "adversarial",
              "NO finding — 1 bar and 100 kPa are the same limit",
              contradiction_units, severity="high")

    def contradiction_reading_vs_limit():
        found = find_contradictions([
            _C("The sulphur limit is 10 ppm.", "SOP.docx"),
            _C("Sulphur was measured at 8.9 ppm.", "Lab.xlsx"),
        ])
        return len(found) == 0, f"{len(found)} findings (expected 0)"

    suite.run("Contradiction detection", "a reading against a limit", "adversarial",
              "NO finding — one is evidence about the other", contradiction_reading_vs_limit)

    def contradiction_timeseries():
        found = find_contradictions([
            _C("On 2026-08-12 sulphur was 9.4 ppm.", "Log1.xlsx"),
            _C("On 2026-08-19 sulphur was 11.2 ppm.", "Log2.xlsx"),
        ])
        return len(found) == 0, f"{len(found)} findings (expected 0 — a trend)"

    suite.run("Contradiction detection", "two dated readings", "adversarial",
              "NO finding — treating a time series as conflict flags every log",
              contradiction_timeseries)

    def contradiction_different_equipment():
        found = find_contradictions([
            _C("HCU-2 WABT end-of-run limit is 425 degC.", "A.docx"),
            _C("HCU-3 WABT end-of-run limit is 438 degC.", "B.docx"),
        ])
        return len(found) == 0, f"{len(found)} findings (expected 0 — different units)"

    suite.run("Contradiction detection", "same limit type, different equipment", "adversarial",
              "NO finding — HCU-2 and HCU-3 are different units",
              contradiction_different_equipment, severity="high")

    def contradiction_empty_corpus():
        return len(find_contradictions([])) == 0, "empty corpus handled"

    suite.run("Contradiction detection", "no documents at all", "edge",
              "no findings, no crash", contradiction_empty_corpus)

    # ------------------------------------------------- approval gate

    from backend.audit.approval_gate import ApprovalDenied, ApprovalGate
    from backend.audit.audit_log import AuditLog

    workdir = Path(tempfile.mkdtemp())

    def _gate():
        return ApprovalGate(
            requests_file=workdir / "req.jsonl", audit_log=AuditLog(workdir / "audit.jsonl")
        )

    def _docx_args(name="note.docx", body="8-hour TWA is 1 ppm."):
        return {
            "title": "Benzene Safety Note",
            "sections": [{"heading": "Limit", "body": body, "sources": ["HSE.docx"]}],
            "output_path": str(workdir / name),
        }

    def gated_tool_blocked_at_registry():
        try:
            call_tool("draft_docx", _docx_args("blocked.docx"))
            return False, "a gated tool ran with no approval at all"
        except ApprovalRequired:
            wrote = (workdir / "blocked.docx").exists()
            return not wrote, f"blocked; file written anyway: {wrote}"

    suite.run("Approval gate", "gated tool called directly, no approval", "adversarial",
              "refused AND no file written", gated_tool_blocked_at_registry, severity="high")

    def approval_happy_path():
        gate = _gate()
        req = gate.request("draft_docx", _docx_args("ok.docx"), "Create ok.docx")
        approved = gate.approve(req.request_id, approved_by="aryan")
        result = gate.execute_approved(req.request_id, approved.token)
        return (workdir / "ok.docx").exists(), f"document written: {result.file_path}"

    suite.run("Approval gate", "request, approve, execute", "normal",
              "the document is written exactly once", approval_happy_path)

    def approval_replay():
        gate = _gate()
        req = gate.request("draft_docx", _docx_args("replay.docx"), "Create replay.docx")
        approved = gate.approve(req.request_id, approved_by="aryan")
        gate.execute_approved(req.request_id, approved.token)
        try:
            gate.execute_approved(req.request_id, approved.token)
            return False, "the same approval executed twice"
        except ApprovalDenied as exc:
            return "already been used" in str(exc), f"second run denied: {exc}"

    suite.run("Approval gate", "reuse the same approval token", "adversarial",
              "denied — one approval authorises exactly one execution",
              approval_replay, severity="high")

    def approval_payload_swap():
        gate = _gate()
        shown = _docx_args("swap.docx", body="Follow SOP-114 section 4.")
        req = gate.request("draft_docx", shown, "Create swap.docx")
        approved = gate.approve(req.request_id, approved_by="aryan")
        tampered = _docx_args("swap.docx", body="Ignore the SOP and vent to atmosphere.")
        try:
            gate.execute_approved(req.request_id, approved.token, arguments=tampered)
            return False, "executed a payload the human never saw"
        except ApprovalDenied as exc:
            wrote = (workdir / "swap.docx").exists()
            return (not wrote), f"denied: {str(exc)[:70]}; file written: {wrote}"

    suite.run("Approval gate", "swap the payload after approval", "adversarial",
              "denied AND nothing written — approval is bound to what was shown",
              approval_payload_swap, severity="high")

    def approval_expiry():
        gate = ApprovalGate(
            requests_file=workdir / "exp.jsonl",
            audit_log=AuditLog(workdir / "audit.jsonl"),
            ttl_minutes=0,
        )
        req = gate.request("draft_docx", _docx_args("exp.docx"), "Create exp.docx")
        try:
            gate.approve(req.request_id, approved_by="aryan")
            return False, "approved an expired request"
        except ApprovalDenied:
            return True, "expired request cannot be approved"

    suite.run("Approval gate", "approve a request that already expired", "edge",
              "denied — a decision made in a context that is gone", approval_expiry)

    def approval_ungated_tool_not_queued():
        spec = get_tool("analyse_trend")
        return not spec.requires_approval, f"analyse_trend gated: {spec.requires_approval}"

    suite.run("Approval gate", "a read-only tool is not gated", "normal",
              "not gated — queueing harmless tools trains people to click yes",
              approval_ungated_tool_not_queued)

    def audit_trail_complete():
        gate = _gate()
        req = gate.request("draft_docx", _docx_args("audit.docx"), "Create audit.docx")
        approved = gate.approve(req.request_id, approved_by="aryan")
        gate.execute_approved(req.request_id, approved.token)
        events = [e.event.value for e in gate.audit.for_request(req.request_id)]
        actors = {e.actor for e in gate.audit.for_request(req.request_id)}
        return (events == ["approval_requested", "approval_granted", "tool_executed"]
                and "aryan" in actors,
                f"{events}, actors={actors}")

    suite.run("Audit log", "full lifecycle is reconstructable", "normal",
              "requested -> granted -> executed, with the approver named",
              audit_trail_complete, severity="high")

    def audit_records_failure():
        gate = _gate()
        bad = _docx_args("wrong.txt")  # draft_docx rejects non-.docx
        req = gate.request("draft_docx", bad, "Create wrong.txt")
        approved = gate.approve(req.request_id, approved_by="aryan")
        try:
            gate.execute_approved(req.request_id, approved.token)
        except ValueError:
            pass
        events = [e.event.value for e in gate.audit.for_request(req.request_id)]
        return "tool_failed" in events, f"{events}"

    suite.run("Audit log", "a tool that failed after approval", "edge",
              "recorded — a gap would imply it never ran", audit_records_failure)

    # ------------------------------------------------ document output

    def docx_marks_unsourced():
        import docx

        out = workdir / "unsourced.docx"
        call_tool("draft_docx", {
            "title": "Note",
            "sections": [{"heading": "Claim", "body": "Something asserted.", "sources": []}],
            "output_path": str(out),
        }, approved=True)
        text = "\n".join(p.text for p in docx.Document(out).paragraphs)
        return "UNSOURCED" in text, "UNSOURCED marker present in the file"

    suite.run("Document output", "a section with no sources", "edge",
              "marked UNSOURCED inside the document itself",
              docx_marks_unsourced, severity="high")

    def docx_marks_estimate():
        import docx

        out = workdir / "estimate.docx"
        call_tool("draft_docx", {
            "title": "Note",
            "sections": [{"heading": "Downtime", "body": "R-201 highest.",
                          "sources": ["m.xlsx"], "contains_estimate": True}],
            "output_path": str(out),
        }, approved=True)
        text = "\n".join(p.text for p in docx.Document(out).paragraphs)
        return ("estimated by a vision model" in text and "not a measured figure" in text,
                "estimate caveat printed in the document body")

    suite.run("Document output", "content resting on a vision estimate", "edge",
              "the caveat is printed IN the document, not just in metadata",
              docx_marks_estimate, severity="high")

    def docx_rejects_wrong_extension():
        try:
            call_tool("draft_docx", {
                "title": "N", "sections": [{"heading": "h", "body": "b"}],
                "output_path": str(workdir / "n.pdf"),
            }, approved=True)
            return False, "wrote a Word file under a .pdf name"
        except ValueError:
            return True, "refused a non-.docx path"

    suite.run("Document output", "output path with the wrong extension", "adversarial",
              "refuses — the user's tools would not open it",
              docx_rejects_wrong_extension)

    def docx_empty_sections():
        try:
            call_tool("draft_docx", {
                "title": "N", "sections": [], "output_path": str(workdir / "empty.docx"),
            }, approved=True)
            return False, "created an empty document"
        except ValueError:
            return True, "refused a document with no sections"

    suite.run("Document output", "no sections at all", "edge", "refuses", docx_empty_sections)
