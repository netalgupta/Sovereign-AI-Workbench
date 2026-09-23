import sys
import os
import time
import json
from pathlib import Path
import openpyxl

from backend.orchestrator.agent_loop import run_turn, run_agent_loop, _SYSTEM_PROMPT
from backend.orchestrator.path_router import decide_path
from backend.tools.documents.draft_xlsx import describe_effect as describe_xlsx_effect, draft_xlsx
from backend.tools.documents.draft_docx import describe_effect as describe_docx_effect
from backend.audit.approval_gate import ApprovalGate, ApprovalState
from backend.orchestrator.graph import classify_action_request, is_action_approval_request

def test_1_timeout_fix():
    print("--- VERIFICATION 1: Timeout Fix ---")
    request = "Draft an Excel spreadsheet containing a comparison table of MFI values across polymer batches from the QC sources and save it to storage/outputs/mfi_comparison.xlsx"
    t0 = time.perf_counter()
    events = []
    app_required = False
    for event in run_turn(request):
        elapsed = time.perf_counter() - t0
        events.append((elapsed, event))
        if event.get("type") == "approval_required":
            app_required = True
        print(f"[{elapsed:6.2f}s] Event: {event.get('type')}")
        if elapsed > 120:
            print("Turn taking longer than 120s...")
            break
    total_time = time.perf_counter() - t0
    print(f"Total Turn Time: {total_time:.2f}s (Threshold: < 300s)")
    passed = total_time < 300 and app_required
    print(f"RESULT 1: {'PASS' if passed else 'FAIL'}")
    return passed, total_time, events

def test_2_tool_selection():
    print("\n--- VERIFICATION 2: Tool Selection Reliability ---")
    phrasings = [
        "Draft an Excel spreadsheet of MFI values across polymer batches",
        "Create an Excel file at storage/outputs/test_mfi.xlsx with MFI values for polymer batches",
        "Build a comparison table of MFI values across polymer batches"
    ]
    results = []
    all_passed = True
    for p in phrasings:
        tool_called = None
        for event in run_turn(p):
            if event.get("type") in ("tool_call", "approval_required"):
                tool_called = event.get("name")
                break
        print(f"Phrasing: '{p}' -> Tool called: {tool_called}")
        if tool_called == "draft_xlsx":
            results.append((p, tool_called, "PASS"))
        else:
            results.append((p, tool_called, "FAIL"))
            all_passed = False
    print(f"RESULT 2: {'PASS' if all_passed else 'FAIL'}")
    return all_passed, results

def test_3_disambiguation():
    print("\n--- VERIFICATION 3: Disambiguation (Prose -> draft_docx) ---")
    request = "Draft an inspection report on the hydrocracker unit"
    tool_called = None
    for event in run_turn(request):
        if event.get("type") in ("tool_call", "approval_required"):
            tool_called = event.get("name")
            break
    print(f"Prose Request: '{request}' -> Tool called: {tool_called}")
    passed = tool_called == "draft_docx"
    print(f"RESULT 3: {'PASS' if passed else 'FAIL'}")
    return passed, tool_called

def test_4_approval_modal_effect():
    print("\n--- VERIFICATION 4: Approval Modal Effect Description ---")
    sheets = [{
        "sheet_name": "MFI Comparison",
        "headers": ["Batch ID", "MFI Value (g/10min)", "Status"],
        "rows": [
            {"cells": ["BATCH-001", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True},
            {"cells": ["BATCH-002", {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "is_unsourced": True}
        ]
    }]
    effect = describe_xlsx_effect("MFI Comparison", sheets, "storage/outputs/mfi_comparison.xlsx")
    print(f"Effect output: '{effect}'")
    has_count_lang = "data cells are sourced" in effect or "cells could not be sourced and will be marked UNSOURCED" in effect
    print(f"RESULT 4: {'PASS' if has_count_lang else 'FAIL'}")
    return has_count_lang, effect

def test_5_partial_generation_inspection():
    print("\n--- VERIFICATION 5: Partial Generation & Inspection ---")
    out_path = Path("storage/outputs/mfi_comparison.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate file with unsourced cells
    sheets = [{
        "sheet_name": "MFI Comparison",
        "headers": ["Batch ID", "MFI Value (g/10min)", "Status"],
        "rows": [
            {"cells": [{"value": "BATCH-H030SG-1", "sources": ["SOP-101.pdf"]}, {"value": "", "is_unsourced": True}, {"value": "", "is_unsourced": True}], "sources": ["SOP-101.pdf"]},
            {"cells": ["BATCH-H030SG-2", {"value": "INVALID_FABRICATED_VAL", "is_unsourced": True}, ""], "is_unsourced": True}
        ]
    }]
    
    draft_xlsx("MFI Comparison", sheets, str(out_path))
    
    wb = openpyxl.load_workbook(out_path, data_only=True)
    ws = wb.active
    
    # Inspect cells
    cell_contents = []
    fabricated_found = False
    for r in range(1, ws.max_row + 1):
        row_vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        cell_contents.append((r, row_vals))
        print(f"Row {r}: {row_vals}")
        # Check if unsourced data cell contains fabricated numeric/text payload
        for col_idx, val in enumerate(row_vals, start=1):
            if r >= 5 and col_idx < len(row_vals): # data cell
                comment = ws.cell(row=r, column=col_idx).comment
                if comment and "UNSOURCED" in comment.text:
                    if val != "" and val is not None:
                        fabricated_found = True
                        print(f"ERROR: Found value '{val}' in unsourced cell ({r}, {col_idx})")
    
    passed = out_path.exists() and not fabricated_found
    print(f"RESULT 5: {'PASS' if passed else 'FAIL'}")
    return passed, cell_contents

def test_6_sourced_path():
    print("\n--- VERIFICATION 6: Sourced Path ---")
    out_path = Path("storage/outputs/sourced_test.xlsx")
    sheets = [{
        "sheet_name": "Sourced Sheet",
        "headers": ["Batch ID", "Density (g/cm3)"],
        "rows": [
            {"cells": [{"value": "H030SG", "sources": ["Spec_Sheet_H030SG.pdf"]}, {"value": "0.905", "sources": ["Spec_Sheet_H030SG.pdf"]}], "sources": ["Spec_Sheet_H030SG.pdf"]}
        ]
    }]
    draft_xlsx("Sourced Sheet", sheets, str(out_path))
    wb = openpyxl.load_workbook(out_path)
    ws = wb.active
    val1 = ws.cell(row=5, column=1).value
    val2 = ws.cell(row=5, column=2).value
    fill1 = ws.cell(row=5, column=1).fill.start_color.rgb if ws.cell(row=5, column=1).fill else None
    comment1 = ws.cell(row=5, column=1).comment.text if ws.cell(row=5, column=1).comment else ""
    print(f"Cell (5,1): val='{val1}', fill='{fill1}', comment='{comment1}'")
    print(f"Cell (5,2): val='{val2}'")
    passed = val1 == "H030SG" and val2 == "0.905" and "Sources:" in comment1
    print(f"RESULT 6: {'PASS' if passed else 'FAIL'}")
    return passed

def test_7_refuse_path(tmp_path_str="storage/outputs/refuse_test.jsonl"):
    print("\n--- VERIFICATION 7: Refuse Path ---")
    gate = ApprovalGate(requests_file=tmp_path_str)
    req = gate.request("draft_xlsx", {"title": "T", "sheets": [{"headers":["A"],"rows":[["B"]]}], "output_path": "storage/outputs/never_written.xlsx"}, "Effect T")
    refused_req = gate.refuse(req.request_id, refused_by="operator", reason="User cancelled action")
    print(f"Refused request state: {refused_req.state}")
    file_exists = Path("storage/outputs/never_written.xlsx").exists()
    passed = refused_req.state == ApprovalState.REFUSED and not file_exists
    print(f"RESULT 7: {'PASS' if passed else 'FAIL'}")
    return passed

def test_8_classification_regression():
    print("\n--- VERIFICATION 8: Classification Regression ---")
    q1 = "What is the average MFI for Homopolymer H030SG?"
    dec1 = decide_path(q1)
    print(f"Question 1: '{q1}' -> Path: {dec1.path} ({dec1.reason})")

    q2 = "Set HCU feed rate to 115%"
    is_action = is_action_approval_request(q2)
    cat2 = classify_action_request(q2)
    print(f"Question 2: '{q2}' -> is_action: {is_action}, cat: {cat2}")
    
    passed = dec1.path == "direct" and is_action and cat2 == "DCS_SETPOINT_WRITE"
    print(f"RESULT 8: {'PASS' if passed else 'FAIL'}")
    return passed

def test_9_git_diff_check():
    print("\n--- VERIFICATION 9: Git Diff Graph.py Check ---")
    import subprocess
    res = subprocess.run(["git", "diff", "backend/orchestrator/graph.py"], capture_output=True, text=True)
    diff_output = res.stdout.strip()
    print(f"git diff backend/orchestrator/graph.py output length: {len(diff_output)}")
    passed = len(diff_output) == 0
    print(f"RESULT 9: {'PASS' if passed else 'FAIL'}")
    return passed

def main():
    print("===============================================================================")
    print("RUNNING ALL 9 VERIFICATION PLAN CHECKS")
    print("===============================================================================")
    
    r1, time1, events1 = test_1_timeout_fix()
    r2, res2 = test_2_tool_selection()
    r3, tool3 = test_3_disambiguation()
    r4, eff4 = test_4_approval_modal_effect()
    r5, cells5 = test_5_partial_generation_inspection()
    r6 = test_6_sourced_path()
    r7 = test_7_refuse_path()
    r8 = test_8_classification_regression()
    r9 = test_9_git_diff_check()
    
    summary = [
        ("1. Timeout Fix", r1),
        ("2. Tool Selection Reliability", r2),
        ("3. Disambiguation (docx vs xlsx)", r3),
        ("4. Approval Modal Effect Description", r4),
        ("5. Partial Generation & Empty UNSOURCED Cells", r5),
        ("6. Sourced Path Works", r6),
        ("7. Refuse Path Works", r7),
        ("8. Classification Regression Check", r8),
        ("9. Graph.py Untouched Check", r9),
    ]
    
    print("\n===============================================================================")
    print("VERIFICATION SUMMARY TABLE")
    print("===============================================================================")
    all_pass = True
    for name, p in summary:
        status = "PASS" if p else "FAIL"
        print(f"{name:<45} | {status}")
        if not p:
            all_pass = False
    print("===============================================================================")
    print(f"OVERALL STATUS: {'ALL PASSED' if all_pass else 'SOME FAILED'}")

if __name__ == "__main__":
    main()
