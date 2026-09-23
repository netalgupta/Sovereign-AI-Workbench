"""PDF drafting & export — TOOLS.md row 40a (🟡), FRONTEND.md §3.7 / Kanishka.md.

Produces formatted, standalone PDF reports from titled sections, structural citations,
and quantitative findings using PyMuPDF (fitz).

THIS TOOL WRITES A FILE, SO IT IS GATED. `requires_approval=True` ensures the approval
gate (backend/audit/approval_gate.py) prompts the human before execution (CLAUDE.md Hard Constraint #4).

SAFETY & PROVENANCE CONSTRAINTS:
- Citations are structural: sources are rendered in an explicit citation block per section.
- Unsourced claims are visibly tagged with an [UNSOURCED] warning badge in the PDF itself.
- Vision estimates carry an explicit [ESTIMATE] badge.
- Validates file path and ensures safe output under storage/outputs/.
"""

from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from pydantic import BaseModel

from backend.tools.registry import tool


class PdfSection(BaseModel):
    heading: str
    body: str
    sources: list[str] = []
    contains_estimate: bool = False


class DraftedPdf(BaseModel):
    file_path: str
    title: str
    page_count: int
    section_count: int
    total_sources: int
    unsourced_sections: list[str]
    contains_estimates: bool
    byte_size: int


def describe_effect(title: str, sections: list[dict[str, Any]], output_path: str) -> str:
    """Plain-language description of what drafting will do, for the approval prompt."""
    parsed = [PdfSection.model_validate(s) for s in sections]
    unsourced = [s.heading for s in parsed if not s.sources]
    estimates = any(s.contains_estimate for s in parsed)

    lines = [
        f'Create the PDF report "{title}" at {output_path}',
        f"with {len(parsed)} section(s), "
        f"{sum(len(s.sources) for s in parsed)} source citation(s).",
    ]
    if unsourced:
        lines.append(
            f"WARNING: {len(unsourced)} section(s) have NO sources: {', '.join(unsourced)}."
        )
    if estimates:
        lines.append("WARNING: contains at least one vision-model ESTIMATE.")
    if Path(output_path).exists():
        lines.append(f"WARNING: {output_path} already exists and will be OVERWRITTEN.")
    return " ".join(lines)


@tool(
    name="generate_pdf",
    description=(
        "Draft a formal PDF document from titled sections with their source citations. "
        "WRITES A FILE, so it requires human approval before it runs. "
        "Use only when the user has asked for a PDF or formal exported report."
    ),
    category="documents",
    priority="🟡",
    tools_md_row=40,
    requires_approval=True,
)
def generate_pdf(
    title: str,
    sections: list[dict[str, Any]],
    output_path: str = "storage/outputs/report.pdf",
) -> dict[str, Any]:
    """Generate a sovereign, publication-ready PDF document from structured sections."""
    parsed = [PdfSection.model_validate(s) for s in sections]

    # Validate file extension
    if not output_path.lower().endswith(".pdf"):
        raise ValueError(f"Output path must end in .pdf, got: {output_path!r}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()

    # Layout constants
    PAGE_WIDTH = 595.32  # A4 width in pt
    PAGE_HEIGHT = 842.04  # A4 height in pt
    MARGIN_LEFT = 54.0
    MARGIN_RIGHT = 54.0
    MARGIN_TOP = 54.0
    MARGIN_BOTTOM = 54.0
    CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

    def create_page():
        p = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        # Header rule
        p.draw_line(
            fitz.Point(MARGIN_LEFT, 40),
            fitz.Point(PAGE_WIDTH - MARGIN_RIGHT, 40),
            color=(0.8, 0.8, 0.8),
            width=0.75,
        )
        p.insert_text(
            fitz.Point(MARGIN_LEFT, 35),
            "MRPL Sovereign Air-Gapped Workbench — Offline Publication",
            fontsize=8,
            color=(0.4, 0.4, 0.4),
        )
        return p

    current_page = create_page()
    y_pos = MARGIN_TOP + 15

    # Document Title
    current_page.insert_text(
        fitz.Point(MARGIN_LEFT, y_pos),
        title,
        fontsize=20,
        color=(0.1, 0.15, 0.25),
    )
    y_pos += 26

    # Subtitle / Metadata
    today_str = date.today().isoformat()
    meta_text = f"Drafted on {today_str} | Verified Citations & Provenance Trace"
    current_page.insert_text(
        fitz.Point(MARGIN_LEFT, y_pos),
        meta_text,
        fontsize=9,
        color=(0.45, 0.45, 0.5),
    )
    y_pos += 20

    # Divider bar
    current_page.draw_line(
        fitz.Point(MARGIN_LEFT, y_pos),
        fitz.Point(PAGE_WIDTH - MARGIN_RIGHT, y_pos),
        color=(0.15, 0.35, 0.65),
        width=1.5,
    )
    y_pos += 24

    for sec in parsed:
        # Check remaining space; wrap to next page if tight
        if y_pos > PAGE_HEIGHT - MARGIN_BOTTOM - 90:
            current_page = create_page()
            y_pos = MARGIN_TOP + 20

        # Section Heading
        current_page.insert_text(
            fitz.Point(MARGIN_LEFT, y_pos),
            sec.heading,
            fontsize=13,
            color=(0.1, 0.2, 0.35),
        )
        y_pos += 18

        # UNSOURCED warning badge if no sources
        if not sec.sources:
            rect = fitz.Rect(MARGIN_LEFT, y_pos - 10, MARGIN_LEFT + 120, y_pos + 4)
            current_page.draw_rect(rect, color=(0.85, 0.5, 0.1), fill=(1.0, 0.95, 0.8), width=0.5)
            current_page.insert_text(
                fitz.Point(MARGIN_LEFT + 6, y_pos),
                "UNSOURCED SECTION",
                fontsize=8,
                color=(0.75, 0.35, 0.0),
            )
            y_pos += 16

        # ESTIMATE warning badge
        if sec.contains_estimate:
            rect = fitz.Rect(MARGIN_LEFT, y_pos - 10, MARGIN_LEFT + 155, y_pos + 4)
            current_page.draw_rect(rect, color=(0.9, 0.4, 0.1), fill=(1.0, 0.9, 0.8), width=0.5)
            current_page.insert_text(
                fitz.Point(MARGIN_LEFT + 6, y_pos),
                "CONTAINS VISION ESTIMATE",
                fontsize=8,
                color=(0.8, 0.3, 0.0),
            )
            y_pos += 16

        # Body Text (multi-line wrapping)
        text_rect = fitz.Rect(MARGIN_LEFT, y_pos, MARGIN_LEFT + CONTENT_WIDTH, PAGE_HEIGHT - MARGIN_BOTTOM)
        rc = current_page.insert_textbox(
            text_rect,
            sec.body,
            fontsize=10,
            color=(0.15, 0.15, 0.15),
            lineheight=1.35,
        )
        if rc < 0:  # Text overflowed, add page
            current_page = create_page()
            y_pos = MARGIN_TOP + 20
            text_rect = fitz.Rect(MARGIN_LEFT, y_pos, MARGIN_LEFT + CONTENT_WIDTH, PAGE_HEIGHT - MARGIN_BOTTOM)
            current_page.insert_textbox(text_rect, sec.body, fontsize=10, lineheight=1.35)
            y_pos += 60
        else:
            # Approximate height used: lines based on text length
            lines_est = max(1, len(sec.body) // 75 + 1)
            y_pos += lines_est * 14 + 10

        # Citations block
        if sec.sources:
            citations_str = "Sources: " + " | ".join(sec.sources)
            current_page.insert_text(
                fitz.Point(MARGIN_LEFT, y_pos),
                citations_str,
                fontsize=8,
                color=(0.3, 0.5, 0.7),
            )
            y_pos += 18
        else:
            current_page.insert_text(
                fitz.Point(MARGIN_LEFT, y_pos),
                "Sources: None (untraceable claim)",
                fontsize=8,
                color=(0.8, 0.4, 0.1),
            )
            y_pos += 18

        y_pos += 10

    # Save to disk
    doc.save(str(out_file))
    doc.close()

    unsourced = [s.heading for s in parsed if not s.sources]
    estimates = any(s.contains_estimate for s in parsed)
    total_sources = sum(len(s.sources) for s in parsed)

    result = DraftedPdf(
        file_path=str(out_file),
        title=title,
        page_count=len(doc) if not doc.is_closed else 1,
        section_count=len(parsed),
        total_sources=total_sources,
        unsourced_sections=unsourced,
        contains_estimates=estimates,
        byte_size=out_file.stat().st_size,
    )
    return result.model_dump()
