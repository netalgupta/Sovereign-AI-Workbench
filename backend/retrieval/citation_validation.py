"""Post-generation citation validation — RAG_SPEC.md §4.

Grounding a prompt in retrieved sources doesn't guarantee the model
actually cites them correctly — it can still invent a citation number
that was never in the sources list (a "[7]" when only 5 chunks were
retrieved), or cite [3] for a claim that chunk never supported. This
module catches the first failure mode mechanically (the second — does
the cited text actually support the claim — needs a semantic check,
out of scope for this pass and not what RAG_SPEC.md §4 asks for here).
"""

import re

from pydantic import BaseModel

_CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")


class CitationValidationResult(BaseModel):
    valid_citation_numbers: list[int]
    invalid_citation_numbers: list[int]  # cited but out of range for the sources actually retrieved
    cleaned_text: str  # invalid citation markers stripped; valid ones left as-is


def validate_citations(generated_text: str, num_retrieved_chunks: int) -> CitationValidationResult:
    """Check every `[N]` marker in `generated_text` against how many
    sources were actually retrieved (sources are numbered 1..N per
    RAG_SPEC.md §4's prompt template, `{retrieved_chunks_formatted_with_numbers}`).

    Per RAG_SPEC.md §4: "if an invalid citation number is found, either
    strip that claim or flag it for human review before it reaches the
    approval-note generator; do not silently pass it through." This
    function does the mechanical half — stripping the invalid marker
    from the text and reporting exactly which numbers were invalid, so
    the caller can flag the surrounding claim for human review rather
    than silently keep a citation pointing at a source that doesn't exist.
    """
    cited_numbers = [int(match.group(1)) for match in _CITATION_MARKER_PATTERN.finditer(generated_text)]

    valid = sorted({n for n in cited_numbers if 1 <= n <= num_retrieved_chunks})
    invalid = sorted({n for n in cited_numbers if not (1 <= n <= num_retrieved_chunks)})

    def _strip_invalid(match: re.Match) -> str:
        n = int(match.group(1))
        return match.group(0) if 1 <= n <= num_retrieved_chunks else ""

    cleaned_text = _CITATION_MARKER_PATTERN.sub(_strip_invalid, generated_text)

    return CitationValidationResult(
        valid_citation_numbers=valid,
        invalid_citation_numbers=invalid,
        cleaned_text=cleaned_text,
    )
