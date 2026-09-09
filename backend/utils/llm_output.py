"""Shared helpers for parsing raw LLM text output.

Extracted here because two different callers ended up needing the exact
same "strip a markdown code fence off an LLM's response before parsing
it as JSON" logic — router.py (CARD 03) originally, entity_extraction.py
(GRAPH_SPEC.md §5) next. Local models over Ollama routinely wrap JSON
output in ```json ... ``` fences even when explicitly told not to;
every caller that parses structured JSON from a local model's raw text
output needs this same normalization step, so it belongs in one shared
place, not copied per module.
"""

import re

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Strip a leading/trailing ```json ... ``` or ``` ... ``` fence, if
    present. Returns `text` unchanged (just whitespace-trimmed) if there
    is no fence to strip.
    """
    text = text.strip()
    match = _FENCE_PATTERN.match(text)
    return match.group(1).strip() if match else text
