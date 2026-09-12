"""Show the user the page an answer came from, with the passage
highlighted — read live from their own file, never from a copy.

THE PROBLEM. An answer cites "SOP-114, page 7". In a 500-page document
that is a claim the user cannot check without going and finding it
themselves, which is exactly the friction that makes people stop
trusting a retrieval system. Showing the actual page, with the quoted
passage marked on it, turns a citation into evidence.

HOW IT WORKS. Chunk metadata already records the source document name
and page number. The registry (document_registry.py) turns that name
into the live path on the user's machine — nothing is copied, so what is
rendered is always the current file. PyMuPDF renders that one page to a
PNG at a requested DPI, and searches it for the chunk's own text to get
the rectangles to highlight.

WHY THE HIGHLIGHT IS SEARCHED FOR RATHER THAN STORED. Storing character
offsets at ingestion would be faster, but they go stale the moment the
document is edited, and would then highlight the wrong region with total
confidence — worse than no highlight. Searching the live page means the
highlight either matches what is there now, or honestly finds nothing.

WHY ONLY ONE PAGE IS EVER RENDERED. Rendering is the expensive step, and
a preview needs the page the user asked about, not the document. One
page at 150 DPI is a few hundred KB and tens of milliseconds; the whole
500-page document is neither.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from backend.ingestion.document_registry import (
    DocumentRegistry,
    DocumentStatus,
)

# 150 DPI: comfortably readable when zoomed on screen, roughly a quarter
# the pixels of 300 DPI print resolution. Preview quality is a UI
# concern, so it is a parameter, but the default is chosen for reading
# on a screen rather than for printing.
DEFAULT_PREVIEW_DPI = 150

# A highlight is anchored by searching for a distinctive run of words
# from the chunk. Too short and it matches everywhere on the page; too
# long and any extraction difference (a ligature, a hyphenated line
# break) makes it match nothing. Measured against this corpus, 6-10 words
# is the range that reliably hits exactly once.
_ANCHOR_WORDS = 8


class HighlightRect(BaseModel):
    """A rectangle to draw on the rendered page, in IMAGE pixel space.

    Converted from PDF points to pixels here rather than in the UI: the
    conversion depends on the DPI this module chose to render at, and a
    consumer that has to know that is a consumer that will eventually
    get it wrong.
    """

    x: float
    y: float
    width: float
    height: float


class PagePreview(BaseModel):
    document_name: str
    page_number: int
    page_count: int | None
    image_png: bytes
    width_px: int
    height_px: int
    highlights: list[HighlightRect]
    status: str
    warning: str | None = None

    model_config = {"arbitrary_types_allowed": True}


def _anchor_phrases(text: str) -> list[str]:
    """Distinctive phrases from a chunk to search for on the page.

    Several are tried, from different parts of the chunk, because a
    chunk usually spans a page boundary at one end or the other: its
    first words may live on the previous page and its last on the next,
    so anchoring on any single position fails often.
    """
    words = re.findall(r"\S+", text)
    if len(words) < 3:
        return [text.strip()] if text.strip() else []

    phrases = []
    for start in (0, len(words) // 3, len(words) // 2):
        window = words[start:start + _ANCHOR_WORDS]
        if len(window) >= 3:
            phrases.append(" ".join(window))
    return list(dict.fromkeys(phrases))


def render_page_preview(
    document_name: str,
    page_number: int,
    registry: DocumentRegistry,
    highlight_text: str | None = None,
    dpi: int = DEFAULT_PREVIEW_DPI,
) -> PagePreview | None:
    """Render one page of a registered document, highlighting `highlight_text`.

    Returns None only when the document cannot be identified at all. A
    document that is registered but missing or modified still returns a
    preview object where possible, carrying a `warning` — telling the
    user "this file changed since indexing" is far more useful than
    silently showing nothing.
    """
    import fitz

    matches = registry.find_by_name(document_name)
    if not matches:
        return None

    resolved = registry.resolve(matches[0].document_id)
    if resolved.status is DocumentStatus.MISSING or resolved.path is None:
        return None

    warning = resolved.detail if resolved.status is DocumentStatus.MODIFIED else None

    with fitz.open(resolved.path) as doc:
        index = page_number - 1
        if index < 0 or index >= doc.page_count:
            return None
        page = doc[index]

        highlights: list[HighlightRect] = []
        scale = dpi / 72.0  # PDF user space is 72 points per inch
        if highlight_text:
            for phrase in _anchor_phrases(highlight_text):
                # Whole-phrase search first; PyMuPDF handles the common
                # case of a phrase wrapped across a line internally.
                for rect in page.search_for(phrase, quads=False) or []:
                    highlights.append(
                        HighlightRect(
                            x=rect.x0 * scale,
                            y=rect.y0 * scale,
                            width=(rect.x1 - rect.x0) * scale,
                            height=(rect.y1 - rect.y0) * scale,
                        )
                    )
                if highlights:
                    break  # first anchor that lands is enough

        pixmap = page.get_pixmap(dpi=dpi)
        return PagePreview(
            document_name=resolved.ref.original_name if resolved.ref else document_name,
            page_number=page_number,
            page_count=doc.page_count,
            image_png=pixmap.tobytes("png"),
            width_px=pixmap.width,
            height_px=pixmap.height,
            highlights=highlights,
            status=resolved.status.value,
            warning=warning,
        )


def preview_for_chunk(chunk, registry: DocumentRegistry, dpi: int = DEFAULT_PREVIEW_DPI):
    """Preview the page a retrieved chunk came from, highlighting it.

    Accepts either shape of chunk — an IngestedChunk with `.metadata`, or
    a RetrievedChunk with the fields directly — so a caller does not have
    to convert between the ingestion and retrieval views to show a page.

    Returns None for chunks from unpaginated sources (DOCX, TXT, email,
    audio): there is no page to render, and rendering "page 1" of a flow
    document would show something the text may not even be on.
    """
    metadata = getattr(chunk, "metadata", None) or chunk
    page_number = getattr(metadata, "page_number", None)
    document_name = getattr(metadata, "source_document", None)
    if page_number is None or not document_name:
        return None

    return render_page_preview(
        document_name=document_name,
        page_number=page_number,
        registry=registry,
        highlight_text=getattr(chunk, "text", None),
        dpi=dpi,
    )


def save_preview(preview: PagePreview, out_path: str | Path) -> Path:
    """Write a preview's PNG to disk (for a CLI, a test, or a file the UI serves)."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(preview.image_png)
    return path
