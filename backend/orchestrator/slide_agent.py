"""Presentation generation: the two phases either side of the approval gate.

    prepare_deck(request)   plans and validates the deck. Writes nothing.
    generate_deck(spec, p)  renders exactly that deck. WRITES A FILE, so
                            it is registered with requires_approval=True.

Hard constraint #4 allows no file write without approval, and the gate's
contract is that the operator approves the concrete call that will run.
A deck cannot meet that if one call both plans and writes -- the slides
do not exist until the model has written them -- so planning happens
first, the approval lists the real slide titles and sources, and the
gated call renders that plan with no model call that could change it.

WHAT IS WHERE. Content (what the deck says, grounded and validated):
orchestrator/deck_agent.py. Design (how it looks): tools/generation/deck.

NOT RENDERED IN THE SANDBOX, deliberately. The sandbox exists for
MODEL-WRITTEN code, which cannot be trusted with the filesystem. The
renderer is our own deterministic code driven by validated data, and
putting it in a container made deck generation fail whenever Docker was
not running -- a dependency the demo does not need.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.audit.audit_log import AuditLog
from backend.orchestrator.deck_agent import NotInCorpus, build_deck_spec
from backend.tools.generation.deck import render_deck as _render

logger = logging.getLogger("pptx.slide_agent")

__all__ = ["prepare_deck", "generate_deck", "NotInCorpus"]


def prepare_deck(request: str, session_id: str = "default", max_slides: int | None = None) -> dict[str, Any]:
    """Plan and validate a deck for `request`. No file is written.

    Args:
        request: the operator's own words.
        session_id: for logging only.
        max_slides: accepted for compatibility and IGNORED. Deck length
            follows the material: a thin source makes a short deck, a
            rich one a long deck. Capping it either padded thin decks or
            silently dropped findings from rich ones.

    Returns what the approval card needs: the spec, the slide titles, the
    source documents, and anything left out for lack of a source.

    Raises:
        NotInCorpus: no document covers the request.
    """
    from backend.api.state import get_state

    store, chunks = get_state().ensure_corpus()
    logger.info("Preparing deck for %r", request)
    built = build_deck_spec(request, store, chunks)

    clean = re.sub(r"[^\w-]+", "_", request[:40]).strip("_") or "Briefing"
    return {
        "deck_spec": built["deck_spec"],
        "filename": f"MRPL_{clean}.pptx",
        "slide_titles": built["slide_titles"],
        "citations": built["documents"],
        "omitted_sections": built["dropped_slides"],
        "writer": built.get("writer"),
        "defects": [],
        "retries": 0,
    }


def generate_deck(deck_spec: dict, output_path: str) -> dict:
    """Render an approved deck spec to a .pptx file. WRITES A FILE.

    Deterministic: the same spec renders the same deck, so the file
    matches what was approved.

    Args:
        deck_spec: the spec from prepare_deck, as shown in the approval.
        output_path: where to write the .pptx.

    Raises:
        ValueError: a spec with no slides, or a path that is not .pptx.
    """
    sections = [s for s in (deck_spec or {}).get("sections", []) if s.get("slides")]
    if not sections:
        raise ValueError("The deck spec has no slides.")
    out = Path(output_path)
    if out.suffix.lower() != ".pptx":
        raise ValueError(f"Output must be a .pptx file, got {out.name}.")

    result = _render(deck_spec, out)
    digest = hashlib.sha256(json.dumps(deck_spec, sort_keys=True).encode()).hexdigest()[:12]
    documents = [s["document"] for s in deck_spec.get("sources", [])]
    AuditLog().log(
        event="tool_executed",
        request_id=digest,
        actor="generate_deck",
        summary=f"Wrote {result['slide_count']}-slide presentation {out.name}",
        details={"output_path": str(out), "documents": documents},
    )
    return {
        "deck_path": str(out),
        "filename": out.name,
        # Measured, never a plausible default (Review Rule 4).
        "file_size": f"{out.stat().st_size // 1024} KB",
        "slide_count": result["slide_count"],
        "citations": documents,
    }
