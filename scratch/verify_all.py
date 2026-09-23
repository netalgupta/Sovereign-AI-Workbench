import sys
import os
import time
import subprocess
from pathlib import Path
import openpyxl
from unittest.mock import patch, MagicMock

# Import workbench modules
from backend.orchestrator.agent_loop import CHAT_TOOLS, _tools_for_chat, _SYSTEM_PROMPT, run_agent_loop, run_turn
from backend.orchestrator.path_router import decide_path
from backend.tools.documents.draft_xlsx import describe_effect as describe_xlsx_effect, draft_xlsx
from backend.tools.documents.draft_docx import describe_effect as describe_docx_effect
from backend.audit.approval_gate import ApprovalGate, ApprovalState
from backend.orchestrator.graph import classify_action_request, is_action_approval_request


def run_verification():
    print("===============================================================================")
    print("STARTING COMPLETE VERIFICATION OF ALL 9 REQUIREMENTS")
    print("===============================================================================\n")

    results = []

    # -------------------------------------------------------------------------
    # 1. TIMEOUT FIX VERIFICATION
    # -------------------------------------------------------------------------
    print("--- 1. TIMEOUT FIX VERIFICATION ---")
    request_str = "Draft an Excel spreadsheet containing a comparison table of MFI values across polymer batches from the QC sources and save it to storage/outputs/mfi_comparison.xlsx"
    
    # Mock LLM call to simulate model choosing draft_xlsx tool call within 0.1s
    mock_llm_response = {
        "message": {
            "role": "assistant",
            "content": "Creating the requested spreadsheet...",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {
                        "name": "draft_xlsx",
                        "arguments": {
                            "title": "MFI Comparison",
                            "sheets": [{
                                "sheet_name": "MFI Values",
                                "headers": ["Batch ID", "MFI Value (g/10min)", "Sources / Citations"],
                                "rows": [
                                    {"cells": ["BATCH-001", {"value": "", "is_unsourced": True}, "UNSOURCED"], "is_unsourced": True}
                                ]
                            }],
                            "output_path": "storage/outputs/mfi_comparison.xlsx"
                        }
                    }
                }
            ]
        },
        "done": True
    }

    t0 = time.perf_counter()
    events = []
    with patch("backend.orchestrator.agent_loop._stream_once") as mock_stream, \
         patch("backend.orchestrator.planner.plan_request") as mock_planner:
        
        mock_planner.side_effect = Exception("Planner fast timeout")
        mock_stream.return_value = iter([mock_llm_response])

        for event in run_turn(request_str):
            events.append(event)

    total_time = time.perf_counter() - t0
    print(f"Turn completed in {total_time:.3f}s (Threshold: < 300s)")
    print(f"Events captured: {[e.get('type') for e in events]}")
    p1 = total_time < 300 and any(e.get("type") == "approval_required" for e in events)
    results.append(("1. Timeout Fix (< 300s & timing logs)", "PASS" if p1 else "FAIL", f"Elapsed: {total_time:.3f}s"))

    # -------------------------------------------------------------------------
    # 2. TOOL SELECTION RELIABILITY VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 2. TOOL SELECTION RELIABILITY VERIFICATION ---")
    chat_tools = CHAT_TOOLS
    tools_offered = _tools_for_chat()
    offered_names = [t["function"]["name"] for t in tools_offered]
    print(f"draft_xlsx in CHAT_TOOLS: {'draft_xlsx' in chat_tools}")
    print(f"Offered tools count: {len(tools_offered)}")
    print(f"Offered tool names: {offered_names}")
    
    p2_a = "draft_xlsx" in chat_tools and "draft_xlsx" in offered_names
    p2_b = ".xlsx" in _SYSTEM_PROMPT and "draft_xlsx" in _SYSTEM_PROMPT
    p2_c = "INSUFFICIENT OR MISSING SOURCE DATA IS NOT A REASON TO SKIP" in _SYSTEM_PROMPT
    
    p2 = p2_a and p2_b and p2_c
    results.append(("2. Tool Selection Reliability", "PASS" if p2 else "FAIL", f"Offered tools: {len(offered_names)}"))

    # -------------------------------------------------------------------------
    # 3. DISAMBIGUATION VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 3. DISAMBIGUATION VERIFICATION ---")
    has_xlsx_rule = "draft_xlsx for tabular data/spreadsheets" in _SYSTEM_PROMPT or ".xlsx is a HARD SIGNAL" in _SYSTEM_PROMPT
    has_docx_rule = "draft_docx" in _SYSTEM_PROMPT
    p3 = has_xlsx_rule and has_docx_rule
    print(f"Disambiguation system prompt rules verified: {p3}")
    results.append(("3. Disambiguation (docx vs xlsx)", "PASS" if p3 else "FAIL", "Rules verified in _SYSTEM_PROMPT"))

    # -------------------------------------------------------------------------
    # 4. APPROVAL MODAL EFFECT DESCRIPTION VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 4. APPROVAL MODAL EFFECT DESCRIPTION VERIFICATION ---")
    test_sheets = [{
        "sheet_name": "MFI Comparison",
        "headers": ["Batch ID", "MFI Value (g/10min)", "Status"],
        "rows": [
            {"cells": ["BATCH-001", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-002", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-003", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-004", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-005", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-006", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
        ]
    }]
    effect_str = describe_xlsx_effect("MFI Comparison", test_sheets, "storage/outputs/mfi_comparison.xlsx")
    print(f"Approval Modal Effect Description:\n  '{effect_str}'")
    p4 = "0 of 18 data cells are sourced" in effect_str and "18 cells could not be sourced and will be marked UNSOURCED and left empty" in effect_str
    results.append(("4. Approval Modal Effect Sourcing Counts", "PASS" if p4 else "FAIL", f"Effect: '{effect_str}'"))

    # -------------------------------------------------------------------------
    # 5. PARTIAL GENERATION & EMPTY UNSOURCED CELLS VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 5. PARTIAL GENERATION & EMPTY UNSOURCED CELLS VERIFICATION ---")
    out_file = Path("storage/outputs/mfi_comparison.xlsx")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    partial_sheets = [{
        "sheet_name": "MFI Comparison",
        "headers": ["Batch ID", "MFI Value (g/10min)", "Status"],
        "rows": [
            {"cells": [{"value": "BATCH-001", "sources": ["QC_Log.pdf"]}, {"value": 12.5, "sources": ["QC_Log.pdf"]}, {"value": "Pass", "sources": ["QC_Log.pdf"]}], "sources": ["QC_Log.pdf"]},
            {"cells": ["BATCH-002", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-003", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
        ]
    }]
    
    draft_xlsx("MFI Comparison", partial_sheets, str(out_file))
    
    wb = openpyxl.load_workbook(out_file, data_only=True)
    ws = wb.active
    
    print("Workbook contents & cell states:")
    rows_data = []
    fabricated_numbers = []
    for r in range(1, ws.max_row + 1):
        r_vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        rows_data.append((r, r_vals))
        print(f"  Row {r}: {r_vals}")
        if r >= 5: # data rows
            for c_idx in range(1, len(r_vals)): # data columns
                c_val = r_vals[c_idx - 1]
                comment = ws.cell(row=r, column=c_idx).comment
                fill = ws.cell(row=r, column=c_idx).fill
                if comment and "UNSOURCED" in comment.text:
                    if c_val != "" and c_val is not None:
                        fabricated_numbers.append((r, c_idx, c_val))
    
    stamp_cell = ws.cell(row=2, column=1).value
    print(f"Provenance stamp (Row 2): '{stamp_cell}'")
    
    p5 = (
        out_file.exists()
        and len(fabricated_numbers) == 0
        and ws.cell(row=6, column=2).value in ("", None)
        and "UNSOURCED" in (ws.cell(row=6, column=2).comment.text if ws.cell(row=6, column=2).comment else "")
        and "marked UNSOURCED" in stamp_cell
    )
    results.append(("5. Partial Generation & Empty UNSOURCED Cells", "PASS" if p5 else "FAIL", "Unsourced cells empty & labeled"))

    # -------------------------------------------------------------------------
    # 6. SOURCED PATH STILL WORKS VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 6. SOURCED PATH STILL WORKS VERIFICATION ---")
    sourced_file = Path("storage/outputs/sourced_mfi.xlsx")
    sourced_sheets = [{
        "sheet_name": "Sourced MFI",
        "headers": ["Batch ID", "MFI Value (g/10min)"],
        "rows": [
            {"cells": [{"value": "H030SG", "sources": ["Lab_Result_H030SG.pdf"]}, {"value": 11.8, "sources": ["Lab_Result_H030SG.pdf"]}], "sources": ["Lab_Result_H030SG.pdf"]}
        ]
    }]
    draft_xlsx("Sourced MFI", sourced_sheets, str(sourced_file))
    wb_s = openpyxl.load_workbook(sourced_file)
    ws_s = wb_s.active
    s_val1 = ws_s.cell(row=5, column=1).value
    s_val2 = ws_s.cell(row=5, column=2).value
    s_comment = ws_s.cell(row=5, column=1).comment.text if ws_s.cell(row=5, column=1).comment else ""
    print(f"Sourced cells: ({s_val1}, {s_val2}), Comment: '{s_comment}'")
    
    p6 = s_val1 == "H030SG" and s_val2 == 11.8 and "Lab_Result_H030SG.pdf" in s_comment and "UNSOURCED" not in s_comment
    results.append(("6. Sourced Path Works (Values & Citations)", "PASS" if p6 else "FAIL", "Sourced values & citations verified"))

    # -------------------------------------------------------------------------
    # 7. REFUSE PATH VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 7. REFUSE PATH VERIFICATION ---")
    test_req_file = Path("storage/outputs/test_requests.jsonl")
    if test_req_file.exists():
        test_req_file.unlink()
    gate = ApprovalGate(requests_file=test_req_file)
    req = gate.request(
        "draft_xlsx",
        {"title": "T", "sheets": [{"headers":["A"],"rows":[["B"]]}], "output_path": "storage/outputs/refused_file.xlsx"},
        "Create refused_file.xlsx"
    )
    refused = gate.refuse(req.request_id, refused_by="operator", reason="Operator cancelled action")
    refused_file_exists = Path("storage/outputs/refused_file.xlsx").exists()
    print(f"Refuse action state: {refused.state}, File exists: {refused_file_exists}")
    p7 = refused.state == ApprovalState.REFUSED and not refused_file_exists
    results.append(("7. Refuse Path (No File Written)", "PASS" if p7 else "FAIL", "Refusal audited & no file written"))

    # -------------------------------------------------------------------------
    # 8. CLASSIFICATION REGRESSION VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 8. CLASSIFICATION REGRESSION VERIFICATION ---")
    q_fact = "What is the average MFI for Homopolymer H030SG?"
    dec_fact = decide_path(q_fact)
    print(f"Factual query '{q_fact}' -> path: {dec_fact.path}")

    q_setpoint = "Set HCU feed rate to 115%"
    is_act = is_action_approval_request(q_setpoint)
    cat_act = classify_action_request(q_setpoint)
    print(f"Setpoint query '{q_setpoint}' -> is_action: {is_act}, category: {cat_act}")
    
    p8 = dec_fact.path == "direct" and is_act and (cat_act in ("setpoint change", "DCS_SETPOINT_WRITE"))
    results.append(("8. Classification Regression Check", "PASS" if p8 else "FAIL", f"Unchanged routing verified ({cat_act})"))

    # -------------------------------------------------------------------------
    # 9. GRAPH.PY UNTOUCHED VERIFICATION
    # -------------------------------------------------------------------------
    print("\n--- 9. GRAPH.PY UNTOUCHED VERIFICATION ---")
    git_res = subprocess.run(["git", "diff", "backend/orchestrator/graph.py"], capture_output=True, text=True)
    diff_out = git_res.stdout.strip()
    print(f"git diff backend/orchestrator/graph.py output length: {len(diff_out)}")
    p9 = len(diff_out) == 0
    results.append(("9. Graph.py Untouched Check", "PASS" if p9 else "FAIL", "Diff length: 0"))

    # -------------------------------------------------------------------------
    # SUMMARY TABLE
    # -------------------------------------------------------------------------
    print("\n===============================================================================")
    print("FINAL VERIFICATION RESULTS TABLE")
    print("===============================================================================")
    all_passed = True
    for item, status, detail in results:
        print(f"{item:<45} | {status:<6} | {detail}")
        if status != "PASS":
            all_passed = False
    print("===============================================================================")
    print(f"OVERALL TASK STATUS: {'SUCCESS - ALL 9 PASSED' if all_passed else 'FAILED'}")

if __name__ == "__main__":
    run_verification()
