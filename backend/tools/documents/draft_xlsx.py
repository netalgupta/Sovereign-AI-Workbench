from __future__ import annotations

"""XLSX drafting — TOOLS.md row 39 (🔴), FR-9 / FR-12.

Outputs structured Excel spreadsheets grounded in the corpus, with structural
citations, UNSOURCED markers, vision estimate warnings, and live formulas.

THIS TOOL WRITES A FILE, SO IT IS GATED. `requires_approval=True` on its
registration means the registry's dispatcher refuses to run it without an
approval token obtained through backend/audit/approval_gate.py — CLAUDE.md
hard constraint #4, NFR-6.

CITATIONS ARE STRUCTURAL, NOT DECORATIVE. Every row/cell carries the sources
it was drawn from in a dedicated Sources column and cell comments. Rows/cells
without sources are rendered with an explicit UNSOURCED marker (amber fill).

ESTIMATES ARE MARKED IN THE SPREADSHEET ITSELF. If any data rests on a
vision-model chart reading or scan, that cell is flagged with an orange fill,
an [ESTIMATE] label, and an Excel comment.

FORMULAS ARE LIVE. Any in-sheet calculation (sums, averages, comparisons) is
written as a real Excel formula (e.g., `=AVERAGE(B4:B6)`) rather than a static
Python value, so Excel evaluates it dynamically.
"""

from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.registry import tool


class SpreadsheetCell(BaseModel):
    value: Any
    sources: list[str] = Field(default_factory=list)
    is_unsourced: bool = False
    contains_estimate: bool = False
    comment: str | None = None


class SpreadsheetRow(BaseModel):
    cells: list[Any] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    is_unsourced: bool = False
    contains_estimate: bool = False


class SpreadsheetSheet(BaseModel):
    sheet_name: str
    headers: list[str] = Field(default_factory=list)
    rows: list[Any] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    contains_estimate: bool = False


class DraftedSpreadsheet(BaseModel):
    file_path: str
    title: str
    sheet_count: int
    row_count: int
    total_sources: int
    unsourced_count: int
    contains_estimates: bool
    has_formulas: bool
    byte_size: int


def describe_effect(
    title: str, sheets: list[dict], output_path: str
) -> str:
    """Plain-language description of what XLSX drafting will do, for the
    approval prompt.
    """
    total_rows = 0
    total_data_cells = 0
    unsourced_cells = 0
    total_sources = 0
    has_estimates = False
    has_formulas = False

    for s in sheets:
        headers = list(s.get("headers") or [])
        rows = s.get("rows") or []
        total_rows += len(rows)

        sheet_sources = list(s.get("sources") or [])
        total_sources += len(sheet_sources)
        if s.get("contains_estimate"):
            has_estimates = True

        # Sources column check
        has_sources_col = any("source" in h.lower() or "citation" in h.lower() for h in headers)
        data_col_count = len(headers) if has_sources_col else max(len(headers), 1)

        for r in rows:
            row_srcs = list(sheet_sources)
            row_unsourced = False
            cells = []

            if isinstance(r, dict):
                cells = list(r.get("cells") or [])
                r_srcs = r.get("sources") or []
                if r.get("is_unsourced"):
                    row_unsourced = True
                    row_srcs = []
                else:
                    if r_srcs:
                        row_srcs.extend(r_srcs)
                        total_sources += len(r_srcs)
                    if not row_srcs:
                        row_unsourced = True
                if r.get("contains_estimate"):
                    has_estimates = True
            elif isinstance(r, (list, tuple)):
                cells = list(r)
                if not row_srcs:
                    row_unsourced = True
            else:
                cells = [r]
                if not row_srcs:
                    row_unsourced = True

            # Limit data cells iteration to data columns
            num_data_cols = min(len(cells), data_col_count)
            if num_data_cols == 0:
                num_data_cols = data_col_count

            for idx in range(data_col_count):
                total_data_cells += 1
                c = cells[idx] if idx < len(cells) else None

                cell_val = None
                cell_srcs = []
                c_unsourced = row_unsourced

                if isinstance(c, dict):
                    cell_val = c.get("value")
                    cell_srcs = c.get("sources") or []
                    if cell_srcs:
                        total_sources += len(cell_srcs)
                        c_unsourced = False
                    if c.get("is_unsourced"):
                        c_unsourced = True
                    if c.get("contains_estimate"):
                        has_estimates = True
                else:
                    cell_val = c
                    if row_srcs:
                        c_unsourced = False

                if isinstance(cell_val, str) and cell_val.startswith("="):
                    has_formulas = True

                if c_unsourced or cell_val is None or (isinstance(cell_val, str) and (not cell_val.strip() or cell_val.strip() == "UNSOURCED")):
                    unsourced_cells += 1

    sourced_cells = max(0, total_data_cells - unsourced_cells)

    lines = [
        f'Create the Excel spreadsheet "{title}" at {output_path} — {len(sheets)} sheet(s), {total_rows} row(s).',
    ]
    if total_data_cells > 0:
        if unsourced_cells > 0:
            lines.append(
                f"{sourced_cells} of {total_data_cells} data cells are sourced. "
                f"{unsourced_cells} cells could not be sourced and will be marked UNSOURCED and left empty."
            )
        else:
            lines.append(f"All {total_data_cells} data cells are sourced from cited documents.")

    if has_estimates:
        lines.append("WARNING: contains vision-model ESTIMATE(S), not measured figures.")
    if has_formulas:
        lines.append("Includes live Excel formulas for calculations.")
    if Path(output_path).exists():
        lines.append(f"WARNING: {output_path} already exists and will be OVERWRITTEN.")

    return " ".join(lines)


@tool(
    name="draft_xlsx",
    description=(
        "Draft an Excel (.xlsx) spreadsheet from titled sheets, headers, data rows, "
        "and source citations. Supports live Excel formulas (e.g. =SUM(), =AVERAGE()), "
        "structural citations, UNSOURCED markers, and vision estimate warnings. "
        "WRITES A FILE, so it requires human approval before it runs. "
        "Use when the user asks for a spreadsheet, Excel file, comparison table, "
        "or data matrix."
    ),
    category="documents",
    priority="🔴",
    requires_approval=True,
    tools_md_row=39,
)
def draft_xlsx(
    title: str,
    sheets: list[dict],
    output_path: str,
    subtitle: str = "",
) -> DraftedSpreadsheet:
    """Write an .xlsx file from structured sheets.

    Args:
        title: spreadsheet title / workbook heading.
        sheets: list of sheet dictionaries:
            {
              "sheet_name": str,
              "headers": list[str],
              "rows": list[list[Any] | dict],
              "sources": list[str],
              "contains_estimate": bool
            }
        output_path: file path ending in .xlsx (e.g., storage/outputs/report.xlsx).
        subtitle: optional description or unit tag.

    Raises:
        ValueError: if sheets list is empty or output_path does not end in .xlsx.
    """
    import openpyxl
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if not sheets:
        raise ValueError("Cannot draft a spreadsheet with no sheets.")
    destination = Path(output_path)
    if destination.suffix.lower() != ".xlsx":
        raise ValueError(
            f"Output path must end in .xlsx; got {destination.suffix!r}. An Excel file "
            "under another extension will not open in user tools."
        )

    # Pre-calculate cell sourcing stats across all sheets
    total_data_cells_all = 0
    unsourced_data_cells_all = 0
    for s in sheets:
        headers_cnt = len(s.get("headers") or [])
        has_src_col = any("source" in h.lower() or "citation" in h.lower() for h in (s.get("headers") or []))
        data_col_cnt = headers_cnt if has_src_col else max(headers_cnt, 1)
        s_srcs = s.get("sources") or []

        for r in (s.get("rows") or []):
            r_unsourced = False
            r_srcs = list(s_srcs)
            cells = []
            if isinstance(r, dict):
                cells = list(r.get("cells") or [])
                r_srcs.extend(r.get("sources") or [])
                if r.get("is_unsourced") or not r_srcs:
                    r_unsourced = True
            elif isinstance(r, (list, tuple)):
                cells = list(r)
                if not r_srcs:
                    r_unsourced = True

            for idx in range(data_col_cnt):
                total_data_cells_all += 1
                c = cells[idx] if idx < len(cells) else None
                c_unsourced = r_unsourced
                cell_val = None
                if isinstance(c, dict):
                    cell_val = c.get("value")
                    if c.get("sources"):
                        c_unsourced = False
                    if c.get("is_unsourced"):
                        c_unsourced = True
                else:
                    cell_val = c
                    if r_srcs:
                        c_unsourced = False

                if c_unsourced or cell_val is None or (isinstance(cell_val, str) and (not cell_val.strip() or cell_val.strip() == "UNSOURCED")):
                    unsourced_data_cells_all += 1

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="4B5563")
    stamp_font = Font(name="Calibri", size=9, italic=True, color="6B7280")

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")

    bold_font = Font(name="Calibri", size=11, bold=True)
    normal_font = Font(name="Calibri", size=11)

    unsourced_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Light amber
    unsourced_font = Font(name="Calibri", size=11, bold=True, color="B45309")

    estimate_fill = PatternFill(start_color="FFEDD5", end_color="FFEDD5", fill_type="solid")   # Light orange
    estimate_font = Font(name="Calibri", size=11, bold=True, color="C2410C")

    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    total_data_rows = 0
    total_sources = 0
    unsourced_count = 0
    contains_estimates = False
    has_formulas = False

    for s_idx, s_data in enumerate(sheets):
        sheet_name = s_data.get("sheet_name") or f"Sheet{s_idx + 1}"
        ws = wb.create_sheet(title=sheet_name[:31])

        # Row 1: Title
        ws.cell(row=1, column=1, value=title).font = title_font

        # Row 2: Subtitle / Provenance stamp with cell sourcing counts
        if unsourced_data_cells_all > 0 and total_data_cells_all > 0:
            sourcing_stamp = f"{unsourced_data_cells_all} of {total_data_cells_all} data cells could not be sourced from the provided corpus and are marked UNSOURCED."
        elif total_data_cells_all > 0:
            sourcing_stamp = f"All {total_data_cells_all} data cells sourced from cited documents."
        else:
            sourcing_stamp = "Drafted from cited sources."

        stamp_text = (
            f"{subtitle} — " if subtitle else ""
        ) + f"Drafted by Sovereign Workbench on {date.today().isoformat()}. {sourcing_stamp} Review before circulation."
        ws.cell(row=2, column=1, value=stamp_text).font = stamp_font

        # Row 3: Blank spacing
        start_row = 4

        headers = list(s_data.get("headers") or [])
        sheet_sources = list(s_data.get("sources") or [])
        if sheet_sources:
            total_sources += len(sheet_sources)
        if s_data.get("contains_estimate"):
            contains_estimates = True

        # Append "Sources / Citations" column header if not present
        has_sources_col = any("source" in h.lower() or "citation" in h.lower() for h in headers)
        if not has_sources_col and headers:
            headers.append("Sources / Citations")

        # Write Headers (Row 4)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        ws.row_dimensions[start_row].height = 26

        # Write Data Rows (Row 5+)
        current_row = start_row + 1
        raw_rows = s_data.get("rows") or []

        for r_item in raw_rows:
            total_data_rows += 1
            row_sources = list(sheet_sources)
            row_is_unsourced = False
            row_is_estimate = s_data.get("contains_estimate", False)

            if isinstance(r_item, dict):
                cell_values = list(r_item.get("cells") or [])
                r_srcs = r_item.get("sources") or []
                if r_item.get("is_unsourced"):
                    row_is_unsourced = True
                    row_sources = []
                else:
                    if r_srcs:
                        row_sources.extend(r_srcs)
                        total_sources += len(r_srcs)
                    if not row_sources:
                        row_is_unsourced = True
                if r_item.get("contains_estimate"):
                    row_is_estimate = True
                    contains_estimates = True
            elif isinstance(r_item, (list, tuple)):
                cell_values = list(r_item)
                if not row_sources:
                    row_is_unsourced = True
            else:
                cell_values = [str(r_item)]
                if not row_sources:
                    row_is_unsourced = True

            # If Sources column was auto-appended, ensure values match
            if not has_sources_col and len(cell_values) < len(headers):
                if row_sources and not row_is_unsourced:
                    cell_values.append("; ".join(sorted(set(row_sources))))
                else:
                    cell_values.append("UNSOURCED")

            for col_idx, raw_c in enumerate(cell_values, start=1):
                cell_val = raw_c
                cell_srcs = []
                c_unsourced = row_is_unsourced
                c_estimate = row_is_estimate
                c_comment = None

                if isinstance(raw_c, dict):
                    cell_val = raw_c.get("value")
                    cell_srcs = raw_c.get("sources") or []
                    if cell_srcs:
                        total_sources += len(cell_srcs)
                        c_unsourced = False
                    if raw_c.get("is_unsourced"):
                        c_unsourced = True
                    if raw_c.get("contains_estimate"):
                        c_estimate = True
                        contains_estimates = True
                    c_comment = raw_c.get("comment")

                is_sources_col_cell = (not has_sources_col and col_idx == len(headers)) or (has_sources_col and "source" in headers[col_idx-1].lower())

                cell = ws.cell(row=current_row, column=col_idx)

                # Unsourced data cell constraint: leave cell value EMPTY (empty string) and apply amber UNSOURCED formatting.
                if c_unsourced and not is_sources_col_cell:
                    cell.value = ""
                elif isinstance(cell_val, str) and cell_val.startswith("="):
                    has_formulas = True
                    cell.value = cell_val
                else:
                    cell.value = cell_val

                cell.font = normal_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

                # Formatting flags
                if c_estimate:
                    cell.fill = estimate_fill
                    cell.font = estimate_font
                    comment_msg = c_comment or "ESTIMATE — value estimated by a vision/OCR model from a chart image. Verify against raw data."
                    cell.comment = Comment(comment_msg, "Sovereign Workbench")
                elif c_unsourced or (isinstance(cell_val, str) and cell_val.strip() == "UNSOURCED"):
                    cell.fill = unsourced_fill
                    cell.font = unsourced_font
                    if is_sources_col_cell:
                        unsourced_count += 1
                        cell.value = "UNSOURCED"
                    else:
                        cell.value = ""
                    comment_msg = c_comment or "UNSOURCED — this value is not traceable to a source document."
                    cell.comment = Comment(comment_msg, "Sovereign Workbench")

                if cell_srcs and not cell.comment:
                    cell.comment = Comment(f"Sources: {'; '.join(cell_srcs)}", "Sovereign Workbench")

            ws.row_dimensions[current_row].height = 20
            current_row += 1

        # Auto-fit column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)

    return DraftedSpreadsheet(
        file_path=str(destination),
        title=title,
        sheet_count=len(wb.sheetnames),
        row_count=total_data_rows,
        total_sources=total_sources,
        unsourced_count=unsourced_count,
        contains_estimates=contains_estimates,
        has_formulas=has_formulas,
        byte_size=destination.stat().st_size,
    )

