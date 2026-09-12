"""Grounded answer generation — RAG_SPEC.md §4.

Ties together grounded_retrieval.py (§3's confidence gate), the exact
verbatim grounding-enforcement prompt (§4), and citation_validation.py
(§4's post-generation check) into the one function that actually answers
a user's question the way this system is supposed to: grounded, cited,
and willing to say "not found" instead of guessing.
"""

import requests
from pydantic import BaseModel

from backend.models.ollama_client import generate as ollama_generate
from backend.models.registry import resolve_model_name
from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
from backend.retrieval.citation_validation import validate_citations
from backend.retrieval.hybrid_search import RetrievedChunk
from backend.retrieval.vector_store import VectorStore

_OLLAMA_HOST = "http://localhost:11434"

# Verbatim per RAG_SPEC.md §4 — do not paraphrase when implementing.
# Built as prefix + concat, not str.format(): same lesson as
# entity_extraction.py's prompt — avoid brace-collision bugs entirely by
# never running .format() over text that itself might contain literal
# braces (this one doesn't today, but the pattern is now consistent
# across every prompt-building function in this codebase).
_GROUNDING_INSTRUCTIONS = (
    "You must only state facts that are directly supported by the SOURCES section "
    "below. For every factual claim, include a citation marker [N] referring to the "
    "source number. If the sources do not contain enough information to answer, say "
    "so explicitly rather than filling the gap from general knowledge.\n\n"
    "SOURCES:\n"
)


class GeneratedAnswer(BaseModel):
    answer_text: str
    found: bool
    sources: list[RetrievedChunk]
    # Carried through on a refusal so the caller can explain it. See
    # GroundedRetrievalResult for why names, and only names, travel here.
    near_miss_documents: list[str] = []
    best_similarity: float = 0.0
    threshold: float = 0.0
    invalid_citations_stripped: list[int]
    unresolved_placeholders_stripped: int  # count of literal "[N]"-shaped markers the model never resolved — see citation_validation.py


def _format_sources(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        page_part = f", p.{chunk.page_number}" if chunk.page_number is not None else ""
        lines.append(f"[{i}] ({chunk.source_document}{page_part}) {chunk.text}")
    return "\n".join(lines)


# APPENDED, never merged into _GROUNDING_INSTRUCTIONS above, which is
# verbatim per §4 and must stay that way. This is presentation guidance
# only: it changes how an answer is laid out, never what may be claimed
# or how it must be cited.
#
# WHY IT IS WORTH HAVING. The frontend renders GitHub-flavoured markdown
# properly -- real tables via remark-gfm, syntax-highlighted code blocks
# -- and that capability was previously exercised only by a hardcoded
# thermocouple table baked into the JSX. Refinery answers are frequently
# tabular (per-grade specs, per-batch readings, limit-vs-actual), so the
# model should reach for a table when the sources are tabular, and for
# prose when they are not. Structure that mirrors the source is easier
# to check against it, which is the whole point of citing.
_FORMATTING_GUIDANCE = (
    "\n\nFORMATTING:\n"
    "Write in GitHub-flavoured markdown.\n"
    "- When the answer compares several items, or reports values against "
    "limits or specifications, use a markdown table. Put the citation "
    "marker in the cell or the row it supports.\n"
    "- Use `inline code` for tags, identifiers and units (TC-201A, "
    "SOP-114-Rev3, g/10min).\n"
    "- Use a fenced code block for code or for multi-line machine output.\n"
    "- Use **bold** for the single figure that answers the question.\n"
    "- Keep it as short as the question allows. Do not pad an answer to "
    "fill a table, and do not tabulate a single value.\n"
    "- Never invent a row, a column, or a value to complete a table. If "
    "the sources cover only some of the rows, include only those.\n"
)


def _build_prompt(sources_text: str, user_request: str) -> str:
    return (
        f"{_GROUNDING_INSTRUCTIONS}{sources_text}"
        f"{_FORMATTING_GUIDANCE}"
        f"\nREQUEST:\n{user_request}"
    )


def _call_reasoning_model(prompt: str, model_name: str) -> str:
    # Routed through ollama_client so GPU placement (num_gpu) applies
    # here too. Each of the four call sites used to build its own
    # request body, so an option added in one silently missed the rest.
    return ollama_generate(model_name, prompt, timeout=600)


def generate_grounded_answer(
    store: VectorStore, user_request: str, top_k: int = 5, model_id: str = "reasoning-model"
) -> GeneratedAnswer:
    """Answer `user_request`, grounded only in what `store` actually contains.

    This is the literal implementation of the NotebookLM-style trust
    claim: if retrieve_with_grounding_check (RAG_SPEC.md §3) can't find a
    confident match, this function returns the exact refusal text
    without ever calling the reasoning model at all — there is no
    prompt path by which an LLM can "helpfully" fill the gap from
    general knowledge when the corpus doesn't support an answer.
    """
    from backend.observability import turn_log as T

    T.section("RETRIEVAL")
    T.kv("request", repr(user_request))
    T.kv("top_k", top_k)
    with T.stage("hybrid search + grounding check"):
        grounding = retrieve_with_grounding_check(store, user_request, top_k)

    try:
        from backend.ingestion.embeddings import active_backend
        from backend.retrieval.grounded_retrieval import confidence_threshold

        T.kv("embedding backend", active_backend())
        T.kv("confidence threshold", f"{confidence_threshold():.3f}")
    except Exception:  # noqa: BLE001 — tracing must never break the turn
        pass

    T.kv("grounding.found", T.GREEN(str(grounding.found)) if grounding.found
         else T.YELLOW("False — will refuse"))
    T.kv("chunks returned", len(grounding.chunks))
    T.chunks_table(grounding.chunks)

    if not grounding.found:
        T.warn(f"REFUSING: best cosine {grounding.best_similarity} < "
               f"threshold {grounding.threshold}. No prompt sent to the model.")
        if grounding.near_miss_documents:
            T.note("  closest documents: " + ", ".join(grounding.near_miss_documents))
        return GeneratedAnswer(
            answer_text="Not found in the provided corpus.",
            found=False,
            sources=[],
            invalid_citations_stripped=[],
            unresolved_placeholders_stripped=0,
            near_miss_documents=grounding.near_miss_documents,
            best_similarity=grounding.best_similarity,
            threshold=grounding.threshold,
        )

    model_name = resolve_model_name(model_id)
    sources_text = _format_sources(grounding.chunks)
    prompt = _build_prompt(sources_text, user_request)

    T.section("GENERATION")
    T.kv("model id -> tag", f"{model_id} -> {model_name}")
    T.kv("prompt length", f"{len(prompt)} chars")
    T.kv("sources block", f"{len(sources_text)} chars, {len(grounding.chunks)} source(s)")
    T.block("PROMPT SENT TO MODEL", prompt, only_full=True)

    with T.stage(f"reasoning model ({model_name})"):
        raw_answer = _call_reasoning_model(prompt, model_name)

    T.block("RAW MODEL OUTPUT", raw_answer, only_full=True)

    T.section("CITATION VALIDATION")
    validation = validate_citations(raw_answer, num_retrieved_chunks=len(grounding.chunks))
    if validation.invalid_citation_numbers:
        T.warn(f"stripped invalid citations: {validation.invalid_citation_numbers} "
               f"(only {len(grounding.chunks)} source(s) were retrieved)")
    else:
        T.note(T.GREEN("all citation markers resolve to a retrieved source"))
    if getattr(validation, "unresolved_placeholder_count", 0):
        T.warn(f"stripped {validation.unresolved_placeholder_count} literal \"[N]\" placeholder(s)")

    T.section("FINAL ANSWER")
    T.answer_structure(validation.cleaned_text)
    T.block("ANSWER", validation.cleaned_text)

    return GeneratedAnswer(
        answer_text=validation.cleaned_text,
        found=True,
        sources=grounding.chunks,
        invalid_citations_stripped=validation.invalid_citation_numbers,
        unresolved_placeholders_stripped=validation.unresolved_placeholder_count,
    )
