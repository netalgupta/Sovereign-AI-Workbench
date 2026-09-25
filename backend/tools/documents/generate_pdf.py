"""PDF drafting & export — TOOLS.md row 40a (🟡), FRONTEND.md §3.7 / Kanishka.md.

Produces formatted, standalone PDF reports from titled sections and their
citations.

THIS TOOL WRITES A FILE, SO IT IS GATED. `requires_approval=True` ensures the approval
gate (backend/audit/approval_gate.py) prompts the human before execution (CLAUDE.md Hard Constraint #4).

SAFETY & PROVENANCE CONSTRAINTS:
- Citations are structural: every section says where it came from.
- Unsourced claims are visibly tagged with an UNSOURCED badge in the PDF itself.
- Vision estimates carry an explicit ESTIMATE badge.

WHY THIS IS TYPESET, NOT DRAWN. The first version placed text with
PyMuPDF at computed coordinates, and three things were wrong with that:
  * a section's height was GUESSED from its length (len(body) // 75), so
    sections overlapped or left gaps;
  * text longer than the space left on a page was re-inserted on one new
    page, and insert_textbox writes NOTHING when text does not fit -- so a
    section longer than a page was SILENTLY TRUNCATED, which a multi-page
    book chapter always is;
  * titles did not wrap, and the built-in font has no em dash, so dashes
    printed as "?".
reportlab's flowables lay text out the way a typesetter does: paragraphs
wrap and flow across pages, a heading is kept with the text under it,
and a Unicode font (DejaVu, shipped with matplotlib, offline) prints every
character the text contains.
"""

from __future__ import annotations

import html
import os
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.tools.registry import tool


class PdfSection(BaseModel):
    heading: str
    body: str
    sources: list[str] = []
    contains_estimate: bool = False
    # A short provenance note shown under the section, e.g. "Pages 17-69 of
    # the source". When every section shares one source, the source itself
    # is printed once at the end instead of after every section.
    note: str = ""


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


def _org() -> str:
    """Whose name goes on the file: the deployment, not the subject."""
    return os.environ.get("WORKBENCH_ORG", "MRPL").strip() or "MRPL"


_FONTS_READY = False


def _fonts() -> tuple[str, str]:
    """(regular, bold) font names: DejaVu when available, Helvetica otherwise."""
    global _FONTS_READY
    try:
        import matplotlib
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        if not _FONTS_READY:
            base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
            pdfmetrics.registerFont(TTFont("DejaVu", str(base / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(base / "DejaVuSans-Bold.ttf")))
            _FONTS_READY = True
        return "DejaVu", "DejaVu-Bold"
    except Exception:  # noqa: BLE001 - Helvetica still renders; dashes may not
        return "Helvetica", "Helvetica-Bold"


def _paragraphs(text: str) -> list[str]:
    """Body text as paragraphs: split on blank lines, whitespace normalised."""
    parts = [" ".join(p.split()) for p in (text or "").replace("\r", "").split("\n\n")]
    return [p for p in parts if p]


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
    subtitle: str = "",
) -> dict[str, Any]:
    """Generate a sovereign, publication-ready PDF document from structured sections.

    `subtitle` is the one line of context under the title, as draft_docx
    takes. It was missing here, so an approved PDF failed at execution with
    "generate_pdf does not take ['subtitle']" -- the operator had approved
    a document that could not be written.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    parsed = [PdfSection.model_validate(s) for s in sections]
    if not output_path.lower().endswith(".pdf"):
        raise ValueError(f"Output path must end in .pdf, got: {output_path!r}")
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    regular, bold = _fonts()
    ink, muted, accent = colors.HexColor("#1F2933"), colors.HexColor("#6B7785"), colors.HexColor("#0E5E7E")
    styles = {
        "title": ParagraphStyle("title", fontName=bold, fontSize=21, leading=26,
                                textColor=colors.HexColor("#0B1F33"), spaceAfter=6, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("subtitle", fontName=regular, fontSize=12, leading=16, textColor=accent,
                                   spaceAfter=4),
        "meta": ParagraphStyle("meta", fontName=regular, fontSize=8.5, leading=12, textColor=muted, spaceAfter=14),
        "toc_head": ParagraphStyle("toc_head", fontName=bold, fontSize=10, leading=14, textColor=ink,
                                   spaceBefore=4, spaceAfter=4),
        "toc": ParagraphStyle("toc", fontName=regular, fontSize=9.5, leading=14, textColor=ink, leftIndent=8),
        "h": ParagraphStyle("h", fontName=bold, fontSize=13.5, leading=18, textColor=colors.HexColor("#0B1F33"),
                            spaceBefore=16, spaceAfter=6),
        "body": ParagraphStyle("body", fontName=regular, fontSize=10.3, leading=15.2, textColor=ink,
                               spaceAfter=7),
        "note": ParagraphStyle("note", fontName=regular, fontSize=8, leading=11, textColor=muted, spaceAfter=4),
        "badge": ParagraphStyle("badge", fontName=bold, fontSize=7.5, leading=10,
                                textColor=colors.HexColor("#8A4B08")),
    }

    def para(text: str, style: str) -> Paragraph:
        return Paragraph(html.escape(text), styles[style])

    def badge(label: str) -> Table:
        t = Table([[para(label, "badge")]], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF1DC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D98E2B")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    all_sources = sorted({src for s in parsed for src in s.sources})
    shared_source = len(all_sources) == 1 and all(s.sources == all_sources for s in parsed)

    story: list = [para(title, "title")]
    if subtitle:
        story.append(para(subtitle, "subtitle"))
    story.append(para(f"Drafted {date.today().isoformat()} by the {_org()} Sovereign Workbench, offline. "
                      "Every section names where it came from.", "meta"))

    # A contents list once there is enough to navigate.
    numbered = len(parsed) >= 4
    if numbered:
        story.append(para("Contents", "toc_head"))
        for i, sec in enumerate(parsed, 1):
            story.append(para(f"{i}.  {sec.heading}", "toc"))
        story.append(PageBreak())

    for i, sec in enumerate(parsed, 1):
        heading = f"{i}.  {sec.heading}" if numbered else sec.heading
        opening: list = [para(heading, "h")]
        if not sec.sources:
            opening += [badge("UNSOURCED SECTION: no source document was cited"), Spacer(1, 4)]
        if sec.contains_estimate:
            opening += [badge("CONTAINS A VISION-MODEL ESTIMATE, not a measured value"), Spacer(1, 4)]
        body = _paragraphs(sec.body) or [""]
        # The heading is kept with its first paragraph, so it never sits alone
        # at the foot of a page.
        story.append(KeepTogether(opening + [para(body[0], "body")]))
        story.extend(para(p, "body") for p in body[1:])
        note_parts = [sec.note] if sec.note else []
        if not shared_source:
            note_parts.append("Sources: " + ("; ".join(sec.sources) if sec.sources
                                             else "none (untraceable claim)"))
        if note_parts:
            story.append(para(" | ".join(note_parts), "note"))

    if shared_source:
        story += [Spacer(1, 10), para(f"Source: {all_sources[0]}", "note")]

    # Page furniture, and "Page N of M": the total is only known after
    # layout, so every page is held back and numbered when the canvas saves.
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._held: list = []

        def showPage(self):  # noqa: N802 - reportlab API
            self._held.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._held)
            for state in self._held:
                self.__dict__.update(state)
                self.setFont(regular, 7.5)
                self.setFillColor(muted)
                self.drawString(20 * mm, 12 * mm, f"{_org()} Sovereign Workbench  ·  offline publication")
                self.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {self._pageNumber} of {total}")
                self.setStrokeColor(colors.HexColor("#D9E0E6"))
                self.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

    doc = SimpleDocTemplate(str(out_file), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=22 * mm, title=title, author=f"{_org()} Workbench")
    doc.build(story, canvasmaker=NumberedCanvas)

    import fitz  # PyMuPDF, only to count the pages actually written

    with fitz.open(str(out_file)) as written:
        page_count = written.page_count

    result = DraftedPdf(
        file_path=str(out_file),
        title=title,
        page_count=page_count,
        section_count=len(parsed),
        total_sources=sum(len(s.sources) for s in parsed),
        unsourced_sections=[s.heading for s in parsed if not s.sources],
        contains_estimates=any(s.contains_estimate for s in parsed),
        byte_size=out_file.stat().st_size,
    )
    return result.model_dump()
