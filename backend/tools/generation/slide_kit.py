"""slide_kit.py — 19-Mold Presentation Template Engine for MRPL Sovereign Workbench.

Separates "what to say" (LLM structured JSON) from "how it looks" (fixed hand-crafted
layouts in PPTX/MRPL_Template.pptx). Read-and-duplicate only: opens the master template,
duplicates the requested mold layouts, substitutes {{placeholders}}, injects images/tables,
and produces on-brand corporate decks with 0 runtime drawing code.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, Optional, Union

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self) -> dict[str, Any]:
            return self.__dict__
    def Field(default: Any = None, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default

import pptx
from pptx.util import Inches, Pt

# Brand Color Constants (matching graphTheme.js and MRPL industrial identity)
BRAND_AMBER_LIGHT = "#C26A10"
BRAND_AMBER_DARK = "#F59E0B"
BRAND_TEAL_LIGHT = "#12798C"
BRAND_TEAL_DARK = "#06B6D4"
BRAND_SLATE_DARK = "#0F172A"
BRAND_SLATE_MID = "#1E293B"
BRAND_CORAL = "#F43F5E"
BRAND_EMERALD = "#10B981"

# Map of Mold IDs to 0-indexed slide numbers in PPTX/MRPL_Template.pptx
MOLD_INDEX: dict[str, int] = {
    "title_bullets": 0,
    "stat_callout": 1,
    "multi_stat_row": 2,
    "comparison_cards": 3,
    "chart_commentary": 4,
    "process_flow": 5,
    "timeline": 6,
    "quote_highlight": 7,
    "image_caption": 8,
    "safety_alert": 9,
    "table_data": 10,
    "two_column": 11,
    "risk_matrix": 12,
    "org_or_flow_chart": 13,
    "executive_summary": 14,
    "section_divider": 15,
    "agenda": 16,
    "generic_grid": 17,
    "flexible_highlight": 18,
}

# ── Pydantic Mold Schemas ───────────────────────────────────────────────────

class BaseSlide(BaseModel):
    mold_id: str
    title: str = ""
    citations: list[int] = Field(default_factory=list)


class TitleBulletsSlide(BaseSlide):
    mold_id: Literal["title_bullets"] = "title_bullets"
    bullets: list[str] = Field(default_factory=list, max_length=5)


class StatCalloutSlide(BaseSlide):
    mold_id: Literal["stat_callout"] = "stat_callout"
    big_number: str
    label: str
    context_sentence: str = ""


class MultiStatRowSlide(BaseSlide):
    mold_id: Literal["multi_stat_row"] = "multi_stat_row"
    stats: list[dict[str, str]] = Field(default_factory=list, max_length=4)  # [{"value": ..., "label": ...}]


class ComparisonCardsSlide(BaseSlide):
    mold_id: Literal["comparison_cards"] = "comparison_cards"
    cards: list[dict[str, Any]] = Field(default_factory=list, max_length=3)  # [{"title": ..., "points": [...]}]


class ChartCommentarySlide(BaseSlide):
    mold_id: Literal["chart_commentary"] = "chart_commentary"
    chart_image_path: str = ""
    commentary: str = ""


class ProcessFlowSlide(BaseSlide):
    mold_id: Literal["process_flow"] = "process_flow"
    steps: list[str] = Field(default_factory=list, max_length=5)


class TimelineSlide(BaseSlide):
    mold_id: Literal["timeline"] = "timeline"
    phases: list[dict[str, str]] = Field(default_factory=list, max_length=4)  # [{"date": ..., "label": ...}]


class QuoteHighlightSlide(BaseSlide):
    mold_id: Literal["quote_highlight"] = "quote_highlight"
    quote_text: str
    attribution: str = ""


class ImageCaptionSlide(BaseSlide):
    mold_id: Literal["image_caption"] = "image_caption"
    image_path: str = ""
    caption: str = ""


class SafetyAlertSlide(BaseSlide):
    mold_id: Literal["safety_alert"] = "safety_alert"
    alert_title: str
    severity_label: str = "HIGH SEVERITY"
    detail: str = ""


class TableDataSlide(BaseSlide):
    mold_id: Literal["table_data"] = "table_data"
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class TwoColumnSlide(BaseSlide):
    mold_id: Literal["two_column"] = "two_column"
    left_title: str = ""
    left_points: list[str] = Field(default_factory=list, max_length=3)
    right_title: str = ""
    right_points: list[str] = Field(default_factory=list, max_length=3)


class RiskMatrixSlide(BaseSlide):
    mold_id: Literal["risk_matrix"] = "risk_matrix"
    risks: list[dict[str, str]] = Field(default_factory=list, max_length=4)  # [{"label": ..., "likelihood": ..., "impact": ...}]


class OrgChartSlide(BaseSlide):
    mold_id: Literal["org_or_flow_chart"] = "org_or_flow_chart"
    nodes: list[str] = Field(default_factory=list, max_length=5)


class ExecutiveSummarySlide(BaseSlide):
    mold_id: Literal["executive_summary"] = "executive_summary"
    headline: str = ""
    points: list[str] = Field(default_factory=list, max_length=4)


class SectionDividerSlide(BaseSlide):
    mold_id: Literal["section_divider"] = "section_divider"
    section_title: str = ""


class AgendaSlide(BaseSlide):
    mold_id: Literal["agenda"] = "agenda"
    items: list[str] = Field(default_factory=list, max_length=6)


class GenericGridSlide(BaseSlide):
    mold_id: Literal["generic_grid"] = "generic_grid"
    blocks: list[dict[str, str]] = Field(default_factory=list, max_length=4)  # [{"title": ..., "text": ...}]


class FlexibleHighlightSlide(BaseSlide):
    mold_id: Literal["flexible_highlight"] = "flexible_highlight"
    highlights: list[str] = Field(default_factory=list, max_length=6)


SlideSchema = Union[
    TitleBulletsSlide,
    StatCalloutSlide,
    MultiStatRowSlide,
    ComparisonCardsSlide,
    ChartCommentarySlide,
    ProcessFlowSlide,
    TimelineSlide,
    QuoteHighlightSlide,
    ImageCaptionSlide,
    SafetyAlertSlide,
    TableDataSlide,
    TwoColumnSlide,
    RiskMatrixSlide,
    OrgChartSlide,
    ExecutiveSummarySlide,
    SectionDividerSlide,
    AgendaSlide,
    GenericGridSlide,
    FlexibleHighlightSlide,
]


class DeckPlan(BaseModel):
    deck_title: str
    session_id: str = "default"
    slides: list[dict[str, Any]] = Field(default_factory=list)


# ── Template Path Resolution ────────────────────────────────────────────────

def resolve_template_path() -> str:
    """Find the MRPL master template, PPTX/MRPL_Template.pptx.

    ONE TEMPLATE EVERYWHERE. The sandbox (Dockerfile.sandbox) was given
    MRPL_Template.pptx while this resolver, on the host, picked the older
    Gemini_MRPL.pptx -- so every deck users received was built from one
    template and every test ran against another.

    No /tmp candidate: a shared writable path is somewhere any process
    can plant a template that every deck would then be built from.
    """
    env_path = os.environ.get("MRPL_PPTX_TEMPLATE")
    if env_path and os.path.exists(env_path):
        return env_path

    sandbox_template = Path("/sandbox/lib/mrpl_template.pptx")
    if sandbox_template.exists():
        return str(sandbox_template)

    # Only on the host: in the sandbox this file is /sandbox/lib/slide_kit.py,
    # which has no parents[3] -- computing this first raised IndexError and
    # broke every render.
    parents = Path(__file__).resolve().parents
    repo_template = (parents[3] if len(parents) > 3 else Path.cwd()) / "PPTX" / "MRPL_Template.pptx"
    if repo_template.exists():
        return str(repo_template)

    raise FileNotFoundError(f"Master PPTX template not found at {sandbox_template} or {repo_template}.")


# ── Text & Placeholder Substitution ─────────────────────────────────────────

def _build_replacements_for_slide(slide_data: dict[str, Any]) -> dict[str, str]:
    """Convert structured slide JSON into {{placeholder}} string replacements."""
    mold_id = slide_data.get("mold_id", "title_bullets")
    replacements: dict[str, str] = {}

    title = slide_data.get("title", "")
    citations = slide_data.get("citations", [])
    cite_str = "".join(f" [{c}]" for c in citations) if citations else ""
    if title:
        replacements["title"] = f"{title}{cite_str}"
    # The small label above the title. Only what the plan supplies; the
    # template's own ("EXECUTIVE BRIEFING") is sample text.
    replacements["section_label"] = str(slide_data.get("section_label", ""))

    if mold_id == "title_bullets":
        bullets = slide_data.get("bullets", [])
        for i in range(1, 6):
            b = bullets[i - 1] if i - 1 < len(bullets) else ""
            replacements[f"bullet_{i}"] = b

    elif mold_id == "stat_callout":
        replacements["big_number"] = str(slide_data.get("big_number", ""))
        replacements["label"] = str(slide_data.get("label", ""))
        replacements["context_sentence"] = str(slide_data.get("context_sentence", ""))

    elif mold_id == "multi_stat_row":
        stats = slide_data.get("stats", [])
        for i in range(1, 5):
            st = stats[i - 1] if i - 1 < len(stats) else {}
            replacements[f"stat_{i}_value"] = str(st.get("value", ""))
            replacements[f"stat_{i}_label"] = str(st.get("label", ""))

    elif mold_id == "comparison_cards":
        cards = slide_data.get("cards", [])
        for i in range(1, 4):
            card = cards[i - 1] if i - 1 < len(cards) else {}
            replacements[f"card_{i}_title"] = str(card.get("title", ""))
            pts = card.get("points", [])
            replacements[f"card_{i}_point_1"] = pts[0] if len(pts) > 0 else ""
            replacements[f"card_{i}_point_2"] = pts[1] if len(pts) > 1 else ""

    elif mold_id == "chart_commentary":
        replacements["commentary"] = str(slide_data.get("commentary", ""))
        replacements["chart_image"] = str(slide_data.get("chart_image_path", ""))

    elif mold_id == "process_flow":
        steps = slide_data.get("steps", [])
        for i in range(1, 6):
            replacements[f"step_{i}_label"] = steps[i - 1] if i - 1 < len(steps) else ""

    elif mold_id == "timeline":
        phases = slide_data.get("phases", [])
        for i in range(1, 5):
            ph = phases[i - 1] if i - 1 < len(phases) else {}
            replacements[f"phase_{i}_date"] = str(ph.get("date", ""))
            replacements[f"phase_{i}_label"] = str(ph.get("label", ""))

    elif mold_id == "quote_highlight":
        replacements["quote_text"] = str(slide_data.get("quote_text", ""))
        replacements["attribution"] = str(slide_data.get("attribution", ""))

    elif mold_id == "image_caption":
        replacements["caption"] = str(slide_data.get("caption", ""))
        replacements["image"] = str(slide_data.get("image_path", ""))

    elif mold_id == "safety_alert":
        replacements["alert_title"] = str(slide_data.get("alert_title", ""))
        replacements["severity_label"] = str(slide_data.get("severity_label", "CRITICAL ALERT"))
        replacements["detail"] = str(slide_data.get("detail", ""))

    elif mold_id == "two_column":
        replacements["left_title"] = str(slide_data.get("left_title", ""))
        left_pts = slide_data.get("left_points", [])
        replacements["left_point_1"] = left_pts[0] if len(left_pts) > 0 else ""
        replacements["left_point_2"] = left_pts[1] if len(left_pts) > 1 else ""

        replacements["right_title"] = str(slide_data.get("right_title", ""))
        right_pts = slide_data.get("right_points", [])
        replacements["right_point_1"] = right_pts[0] if len(right_pts) > 0 else ""
        replacements["right_point_2"] = right_pts[1] if len(right_pts) > 1 else ""

    elif mold_id == "risk_matrix":
        risks = slide_data.get("risks", [])
        for i in range(1, 5):
            r = risks[i - 1] if i - 1 < len(risks) else {}
            replacements[f"risk_{i}_label"] = str(r.get("label", ""))
            replacements[f"risk_{i}_likelihood"] = str(r.get("likelihood", ""))
            replacements[f"risk_{i}_impact"] = str(r.get("impact", ""))

    elif mold_id == "org_or_flow_chart":
        nodes = slide_data.get("nodes", [])
        for i in range(1, 6):
            replacements[f"node_{i}_label"] = nodes[i - 1] if i - 1 < len(nodes) else ""

    elif mold_id == "executive_summary":
        replacements["headline"] = str(slide_data.get("headline", slide_data.get("subtitle", "")))
        pts = slide_data.get("points") or slide_data.get("bullets", [])
        if not pts:
            pts = [slide_data.get(f"bullet_{i}") for i in range(1, 5) if slide_data.get(f"bullet_{i}")]
        for i in range(1, 5):
            replacements[f"point_{i}_text"] = pts[i - 1] if i - 1 < len(pts) else ""

    elif mold_id == "section_divider":
        replacements["section_title"] = str(slide_data.get("section_title", title))

    elif mold_id == "agenda":
        items = slide_data.get("items", [])
        for i in range(1, 7):
            replacements[f"agenda_item_{i}"] = items[i - 1] if i - 1 < len(items) else ""

    elif mold_id == "generic_grid":
        blocks = slide_data.get("blocks", [])
        for i in range(1, 5):
            blk = blocks[i - 1] if i - 1 < len(blocks) else {}
            replacements[f"block_{i}_title"] = str(blk.get("title", ""))
            replacements[f"block_{i}_text"] = str(blk.get("text", ""))

    elif mold_id == "flexible_highlight":
        hl = slide_data.get("highlights", [])
        for i in range(1, 7):
            replacements[f"highlight_{i}"] = hl[i - 1] if i - 1 < len(hl) else ""

    return replacements


def _replace_in_shape(shape: Any, replacements: dict[str, str]) -> None:
    """Substitute placeholders in a PowerPoint shape's text frame."""
    if not getattr(shape, "has_text_frame", False):
        return

    for p in shape.text_frame.paragraphs:
        _replace_in_paragraph(p, replacements)


# A slot is `{{key}}` OR `{{key: sample text}}`. The updated template
# carries sample text in almost every slot -- "{{title: Q3 FY26 Refinery
# Performance Review}}" -- and matching only the bare form meant no title,
# bullet or label was ever filled: the cleanup below then erased them, and
# decks rendered as a logo, a footer and a few unlabelled numbers.
_SLOT = re.compile(r"\{\{\s*(\w+)\s*(?::[^}]*)?\}\}")


def _replace_in_paragraph(p: Any, replacements: dict[str, str]) -> None:
    full_text = "".join(r.text for r in p.runs) if p.runs else p.text
    if "{{" not in full_text:
        return
    # EVERY slot is resolved: filled from the slide, or emptied. The
    # sample text after the colon is the template author's example
    # ("Crude throughput reached 15.2 MMTPA") and must never survive into
    # a deliverable, where it would read as a sourced figure.
    full_text = _SLOT.sub(lambda m: str(replacements.get(m.group(1), "")), full_text)
    full_text = re.sub(r"•\s*(?:—\s*)?$", "", full_text).strip()
    if p.runs:
        p.runs[0].text = full_text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.text = full_text


def _populate_table(shape: Any, headers: list[str], rows: list[list[str]]) -> None:
    """Populate table cells cleanly in a PowerPoint table shape."""
    if not getattr(shape, "has_table", False):
        return

    table = shape.table
    max_rows = len(table.rows)
    max_cols = len(table.columns)

    # Fill header row
    if headers:
        for c_idx in range(min(len(headers), max_cols)):
            table.cell(0, c_idx).text = str(headers[c_idx])

    # Fill data rows
    for r_idx in range(min(len(rows), max_rows - 1)):
        row_data = rows[r_idx]
        for c_idx in range(min(len(row_data), max_cols)):
            table.cell(r_idx + 1, c_idx).text = str(row_data[c_idx])

    # Clear every cell the data did not reach. The template's rows hold
    # sample figures ("{{row_4_col_2: 3.7 ...}}"); a three-row source left
    # the fourth row of invented numbers in the delivered table.
    for row in table.rows:
        for cell in row.cells:
            for p in cell.text_frame.paragraphs:
                _replace_in_paragraph(p, {})


def _inject_image_into_placeholder(slide: Any, image_path: str, mold_id: str) -> None:
    """Replace an image placeholder box with an actual picture if image exists on disk."""
    if not image_path or not os.path.exists(image_path):
        return

    # Look for the container rounded rectangle and placeholder text box
    placeholder_text = "[ {{chart_image}} ]" if mold_id == "chart_commentary" else "[ {{image}} ]"
    target_box = None

    for shape in list(slide.shapes):
        if getattr(shape, "has_text_frame", False) and placeholder_text in shape.text_frame.text:
            target_box = shape
            break

    if target_box is not None:
        left = target_box.left
        top = target_box.top
        width = target_box.width
        height = target_box.height

        try:
            slide.shapes.add_picture(image_path, left, top, width=width, height=height)
            # Clear the placeholder text box
            target_box.text_frame.text = ""
        except Exception:
            pass


# ── Deck Builder Entrypoint ─────────────────────────────────────────────────

def build_deck(
    plan: dict[str, Any] | DeckPlan,
    template_path: Optional[str] = None,
    out_path: str = "deck.pptx",
) -> str:
    """Build a complete PowerPoint presentation from a structured DeckPlan JSON.

    1. Loads master template containing the 19 molds.
    2. For each slide in plan, clones the corresponding mold slide.
    3. Populates all placeholders, tables, images, and footers.
    4. Drops the 19 template master slides.
    5. Saves clean deliverable to out_path.
    """
    if isinstance(plan, DeckPlan):
        plan_dict = plan.model_dump()
    else:
        plan_dict = plan

    tpl_path = template_path or resolve_template_path()
    prs = pptx.Presentation(tpl_path)

    slides_data = plan_dict.get("slides", [])
    if not slides_data:
        raise ValueError("Cannot build deck: plan contains no slides.")

    # 1. Clone required slides to the end of the presentation
    #
    # EACH CLONE USES ITS MOLD'S OWN LAYOUT. This was
    # `prs.slide_layouts[6]` -- "Blank" in PowerPoint's DEFAULT template.
    # The MRPL template has three layouts (DEFAULT, MRPL_LIGHT, MRPL_DARK),
    # so the index raised on every deck once the template was updated,
    # and no deck could be generated at all. Reusing the mold's layout
    # is also what keeps a dark mold on the dark master.
    template_slide_count = len(prs.slides)
    cloned_slides = []

    for idx, s_data in enumerate(slides_data):
        mold_id = s_data.get("mold_id", "title_bullets")
        if mold_id not in MOLD_INDEX:
            mold_id = "title_bullets"

        mold_idx = MOLD_INDEX[mold_id]
        template_slide = prs.slides[mold_idx]

        new_slide = prs.slides.add_slide(template_slide.slide_layout)
        # add_slide() creates the layout's empty placeholders; the mold's
        # shapes are copied in below, so these would be duplicate empty
        # boxes ("Click to add title") on the delivered slide.
        for placeholder in list(new_slide.placeholders):
            placeholder._element.getparent().remove(placeholder._element)

        # Clone all shapes from template slide
        for shape in template_slide.shapes:
            new_slide.shapes._spTree.append(deepcopy(shape._element))

        # 2. Populate placeholders
        replacements = _build_replacements_for_slide(s_data)

        # Footer slide indicator update (REF-DOC-2026 // SLIDE 0X)
        replacements["footer_slide_no"] = f"REF-DOC-2026 // SLIDE {idx + 1:02d}"

        for shape in new_slide.shapes:
            # Table handling for table_data mold
            if mold_id == "table_data" and getattr(shape, "has_table", False):
                headers = s_data.get("headers", ["Item", "Specification", "Limit", "Status"])
                rows = s_data.get("rows", [])
                _populate_table(shape, headers, rows)
            else:
                _replace_in_shape(shape, replacements)

                # Special footer number update
                if getattr(shape, "has_text_frame", False) and "REF-DOC-2026 // SLIDE" in shape.text_frame.text:
                    shape.text_frame.text = f"REF-DOC-2026 // SLIDE {idx + 1:02d}"

        # 3. Image injection if applicable
        img_path = s_data.get("chart_image_path") or s_data.get("image_path")
        if img_path:
            _inject_image_into_placeholder(new_slide, img_path, mold_id)

        cloned_slides.append(new_slide)

    # 4. Drop the template's own slides -- COUNTED, not assumed to be 19,
    # so adding or removing a mold cannot leave template slides in (or
    # delete generated ones from) the deliverable.
    sld_id_lst = prs.slides._sldIdLst
    for _ in range(template_slide_count):
        if len(sld_id_lst) > 0:
            r_id = sld_id_lst[0].rId
            prs.part.drop_rel(r_id)
            del sld_id_lst[0]

    # Ensure output directory exists
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    prs.save(out_path)
    return out_path
