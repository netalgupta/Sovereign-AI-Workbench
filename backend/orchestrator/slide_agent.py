"""slide_agent.py — LangGraph Subgraph & Agent Pipeline for Sovereign PPTX Generation.

Full sequence per PPTX_SYSTEM_ARCHITECTURE.md & PPTX_AGENT_SPEC.md:
1. Planner call (LLM, backend) -> outline with rough mold guesses.
2. Content fetch loop (deterministic, backend) -> hybrid retrieval + math + images.
3. Filler call per section (LLM, backend) -> confirms mold, populates fields with citations.
4. Assemble context.json (backend) -> written to session sandbox volume.
5. Render step (Docker sandbox / local fallback) -> slide_kit.build_deck -> deck.pptx.
6. Heuristic QA + Visual QA (backend) -> checks bounds, overflow, and placeholders.
7. Bounded retry (max 2 retries) -> fixes defective slide in-place.
8. Deliver -> returns final presentation path, citations, and metadata.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from backend.audit.audit_log import AuditLog
from backend.models.registry import resolve_model_name
from backend.tools.generation.qa_render import convert_pptx_to_images, run_heuristic_qa, run_visual_qa
from backend.tools.generation.slide_kit import MOLD_INDEX, build_deck, resolve_template_path

logger = logging.getLogger("pptx.slide_agent")
# The CHECKED host (Review Rule 7). This read OLLAMA_HOST straight from
# the environment, one variable away from sending corpus text off the
# machine; ollama_client refuses anything that is not loopback.
from backend.models.ollama_client import OLLAMA_HOST as _OLLAMA_HOST

# Maximum retries on QA failure per deck
MAX_RETRIES = 2


# ── Step 3a: Planner Call ───────────────────────────────────────────────────

_PLANNER_SYSTEM_PROMPT = """You are an expert executive presentation planner for Mangalore Refinery and Petrochemicals Limited (MRPL).
Given a user query and technical topic, break it down into an executive slide deck outline of 5 to 7 logical sections.

Available Slide Mold IDs:
- executive_summary: Deck opening summary with key takeaways
- title_bullets: Standard narrative slide (up to 5 bullets)
- stat_callout: Single huge headline metric (e.g., flow rate, throughput)
- multi_stat_row: 3-4 side-by-side KPI stats
- comparison_cards: Comparing 2-3 options or units
- chart_commentary: Trend or historical telemetry with observations
- process_flow: Sequence of operational steps
- timeline: Milestones with dates/durations
- safety_alert: Critical safety warning, interlock, or trip procedure
- table_data: Technical specification or sensor telemetry data table
- two_column: Trade-off or Before/After comparison
- risk_matrix: HAZOP risk severity assessment (likelihood vs impact)
- section_divider: Transition between major operational areas
- agenda: Table of contents

Respond ONLY with a valid JSON array of objects. Each object must have:
- "section_title": String title for the slide
- "provisional_mold": One of the Mold IDs above
- "content_need": Short description of technical data/facts needed
"""

def plan_deck_outline(request: str, model_id: str = "reasoning-model") -> list[dict[str, Any]]:
    """Generate an outline of sections with provisional mold guesses."""
    model_name = resolve_model_name(model_id)

    prompt = (
        f"{_PLANNER_SYSTEM_PROMPT}\n\n"
        f"USER REQUEST: \"{request}\"\n\n"
        "Generate the slide outline as a JSON array:"
    )

    try:
        res = requests.post(
            f"{_OLLAMA_HOST}/api/generate",
            json={"model": model_name, "prompt": prompt, "format": "json", "stream": False},
            timeout=45,
        )
        if res.status_code == 200:
            raw = res.json().get("response", "")
            data = json.loads(raw)
            if isinstance(data, dict) and "outline" in data:
                data = data["outline"]
            if isinstance(data, list) and len(data) >= 3:
                return data[:8]
    except Exception as exc:
        logger.info(f"Ollama planner call failed or unavailable ({exc}); using deterministic fallback outline.")

    # Deterministic high-quality fallback outline matching MRPL refinery operations
    clean_req = re.sub(r"[^\w\s]", "", request).strip() or "Refinery Operations Briefing"
    return [
        {
            "section_title": "EXECUTIVE SUMMARY",
            "provisional_mold": "executive_summary",
            "content_need": f"High-level briefing and operational context for {clean_req}",
        },
        {
            "section_title": "KEY OPERATIONAL METRICS",
            "provisional_mold": "multi_stat_row",
            "content_need": "Throughput, capacity limits, and operating flow rates",
        },
        {
            "section_title": "CRITICAL SAFETY & INTERLOCK PROCEDURES",
            "provisional_mold": "safety_alert",
            "content_need": "Interlocks, trip limits, and emergency shutdown protocols",
        },
        {
            "section_title": "SENSOR TELEMETRY & SPECIFICATIONS",
            "provisional_mold": "table_data",
            "content_need": "Thermocouple array readings and nominal design tolerances",
        },
        {
            "section_title": "ACTION PLAN & NEXT STEPS",
            "provisional_mold": "title_bullets",
            "content_need": "Operator actions and engineering recommendations",
        },
    ]


# ── Step 3b: Content Fetch Loop ─────────────────────────────────────────────

def fetch_section_content(
    section: dict[str, Any],
    original_request: str,
    pipeline_state: Any = None,
) -> dict[str, Any]:
    """Retrieve grounded facts, calculate numbers, and fetch relevant image references."""
    if pipeline_state is None:
        try:
            from backend.api.state import get_state
            pipeline_state = get_state()
        except Exception:
            pipeline_state = None
    query = f"{original_request} {section.get('section_title', '')} {section.get('content_need', '')}"
    bundle: dict[str, Any] = {
        "section_title": section.get("section_title", "Operational Update"),
        "provisional_mold": section.get("provisional_mold", "title_bullets"),
        "text_snippets": [],
        "citations": [],
        "numbers": {},
        "image_path": None,
    }

    try:
        store, _ = pipeline_state.ensure_corpus()
        from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
        res = retrieve_with_grounding_check(store, query, top_k=3)
        if res.found and res.chunks:
            for c in res.chunks:
                bundle["text_snippets"].append(c.text)
                # A citation NAMES ITS SOURCE. These were the integers
                # 1..3 per section, merged across sections into one set,
                # so "[1]" on slide 2 and "[1]" on slide 4 were different
                # passages and neither could be looked up.
                ref = c.source_document + (f" p.{c.page_number}" if c.page_number else "")
                if ref not in bundle["citations"]:
                    bundle["citations"].append(ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval failed for section %r: %s", bundle["section_title"], exc)

    # NOTHING RETRIEVED MEANS NOTHING TO SAY. This used to append the
    # sentence "Verified against MRPL Standard Operating Procedures for
    # <request>" and cite it as source [1] -- text written by this
    # function, presented as a verified document. A section the corpus
    # does not cover is marked ungrounded and left out of the deck.
    bundle["grounded"] = bool(bundle["text_snippets"])
    return bundle


# ── Step 3c: Filler Call ────────────────────────────────────────────────────

_FILLER_SYSTEM_PROMPT = """You are an expert technical slide author for Mangalore Refinery and Petrochemicals Limited (MRPL).
Given a section title, sourced factual snippets, citations, and the available slide molds, generate the structured JSON for ONE slide.

Available Molds:
- executive_summary: fields -> "headline": str, "points": [str] (max 4)
- title_bullets: fields -> "bullets": [str] (max 5)
- stat_callout: fields -> "big_number": str, "label": str, "context_sentence": str
- multi_stat_row: fields -> "stats": [{"value": str, "label": str}] (max 4)
- comparison_cards: fields -> "cards": [{"title": str, "points": [str]}] (max 3)
- process_flow: fields -> "steps": [str] (max 5)
- timeline: fields -> "phases": [{"date": str, "label": str}] (max 4)
- safety_alert: fields -> "alert_title": str, "severity_label": str, "detail": str
- table_data: fields -> "headers": [str], "rows": [[str]]
- two_column: fields -> "left_title": str, "left_points": [str], "right_title": str, "right_points": [str]

Rules:
1. "mold_id" MUST be one of the exact names above.
2. "title": concise uppercase title.
3. Every fact must come strictly from the provided text snippets.
4. "citations": list of integer citation IDs provided.
5. Return ONLY a valid JSON object matching the chosen mold.
"""

def fill_slide_content(
    bundle: dict[str, Any],
    defect_feedback: Optional[str] = None,
    model_id: str = "reasoning-model",
) -> dict[str, Any]:
    """Produce the filled structured JSON for a single slide."""
    mold_guess = bundle.get("provisional_mold", "title_bullets")
    snippets_str = "\n---\n".join(bundle["text_snippets"][:3])
    cites = bundle.get("citations", [1])

    prompt = (
        f"{_FILLER_SYSTEM_PROMPT}\n\n"
        f"SECTION TITLE: {bundle['section_title']}\n"
        f"RECOMMENDED MOLD: {mold_guess}\n"
        f"SOURCED CORPUS TEXT:\n{snippets_str}\n"
        f"AVAILABLE CITATION IDS: {cites}\n"
    )
    if defect_feedback:
        prompt += f"\nCORRECTION REQUIRED: Previous attempt had defect: '{defect_feedback}'. Please fix and strictly respect constraints.\n"

    prompt += "\nOutput JSON object for this slide:"

    try:
        model_name = resolve_model_name(model_id)
        res = requests.post(
            f"{_OLLAMA_HOST}/api/generate",
            json={"model": model_name, "prompt": prompt, "format": "json", "stream": False},
            timeout=40,
        )
        if res.status_code == 200:
            data = json.loads(res.json().get("response", "{}"))
            slide = _validated_slide(data, bundle)
            if slide is not None:
                return slide
    except Exception as exc:  # noqa: BLE001
        logger.info("Slide filler call unavailable (%s); building the slide from sources.", exc)

    return _build_fallback_slide(bundle, mold_guess, cites)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers_in(value: Any) -> set[str]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def _validated_slide(data: Any, bundle: dict[str, Any]) -> dict[str, Any] | None:
    """The model's slide, if it is well-formed AND its numbers are sourced.

    Returns None to fall back to the source text. Two checks:

    SHAPE. The model returned table rows as objects keyed by header, not
    as lists; slide_kit indexed them by position and the render crashed
    with KeyError: 0. Rows are normalised to lists here, and a slide that
    cannot be made to fit its mold is rejected rather than half-rendered.

    NUMBERS. "Every fact must come strictly from the provided text" was a
    sentence in the prompt and nothing more. A figure on a refinery slide
    that no source contains is a fabricated measurement with a citation
    attached, so every number in the slide must appear in the snippets.
    Single digits are exempt: they are step numbers and counts, not
    measurements.
    """
    if not isinstance(data, dict) or data.get("mold_id") not in MOLD_INDEX:
        return None
    data = dict(data)
    data.setdefault("title", bundle["section_title"])
    data["citations"] = list(bundle.get("citations", []))

    if data["mold_id"] == "table_data":
        headers = data.get("headers")
        rows = data.get("rows")
        if not isinstance(headers, list) or not isinstance(rows, list) or not rows:
            return None
        normalised = []
        for row in rows:
            if isinstance(row, dict):
                row = [row.get(h, "") for h in headers]
            if not isinstance(row, list):
                return None
            normalised.append([str(cell) for cell in row])
        data["rows"] = normalised

    sourced = _numbers_in(" ".join(bundle.get("text_snippets", [])))
    content = {k: v for k, v in data.items() if k not in ("citations", "mold_id")}
    unsourced = {n for n in _numbers_in(content) if len(n) > 1 and n not in sourced}
    if unsourced:
        logger.warning(
            "Slide %r has numbers no source contains (%s); using the source text instead.",
            bundle["section_title"], ", ".join(sorted(unsourced)[:5]),
        )
        return None
    return data


def _build_fallback_slide(bundle: dict[str, Any], mold_id: str, cites: list) -> dict[str, Any]:
    """A slide built ONLY from the retrieved text, when the model's is unusable.

    THIS USED TO INVENT A REFINERY. Per mold it returned fixed figures --
    "1,450 m3/h", "410.0 C WABT", "99.65 % H2 purity", a four-row
    thermocouple table all reading NORMAL, "Exceeding 110% of design
    capacity trips FFC-201" -- and attached the section's citations to
    them. Any deck built while the model was busy or returned bad JSON
    carried those numbers as sourced fact. FFC-201 at 1,450 m3/h is the
    same invented interlock Review Rule 4 records being removed three
    times.

    The honest fallback is less impressive: the source sentences
    themselves, as bullets, with their real sources. `mold_id` is
    accepted for signature compatibility and deliberately not honoured --
    a stat callout needs a number, and the only way to guarantee one here
    was to make it up.
    """
    sentences: list[str] = []
    for snippet in bundle.get("text_snippets", []):
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(snippet.split())):
            sentence = sentence.strip()
            if 25 <= len(sentence) <= 220 and sentence not in sentences:
                sentences.append(sentence)
            if len(sentences) == 4:
                break
        if len(sentences) == 4:
            break
    return {
        "mold_id": "title_bullets",
        "title": bundle["section_title"],
        "bullets": sentences,
        "citations": list(cites),
    }


# ── Step 5: Render Engine ───────────────────────────────────────────────────

def render_deck(
    plan: dict[str, Any],
    session_id: str = "default",
    out_dir: Optional[str] = None,
) -> str:
    """Execute rendering step inside the warm, isolated Docker sandbox.

    Per Sovereign Workbench architecture: all script-driven compilation runs
    in an egress-blocked container with strict resource limits.
    """
    from backend.sandbox.pool import SESSIONS_HOST_DIR, SESSIONS_CONTAINER_DIR
    from backend.sandbox.executor import run_in_sandbox

    host_workspace = os.path.join(out_dir or SESSIONS_HOST_DIR, session_id)
    os.makedirs(host_workspace, exist_ok=True)

    context_path = os.path.join(host_workspace, "context.json")
    with open(context_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    container_workspace = f"{SESSIONS_CONTAINER_DIR}/{session_id}"
    container_context = f"{container_workspace}/context.json"
    container_output = f"{container_workspace}/MRPL_Executive_Briefing.pptx"
    output_pptx = os.path.join(host_workspace, "MRPL_Executive_Briefing.pptx")

    code = (
        "import json\n"
        "import sys\n"
        "from slide_kit import build_deck\n"
        f"with open('{container_context}', 'r', encoding='utf-8') as f:\n"
        "    plan = json.load(f)\n"
        f"build_deck(plan, out_path='{container_output}')\n"
        "print('RENDER_SUCCESS')\n"
    )

    logger.info(f"Dispatched PPTX rendering to sandbox container for session: {session_id}")
    res = run_in_sandbox(code, session_id=session_id, language="python", timeout_seconds=30)

    if res.exit_code != 0:
        raise RuntimeError(
            f"Sandbox PPTX rendering failed with exit code {res.exit_code}:\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    if not os.path.exists(output_pptx):
        raise FileNotFoundError(
            f"Sandbox reported success (exit code 0) but output deck not found at {output_pptx}.\n"
            f"Container stdout: {res.stdout}\nContainer stderr: {res.stderr}"
        )

    logger.info(f"Sandbox rendered deck successfully: {output_pptx} ({os.path.getsize(output_pptx)} bytes)")
    return output_pptx


# ── Two phases: prepare (before approval), generate (the gated write) ────────
#
# WHY TWO FUNCTIONS. This was one call, run_slide_pipeline, that planned
# the deck with a model AND wrote the .pptx, and it was exempted from the
# approval gate. Hard constraint #4 allows no file write without approval,
# and the gate's contract is that the operator approves the concrete call
# that will run -- draft_docx shows its actual sections before anyone
# signs. A deck cannot meet that while planning and writing are one step:
# the slides do not exist until the model has written them.
#
# So planning happens first and writes nothing outside the sandbox; the
# approval shows every slide title and source; and the gated tool renders
# exactly the approved plan, deterministically, with no model call that
# could change what was approved.


def prepare_deck(
    request: str,
    session_id: str = "default",
    max_slides: int = 6,
) -> dict[str, Any]:
    """Plan, fill and QA a deck. Writes nothing outside the sandbox.

    Returns the deck plan the approval will show and generate_deck will
    render, plus what the operator needs to judge it.

    Raises:
        ValueError: nothing in the corpus covers the request.
    """
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    pipeline_state = get_state()
    logger.info("Preparing deck for request: %r", request)

    # IS THE REQUEST ITSELF IN THE CORPUS? Section retrieval queries the
    # request PLUS the planner's section title and content need --
    # "Thermocouple array readings and nominal design tolerances". Those
    # words match a refinery corpus whatever was asked, so every section
    # cleared the grounding gate and "The plot of Pride and Prejudice"
    # produced a sourced-looking deck (MEASURED). The gate has to see the
    # request on its own first.
    store, _ = pipeline_state.ensure_corpus()
    gate = retrieve_with_grounding_check(store, request, top_k=3)
    if not gate.found:
        raise ValueError(
            "No document in the corpus covers this request, so no presentation was "
            f"prepared ({gate.reason or 'below the grounding threshold'})."
        )

    outline = plan_deck_outline(request)[:max_slides]

    citations: list[str] = []
    slide_bundles: list[dict[str, Any]] = []
    filled_slides: list[dict[str, Any]] = []
    omitted_sections: list[str] = []
    for section in outline:
        bundle = fetch_section_content(section, request, pipeline_state)
        if not bundle.get("grounded"):
            omitted_sections.append(bundle["section_title"])
            continue
        slide_json = fill_slide_content(bundle)
        if slide_json.get("mold_id") == "title_bullets" and not slide_json.get("bullets"):
            omitted_sections.append(bundle["section_title"])
            continue
        slide_bundles.append(bundle)
        filled_slides.append(slide_json)
        for c in bundle.get("citations", []):
            if c not in citations:
                citations.append(c)

    # A deck with no sourced slide is a refusal, not a deliverable.
    if not filled_slides:
        raise ValueError(
            "No document in the corpus covers this request, so no presentation was "
            f"prepared. Sections searched: {', '.join(omitted_sections) or 'none'}."
        )

    deck_plan = {
        "deck_title": f"MRPL Executive Briefing: {request[:40]}",
        "slides": filled_slides,
    }

    # QA against a render INSIDE THE SANDBOX, with bounded model re-fills.
    # This all happens before approval, so what the operator approves is
    # the plan after correction, not before it.
    preview_session = f"{session_id}-deck-preview"
    deck_path = render_deck(deck_plan, session_id=preview_session)
    retry_count = 0
    defects = run_heuristic_qa(deck_path, deck_plan)
    while defects and retry_count < MAX_RETRIES:
        retry_count += 1
        logger.info("QA defects (retry %d/%d): %d", retry_count, MAX_RETRIES, len(defects))
        defective = {d["slide_index"] for d in defects if 0 <= d["slide_index"] < len(filled_slides)}
        for idx in defective:
            feedback = "; ".join(d["issue"] for d in defects if d["slide_index"] == idx)
            filled_slides[idx] = fill_slide_content(slide_bundles[idx], defect_feedback=feedback)
        deck_plan["slides"] = filled_slides
        deck_path = render_deck(deck_plan, session_id=preview_session)
        defects = run_heuristic_qa(deck_path, deck_plan)

    try:
        images = convert_pptx_to_images(deck_path)
        if images:
            defects.extend(run_visual_qa(images, deck_plan))
    except Exception as exc:  # noqa: BLE001 - visual QA is optional (needs LibreOffice)
        logger.info("Visual QA unavailable: %s", exc)

    clean_name = re.sub(r"[^\w-]", "_", request[:30]).strip("_") or "Operations"
    return {
        "deck_plan": deck_plan,
        "filename": f"MRPL_{clean_name}_Briefing.pptx",
        "slide_titles": [s.get("title", "") for s in filled_slides],
        "citations": citations,
        "omitted_sections": omitted_sections,
        "defects": defects,
        "retries": retry_count,
    }


def generate_deck(deck_plan: dict, output_path: str) -> dict:
    """Render an approved deck plan to a .pptx file. WRITES A FILE.

    Deterministic: renders exactly the plan it is given, in the sandbox,
    with no model call -- so the file matches what was approved.

    Args:
        deck_plan: the plan from prepare_deck, as shown in the approval.
        output_path: where to write the .pptx.

    Raises:
        ValueError: no slides, or an output path that is not .pptx.
    """
    import hashlib
    import shutil

    if not deck_plan.get("slides"):
        raise ValueError("The deck plan has no slides.")
    out = Path(output_path)
    if out.suffix.lower() != ".pptx":
        raise ValueError(f"Output must be a .pptx file, got {out.name}.")

    digest = hashlib.sha256(json.dumps(deck_plan, sort_keys=True).encode()).hexdigest()[:12]
    rendered = render_deck(deck_plan, session_id=f"deck-{digest}")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rendered, out)

    citations = sorted({c for s in deck_plan["slides"] for c in s.get("citations", [])})
    AuditLog().log(
        event="tool_executed",
        request_id=digest,
        actor="generate_deck",
        summary=f"Wrote {len(deck_plan['slides'])}-slide presentation {out.name}",
        details={"output_path": str(out), "citations": citations},
    )
    return {
        "deck_path": str(out),
        "filename": out.name,
        # Measured, never a plausible default (Review Rule 4).
        "file_size": f"{out.stat().st_size // 1024} KB",
        "slide_count": len(deck_plan["slides"]),
        "citations": citations,
    }
