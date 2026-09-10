"""Post-generation citation validation — RAG_SPEC.md §4.

Grounding a prompt in retrieved sources doesn't guarantee the model
actually cites them correctly — it can still invent a citation number
that was never in the sources list (a "[7]" when only 5 chunks were
retrieved), or cite [3] for a claim that chunk never supported. This
module catches the first failure mode mechanically (the second — does
the cited text actually support the claim — needs a semantic check,
out of scope for this pass and not what RAG_SPEC.md §4 asks for here).

Real bug found running this against the MRPL corpus, not by re-reading
the code: RAG_SPEC.md §4's own locked, verbatim-required prompt text
describes the citation format using the literal string "[N]" ("include
a citation marker [N] referring to the source number") — and a model
can echo that placeholder literally instead of substituting a real
digit (observed once for real: Q1 of the corpus test set answered
correctly, sourced correctly, but ended with a bare "[N]" instead of
"[1]"). Because `[N]` isn't numeric, the original digit-only pattern
below silently let it through — neither validated as correct nor
flagged as wrong, exactly what RAG_SPEC.md §4's "do not silently pass
it through" rule exists to prevent. `_UNRESOLVED_PLACEHOLDER_PATTERN`
below catches this narrow, specific shape (a single uppercase letter in
brackets — real citations are always `[<digits>]`, never a bare
letter) without risking false positives on unrelated bracketed text.
"""

import re

from pydantic import BaseModel

_CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")

# Matches an unresolved placeholder like "[N]" -- see module docstring.
# Deliberately narrow (a single uppercase letter only) so it can't
# false-positive on some unrelated bracketed abbreviation in real text.
_UNRESOLVED_PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z])\]")


class CitationValidationResult(BaseModel):
    valid_citation_numbers: list[int]
    invalid_citation_numbers: list[int]  # cited but out of range for the sources actually retrieved
    unresolved_placeholder_count: int  # e.g. a literal "[N]" the model never substituted a real number into
    cleaned_text: str  # invalid citation markers AND unresolved placeholders stripped; valid ones left as-is


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

    unresolved_matches = _UNRESOLVED_PLACEHOLDER_PATTERN.findall(cleaned_text)
    cleaned_text = _UNRESOLVED_PLACEHOLDER_PATTERN.sub("", cleaned_text)

    return CitationValidationResult(
        valid_citation_numbers=valid,
        invalid_citation_numbers=invalid,
        unresolved_placeholder_count=len(unresolved_matches),
        cleaned_text=cleaned_text,
    )
