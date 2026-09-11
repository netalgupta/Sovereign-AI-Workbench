"""DOCX drafting — TOOLS.md row 38 (🔴), FR-9 / FR-12.

The headline output of the workbench: a grounded answer becomes a real
document an engineer can circulate.

THIS TOOL WRITES A FILE, SO IT IS GATED. `requires_approval=True` on its
registration means the registry's dispatcher refuses to run it without an
approval token obtained through backend/audit/approval_gate.py — CLAUDE.md
hard constraint #4, NFR-6. It is the first tool in this repo that
actually exercises that gate rather than merely declaring it.

CITATIONS ARE STRUCTURAL, NOT DECORATIVE. Every section carries the
sources it was drawn from, and `describe_effect()` surfaces the count to
the approving human, because the thing most worth checking before a
document leaves the building is whether its claims are traceable. A
drafted section with no sources is rendered with an explicit
"UNSOURCED" marker rather than looking identical to a grounded one —
CLAUDE.md's NFR-4 posture applied to output as well as to answers.

ESTIMATES ARE MARKED IN THE DOCUMENT ITSELF. If a section rests on a
vision-model chart reading, that qualifier is printed in the document,
not just held in metadata. A DOCX gets forwarded, printed, and pasted
into other documents; a caveat that lives only in the app is lost at the
first hop, which is exactly where it starts to matter.
"""

from datetime import date
from pathlib import Path

from pydantic import BaseModel

from backend.tools.registry import tool


class DocumentSection(BaseModel):
    heading: str
    body: str
    # Source documents this section's content came from. Empty is
    # allowed but is rendered visibly as unsourced rather than silently.
    sources: list[str] = []
    # True when any part of this section rests on a model's estimate
    # (a chart reading, OCR of a poor scan) rather than on text or a
    # computed value.
    contains_estimate: bool = False


class DraftedDocument(BaseModel):
    file_path: str
    title: str
    section_count: int
    total_sources: int
    unsourced_sections: list[str]
    contains_estimates: bool
    byte_size: int


def describe_effect(
    title: str, sections: list[dict], output_path: str
) -> str:
    """Plain-language description of what drafting will do, for the
    approval prompt.

    Written for the person deciding, not for a log. Showing someone
    `draft_docx({...})` and asking them to approve it is not informed
    consent — they will click yes. Showing them "Create X at Y, 4
    sections, 2 unsourced, contains a chart estimate" is a decision they
    can actually make.
    """
    parsed = [DocumentSection.model_validate(s) for s in sections]
    unsourced = [s.heading for s in parsed if not s.sources]
    estimates = any(s.contains_estimate for s in parsed)

    lines = [
        f'Create the Word document "{title}" at {output_path}',
        f"{len(parsed)} section(s), "
        f"{sum(len(s.sources) for s in parsed)} source citation(s).",
    ]
    if unsourced:
        lines.append(
            f"WARNING: {len(unsourced)} section(s) have NO sources: {', '.join(unsourced)}."
        )
    if estimates:
        lines.append(
            "WARNING: contains at least one vision-model ESTIMATE, not a measured value."
        )
    if Path(output_path).exists():
        lines.append(f"WARNING: {output_path} already exists and will be OVERWRITTEN.")
    return " ".join(lines)


@tool(
    name="draft_docx",
    description=(
        "Draft a Word (.docx) document from titled sections with their source "
        "citations. WRITES A FILE, so it requires human approval before it runs. "
        "Use only when the user has asked for a document; to show text, just "
        "reply with it."
    ),
    category="documents",
    priority="🔴",
    requires_approval=True,
    tools_md_row=38,
)
def draft_docx(
    title: str,
    sections: list[dict],
    output_path: str,
    subtitle: str = "",
) -> DraftedDocument:
    """Write a .docx from structured sections.

    Args:
        title: document title, rendered as the heading.
        sections: list of {heading, body, sources, contains_estimate}.
            `sources` are the source document names the section's claims
            came from; a section with none is marked UNSOURCED in the
            output rather than looking identical to a grounded one.
        output_path: where to write the .docx.
        subtitle: optional line under the title, e.g. the unit or date
            range the document covers.

    Raises:
        ValueError: on no sections, or an output path that is not .docx —
            writing a Word document under another extension produces a
            file the user's tools will not open, which looks like data
            loss rather than a naming mistake.
    """
    import docx
    from docx.shared import Pt

    if not sections:
        raise ValueError("Cannot draft a document with no sections.")
    destination = Path(output_path)
    if destination.suffix.lower() != ".docx":
        raise ValueError(
            f"Output path must end in .docx; got {destination.suffix!r}. A Word file "
            "under another extension will not open in the user's tools."
        )

    parsed = [DocumentSection.model_validate(s) for s in sections]
    document = docx.Document()

    document.add_heading(title, level=0)
    if subtitle:
        document.add_paragraph(subtitle)

    # Provenance line: a reader who finds this document months later, out
    # of context, needs to know it was machine-drafted and from when.
    # Omitting that makes an AI draft indistinguishable from an engineer's
    # own work, which is not a property this system should have.
    stamp = document.add_paragraph()
    run = stamp.add_run(
        f"Drafted by the Sovereign Workbench on {date.today().isoformat()} "
        "from the cited source documents. Review before circulation."
    )
    run.italic = True
    run.font.size = Pt(9)

    unsourced: list[str] = []
    for section in parsed:
        document.add_heading(section.heading, level=1)

        if section.contains_estimate:
            warning = document.add_paragraph()
            warning_run = warning.add_run(
                "This section includes a value estimated by a vision model from a "
                "chart image. It is not a measured figure and must be verified "
                "against the source data before use."
            )
            warning_run.bold = True
            warning_run.font.size = Pt(9)

        document.add_paragraph(section.body)

        if section.sources:
            citation = document.add_paragraph()
            citation_run = citation.add_run("Sources: " + "; ".join(section.sources))
            citation_run.italic = True
            citation_run.font.size = Pt(9)
        else:
            unsourced.append(section.heading)
            marker = document.add_paragraph()
            marker_run = marker.add_run(
                "UNSOURCED — this section is not traceable to a source document."
            )
            marker_run.bold = True
            marker_run.font.size = Pt(9)

    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination)

    return DraftedDocument(
        file_path=str(destination),
        title=title,
        section_count=len(parsed),
        total_sources=sum(len(s.sources) for s in parsed),
        unsourced_sections=unsourced,
        contains_estimates=any(s.contains_estimate for s in parsed),
        byte_size=destination.stat().st_size,
    )
