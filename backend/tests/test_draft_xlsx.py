"""Tests for draft_xlsx spreadsheet drafting tool — TOOLS.md row 39 (🔴).

Verifies:
1. XLSX drafting generates valid .xlsx files with styled headers, live formulas,
   structural citations, UNSOURCED markers, and vision estimate warnings.
2. Output path extension validation (.xlsx required).
3. Plain-language describe_effect summary for human approval prompts.
4. Approval gate integration (request/approve/execute).
"""

from pathlib import Path

import openpyxl
import pytest

from backend.audit.approval_gate import ApprovalGate
from backend.tools.documents.draft_xlsx import (


    DraftedSpreadsheet,
    describe_effect,
    draft_xlsx,
)


@pytest.fixture(autouse=True)
def _outputs_in_tmp(tmp_path, monkeypatch):
    """Approved writes may only land in OUTPUT_DIR (backend/paths.py); here that is the test's tmp dir."""
    import backend.paths

    monkeypatch.setattr(backend.paths, "OUTPUT_DIR", tmp_path)


def _args(tmp_path: Path) -> dict:
    return {
        "title": "MRPL Polymer Batch Quality & MFI Comparison",
        "subtitle": "Q3 2026 Novolen & Polypropylene QA Audit",
        "output_path": str(tmp_path / "batch_comparison.xlsx"),
        "sheets": [
            {
                "sheet_name": "Batch Comparison",
                "headers": ["Grade / Batch ID", "MFI (g/10min)", "Spec Limit", "Status"],
                "rows": [
                    {
                        "cells": ["Homopolymer H030SG", 3.4, "3.0 - 3.8", '=IF(B5>=3.0, "PASS", "FAIL")'],
                        "sources": ["Novolen_Batch_QA_Report_Aug2026.pdf"],
                    },
                    {
                        "cells": ["Polypropylene P200", 2.2, "3.0 - 3.8", '=IF(B6>=3.0, "PASS", "FAIL")'],
                        "is_unsourced": True,
                    },
                    {
                        "cells": ["Polypropylene P300 (Scanned Diagram)", 3.1, "3.0 - 3.8", '=IF(B7>=3.0, "PASS", "FAIL")'],
                        "sources": ["Pipeline_Incident_Report_Hassan_Segment.pdf"],
                        "contains_estimate": True,
                    },
                    {
                        "cells": ["Average MFI", "=AVERAGE(B5:B7)", "-", "-"],
                        "sources": ["Novolen_Batch_QA_Report_Aug2026.pdf"],
                    },
                ],
                "sources": ["Novolen_Batch_QA_Report_Aug2026.pdf"],
            }
        ],
    }


def test_draft_xlsx_creates_valid_file(tmp_path: Path):
    args = _args(tmp_path)
    result = draft_xlsx(**args)

    assert isinstance(result, DraftedSpreadsheet)
    assert Path(result.file_path).exists()
    assert result.file_path.endswith(".xlsx")
    assert result.byte_size > 0
    assert result.sheet_count == 1
    assert result.row_count == 4
    assert result.total_sources >= 2
    assert result.contains_estimates is True
    assert result.has_formulas is True

    # Open with openpyxl and inspect sheet contents
    wb = openpyxl.load_workbook(result.file_path, data_only=False)
    assert "Batch Comparison" in wb.sheetnames

    ws = wb["Batch Comparison"]

    # Title check
    assert ws.cell(row=1, column=1).value == "MRPL Polymer Batch Quality & MFI Comparison"

    # Header check (row 4)
    assert ws.cell(row=4, column=1).value == "Grade / Batch ID"
    assert ws.cell(row=4, column=2).value == "MFI (g/10min)"
    assert ws.cell(row=4, column=5).value == "Sources / Citations"

    # Row 5 (H030SG)
    assert ws.cell(row=5, column=1).value == "Homopolymer H030SG"
    assert ws.cell(row=5, column=2).value == 3.4
    assert ws.cell(row=5, column=4).value == '=IF(B5>=3.0, "PASS", "FAIL")'

    # Row 6 (UNSOURCED)
    row6_sources_cell = ws.cell(row=6, column=5)
    assert row6_sources_cell.value == "UNSOURCED"
    assert row6_sources_cell.fill.start_color.rgb == "00FEF3C7"

    # Row 7 (Estimate warning)
    row7_name_cell = ws.cell(row=7, column=1)
    assert row7_name_cell.fill.start_color.rgb == "00FFEDD5"
    assert row7_name_cell.comment is not None
    assert "ESTIMATE" in row7_name_cell.comment.text

    # Row 8 (Formula check)
    assert ws.cell(row=8, column=2).value == "=AVERAGE(B5:B7)"


def test_draft_xlsx_refuses_non_xlsx_extension(tmp_path: Path):
    args = _args(tmp_path)
    args["output_path"] = str(tmp_path / "report.docx")

    with pytest.raises(ValueError, match="Output path must end in .xlsx"):
        draft_xlsx(**args)


def test_describe_effect_returns_plain_language_summary(tmp_path: Path):
    args = _args(tmp_path)
    effect = describe_effect(args["title"], args["sheets"], args["output_path"])

    assert 'Create the Excel spreadsheet "MRPL Polymer Batch Quality & MFI Comparison"' in effect
    assert "1 sheet(s)" in effect
    assert "4 row(s)" in effect
    assert "data cells are sourced" in effect
    assert "WARNING: contains vision-model ESTIMATE(S)" in effect
    assert "Includes live Excel formulas" in effect



def test_draft_xlsx_approval_gate_integration(tmp_path: Path):
    args = _args(tmp_path)
    effect = describe_effect(args["title"], args["sheets"], args["output_path"])

    gate = ApprovalGate(requests_file=tmp_path / "requests.jsonl")
    req = gate.request("draft_xlsx", args, effect)

    assert req.tool_name == "draft_xlsx"
    assert req.state.value == "pending"

    app = gate.approve(req.request_id, approved_by="operator")
    assert app.state.value == "approved"
    assert app.token is not None

    exec_res = gate.execute_approved(req.request_id, app.token)
    assert exec_res.file_path == args["output_path"]
    assert Path(exec_res.file_path).exists()
