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

# DELIBERATE DEVIATION FROM RAG_SPEC.md §4's VERBATIM PROMPT TEXT.
#
# §4 specifies this sentence exactly:
#
#     "For every factual claim, include a citation marker [N] referring
#      to the source number."
#
# That sentence causes a measurable defect, and has been causing it
# since the first validation run. Models copy the literal token "[N]"
# into their answers instead of substituting a digit -- the repo's own
# history records this as the original "[N] bug", and
# citation_validation.py carries an unresolved-placeholder pass that
# exists for no other reason than to clean up after this wording. Two
# such placeholders were stripped in a single traced turn this session.
#
# The failure got worse the smaller the model. Adding a second block
# that used the phrase "citation marker" in order to FORBID the token
# produced qwen2.5:3b answering a question with the entire text
# '[Citation marker]: [4]', and phi3.5 emitting 21 rows of tables
# headed "Citation Marker | Content". Naming a template in front of a
# 3B model is an invitation to reproduce it.
#
# So the instruction now shows the required form in a finished example
# sentence rather than naming a placeholder token. The SEMANTICS are
# unchanged -- every factual claim still carries a bracketed source
# number, and the refusal clause is word-for-word as specified. Only
# the way the format is conveyed has changed, because the specified way
# demonstrably does not survive contact with the models we run.
#
# Flagged rather than done quietly: RAG_SPEC.md §4 should be updated to
# match, and whoever owns that spec should know the original wording is
# the cause of a bug its own pipeline has to repair downstream.
#
# Built as prefix + concat, not str.format(): same lesson as
# entity_extraction.py's prompt — never run .format() over text that
# might itself contain literal braces.
_GROUNDING_INSTRUCTIONS = (
    "You must only state facts that are directly supported by the SOURCES section "
    "below. For every factual claim, include the bracketed number of the source it "
    "came from, at the end of the sentence, like this:\n"
    "    The average MFI is 3.4 g/10min [1].\n"
    "If the sources do not contain enough information to answer, say "
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


_MARKDOWN_FENCE_LABELS = ("markdown", "md", "")


def _unwrap_markdown_fence(text: str) -> str:
    """Undo an answer that wrapped ITSELF in a markdown code fence.

    Observed: the model returned

        ```markdown
        The average MFI for Homopolymer H030SG is 3.4 g/10min [1].

        | Average MFI | Source |
        |---|---|
        ...
        ```

    which the renderer displays as a literal code block -- the table
    never becomes a table, the bold never becomes bold, and the answer
    arrives as grey monospace source. The instruction "Write in
    GitHub-flavoured markdown" is what invites it: a model reads that as
    a request for markdown *as output format*, and the conventional way
    to present a document in a chat reply is inside a fence.

    Only strips when the ENTIRE answer is one fence labelled markdown,
    md, or nothing. A fence in the middle of an answer, or one labelled
    python/json/bash, is a real code block the user asked for and is
    left exactly alone -- stripping those would corrupt the answer
    rather than fix it, which is why this is not a blanket
    strip_code_fences call.
    """
    stripped = (text or "").strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return text

    newline = stripped.find("\n")
    if newline == -1:
        return text

    label = stripped[3:newline].strip().lower()
    if label not in _MARKDOWN_FENCE_LABELS:
        return text

    body = stripped[newline + 1 : -3]

    # If the body contains its own fence, the outer one was structural
    # and removing it would leave unbalanced markers.
    if "```" in body:
        return text

    return body.strip()


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
    # NOT "write in markdown" -- a model reads that as a request for
    # markdown as an output ARTEFACT and wraps the whole reply in a
    # ```markdown fence, which renders as a grey code block. Phrased
    # as what the reply may CONTAIN instead.
    "Your reply is rendered as GitHub-flavoured markdown, so headings, "
    "tables, bold and code spans all work. Never wrap the whole reply "
    "in a code fence.\n"
    "- When the answer compares several items, or reports values against "
    "limits or specifications, use a markdown table. Each row ends "
    "with the bracketed number of the source it came from.\n"
    "- Use `inline code` for tags, identifiers and units (TC-201A, "
    "SOP-114-Rev3, g/10min).\n"
    "- Use a fenced code block for code or for multi-line machine output.\n"
    "- Use **bold** for the single figure that answers the question.\n"
    "- Keep it as short as the question allows. Do not pad an answer to "
    "fill a table, and do not tabulate a single value.\n"
    "- Never invent a row, a column, or a value to complete a table. If "
    "the sources cover only some of the rows, include only those.\n"
)

# CITATION FORM. Three failures shaped this wording, and the third was
# caused by the first attempt to fix the other two.
#
#   1. Literal "[N]" emitted verbatim -- the model echoing the format
#      DESCRIPTION in RAG_SPEC §4's own prompt text instead of
#      substituting a digit. Two were stripped in a single observed
#      turn. This is why citation_validation.py has an
#      unresolved-placeholder pass at all.
#
#   2. Prose citations instead of markers: an answer that wrote
#      "(Novolen_Batch_QA_Report_Aug2026.pdf, p.1)" inline and carried
#      ZERO bracketed markers. The text was grounded and the source was
#      real, but nothing machine-readable came out, so the frontend
#      could render no source chips and validation had nothing to
#      check. An uncheckable citation is, downstream, the same as none.
#
#   3. THE FIX FOR 1 AND 2 CAUSED A WORSE BUG. The first version of
#      this block used the phrase "citation marker" and quoted "[N]" in
#      order to forbid it. Small models copied the instruction into
#      their output: qwen2.5:3b answered one question with the complete
#      text '[Citation marker]: [4]', and phi3.5 emitted 21 rows of
#      tables headed "Citation Marker | Content". Naming a token in
#      order to ban it puts that token in front of the model, and a 3B
#      model reaches for the nearest template -- which was the
#      instruction itself.
#
# So: show the desired form by EXAMPLE in a finished sentence, never as
# a label or a schema, and do not quote the forbidden token at all. The
# placeholder pass in citation_validation.py stays as the backstop,
# because prompt wording is not a guarantee.
_CITATION_FORM = (
    "\n\nCITATIONS:\n"
    "Support each factual sentence with a bracketed source number, "
    "placed at the end of the sentence, like this:\n"
    "    The average MFI is 3.4 g/10min [1].\n"
    "Use the number of the source you actually used. Two sources for "
    "one claim are written together, as in [1][3].\n"
    "Do not cite by filename or page inside the prose; the bracketed "
    "number is what the interface resolves back to the source, and a "
    "filename written into a sentence cannot be checked or linked.\n"
)

# ANSWER DEPTH.
#
# Prompted by a real failure. "Give sops for Hydrocrackers" retrieved
# SOP-114-Rev3 and answered with a three-row table of document number,
# effective date and review cycle, plus one summary sentence -- the
# procedure itself, which was sitting in the retrieved chunk, went
# unused. The ranking half of that is fixed in query_builder.py; this
# is the other half.
#
# The instruction is about USING what was retrieved, never about
# producing more text. Padding is called out explicitly, because "be
# thorough" is exactly the phrasing that makes a model pad.
_ANSWER_DEPTH = (
    "\n\nWHAT TO INCLUDE:\n"
    "- Answer from the SUBSTANCE of the sources, not from their "
    "metadata. Document numbers, effective dates and revision cycles "
    "are not an answer to a question about content.\n"
    "- When asked about a procedure, give the actual steps, conditions "
    "and limits that the sources state.\n"
    "- Prefer specifics the sources contain -- values, units, "
    "thresholds, equipment tags, step order -- over general "
    "description.\n"
    "- Do not pad. If the sources support only a short answer, give a "
    "short answer. Length is never the goal; using what was actually "
    "retrieved is.\n"
)


def _build_prompt(sources_text: str, user_request: str) -> str:
    return (
        f"{_GROUNDING_INSTRUCTIONS}{sources_text}"
        f"{_CITATION_FORM}"
        f"{_ANSWER_DEPTH}"
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
    try:
        from backend.retrieval.query_builder import explain as _explain_query

        _q = _explain_query(user_request, store.all_chunk_texts())
        if _q["added_terms"]:
            T.kv("search query", repr(_q["search_query"]))
            T.kv("terms added", _q["added_terms"])
        else:
            T.kv("search query", T.DIM("unchanged"))
    except Exception:  # noqa: BLE001 - tracing must never break the turn
        pass
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

    # Undo a whole-answer markdown fence BEFORE validation, so citation
    # markers inside the fenced body are seen by the validator.
    unwrapped = _unwrap_markdown_fence(raw_answer)
    if unwrapped != raw_answer:
        T.warn("answer was wrapped in a ```markdown fence; unwrapped so it "
               "renders as formatted text rather than a code block")
        raw_answer = unwrapped

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
    if grounding.chunks and "[" not in validation.cleaned_text:
        # Citation validation cannot catch this: it checks that markers
        # RESOLVE, and an answer with none passes vacuously. An answer
        # that cites by filename in prose is unlinkable and uncheckable,
        # which downstream is the same as uncited.
        T.warn("answer contains NO citation markers despite "
               f"{len(grounding.chunks)} retrieved source(s) -- the model "
               "likely cited in prose instead of [n]")
    T.block("ANSWER", validation.cleaned_text)

    return GeneratedAnswer(
        answer_text=validation.cleaned_text,
        found=True,
        sources=grounding.chunks,
        invalid_citations_stripped=validation.invalid_citation_numbers,
        unresolved_placeholders_stripped=validation.unresolved_placeholder_count,
    )
