"""Grounded answer generation — RAG_SPEC.md §4.

Ties together grounded_retrieval.py (§3's confidence gate), the exact
verbatim grounding-enforcement prompt (§4), and citation_validation.py
(§4's post-generation check) into the one function that actually answers
a user's question the way this system is supposed to: grounded, cited,
and willing to say "not found" instead of guessing.
"""

import requests
from pydantic import BaseModel

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
    invalid_citations_stripped: list[int]


def _format_sources(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        page_part = f", p.{chunk.page_number}" if chunk.page_number is not None else ""
        lines.append(f"[{i}] ({chunk.source_document}{page_part}) {chunk.text}")
    return "\n".join(lines)


def _build_prompt(sources_text: str, user_request: str) -> str:
    return f"{_GROUNDING_INSTRUCTIONS}{sources_text}\n\nREQUEST:\n{user_request}"


def _call_reasoning_model(prompt: str, model_name: str) -> str:
    response = requests.post(
        f"{_OLLAMA_HOST}/api/generate",
        json={"model": model_name, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"]


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
    grounding = retrieve_with_grounding_check(store, user_request, top_k)

    if not grounding.found:
        return GeneratedAnswer(
            answer_text="Not found in the provided corpus.",
            found=False,
            sources=[],
            invalid_citations_stripped=[],
        )

    model_name = resolve_model_name(model_id)
    sources_text = _format_sources(grounding.chunks)
    prompt = _build_prompt(sources_text, user_request)
    raw_answer = _call_reasoning_model(prompt, model_name)

    validation = validate_citations(raw_answer, num_retrieved_chunks=len(grounding.chunks))

    return GeneratedAnswer(
        answer_text=validation.cleaned_text,
        found=True,
        sources=grounding.chunks,
        invalid_citations_stripped=validation.invalid_citation_numbers,
    )
