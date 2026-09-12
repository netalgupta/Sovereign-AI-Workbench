"""Retrieval, exposed to the agent as a callable tool.

WHY THIS FILE HAD TO EXIST.

The tool registry had seventeen tools and not one of them could search
the corpus. `find_contradictions` and `select_images_for_request` sat
under the "retrieval" category, so the category looked populated, but
the thing the whole product is built on -- hybrid search over the
ingested documents -- was reachable only from hardcoded branches inside
`dispatch_node`.

The consequence was immediate and measurable. Given the agent loop and
the full registry, asked "What is the average MFI for Homopolymer
H030SG?", the model reached for `find_contradictions`, got an empty
list, and answered:

    "No documents were found that contain information about the MFI of
     Homopolymer H030SG... I cannot provide an accurate average MFI
     based on the available information."

The corpus contains it. `Novolen_Batch_QA_Report_Aug2026.pdf` states
3.4 g/10min, and the non-agentic path retrieves it every time. The model
did the best it could with the tools it was given; it had no way to look
anything up.

That is the difference between a registry that is complete and one that
merely has entries in every category.

WHY THIS RETURNS THE GROUNDING DECISION, NOT JUST TEXT.

The tool returns `found`, the chunks, and the reason when nothing
cleared the confidence gate -- so the agent sees the same refusal signal
the direct path does. A search tool that returned its best matches
regardless of confidence would hand the model plausible-looking chunks
for an out-of-corpus question and invite exactly the ungrounded answer
NFR-4 exists to prevent.
"""

from __future__ import annotations

from typing import Literal

from backend.tools.registry import tool


@tool(
    name="search_documents",
    category="retrieval",
    tools_md_row=12,
    description=(
        "Search the ingested documents for passages that answer a question. "
        "This is the primary way to find anything about MRPL's equipment, "
        "procedures, specifications, incidents, batches or lab results. "
        "Use it before answering any question about plant documentation. "
        "Returns the matching passages with their source document and page."
    ),
)
def search_documents(query: str, top_k: int = 5) -> dict:
    """Find passages in the corpus that answer `query`.

    Args:
        query: what to look for, in the user's own words.
        top_k: how many passages to return (1-10).

    Returns a dict with `found`, `passages` (text, source_document,
    page_number, score) and, when nothing is confident enough, `reason`
    and the documents that came closest.
    """
    from backend.api.state import get_state
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    top_k = max(1, min(int(top_k or 5), 10))
    store, _ = get_state().ensure_corpus()
    result = retrieve_with_grounding_check(store, query, top_k)

    if not result.found:
        # The refusal is returned to the MODEL, with the near-miss
        # documents, so it can tell "the corpus does not cover this" from
        # "my wording missed" and retry with better terms rather than
        # inventing an answer.
        return {
            "found": False,
            "reason": (
                "Nothing in the indexed documents clears the grounding "
                "confidence threshold for this query."
            ),
            "best_similarity": result.best_similarity,
            "threshold": result.threshold,
            "closest_documents": result.near_miss_documents,
            "passages": [],
        }

    return {
        "found": True,
        "passages": [
            {
                "text": chunk.text,
                "source_document": chunk.source_document,
                "page_number": chunk.page_number,
                "score": round(chunk.score, 4),
            }
            for chunk in result.chunks
        ],
        "admitted_by": result.admitted_by,
    }


@tool(
    name="list_documents",
    category="retrieval",
    description=(
        "List the documents currently loaded in the knowledge base, with "
        "counts and types. Use this when asked what the system has access "
        "to, rather than searching for an answer that is not in any document."
    ),
)
def list_documents(category: Literal["all", "documents", "data", "charts"] = "all") -> dict:
    """What is indexed right now.

    Answers questions ABOUT the collection rather than about its
    contents. Read from the source index, so every name and count is
    exact and nothing is generated.
    """
    from backend.api.routes import get_corpus

    data = get_corpus()
    sources = data.get("sources") or []
    if category != "all":
        sources = [s for s in sources if s.get("category") == category]

    return {
        "count": len(sources),
        "total_size": data.get("totalSizeDisplay"),
        "documents": [
            {
                "name": s.get("name"),
                "type": s.get("type"),
                "category": s.get("category"),
                "collection": s.get("corpus"),
                "size": s.get("size"),
            }
            for s in sources
        ],
    }
