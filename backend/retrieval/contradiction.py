from __future__ import annotations

"""Contradiction detection across documents — TOOLS.md row 15 (🟡),
Aryan.md Day 8.

Two documents in a refinery's corpus stating different values for the
same limit is a safety problem, and it is invisible to ordinary
retrieval: whichever chunk ranks higher wins, the other is never shown,
and the answer is confidently sourced from one of two documents that
disagree.

WHAT MAKES THIS HARD IS THE FALSE POSITIVES, NOT THE DETECTION.
Finding two different numbers for the same phrase is easy. Doing it
without crying wolf is the whole job, because a detector that flags
legitimate variation gets switched off within a day and then catches
nothing. Four kinds of "different numbers" are NOT contradictions:

  1. DIFFERENT UNITS FOR THE SAME QUANTITY. "10 ppm" and "0.001 %" are
     the same limit. Comparing the numerals would flag it. Values are
     therefore converted through Pint before comparison — a real use of
     the unit tool rather than a decorative one.

  2. READINGS versus LIMITS. "sulphur was 8.9 ppm" and "sulphur limit is
     10 ppm" are consistent, and in fact one is evidence about the
     other. Claims carry a `kind`, and only like is compared with like.

  3. TIME SERIES. Two dated readings of the same tag are a trend, not a
     disagreement. A claim with a date is never contradicted by a claim
     with a different date.

  4. DIFFERENT SUBJECTS THAT SHARE A WORD. "HCU-2 WABT" and "HCU-3 WABT"
     are different equipment. Subject matching is on the normalized
     whole subject, never a substring — the same lesson as
     entity_extraction.py's MIN_FUZZY_MATCH_LENGTH, where a single
     letter matched everything.

WHY EXTRACTION IS INJECTABLE. The default extractor is deterministic
pattern matching over the phrasings refinery documents actually use. An
LLM extractor can be passed instead for better recall, but it is not the
default: a contradiction report is a safety artifact, and one whose
contents change between runs on identical input is not one anybody can
act on. Comparison itself is always deterministic — no model decides
whether two values disagree.
"""

import re
from typing import Callable, Literal

from pydantic import BaseModel

ClaimKind = Literal["limit", "reading", "setpoint", "unknown"]

# Phrasings that mark a claim as a LIMIT rather than a measurement.
# Ordered most-specific first; the first match wins, because "shall not
# exceed" is a limit even though the sentence also contains "is".
_LIMIT_MARKERS = (
    "shall not exceed", "must not exceed", "not to exceed", "maximum",
    "max ", "minimum", "min ", "limit", "spec ", "specification",
    "threshold", "target", "end-of-run", "trigger",
)
_READING_MARKERS = (
    "measured", "recorded", "observed", "reading", "was ", "reached",
    "logged", "sampled", "actual",
)

# A number with an optional unit. Deliberately narrow: it matches a
# figure followed by a recognisable unit token, rather than every number
# in the text. Matching bare integers would pull in revision numbers,
# page numbers and equipment tags, and a report full of those is noise.
_VALUE_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ppm|ppb|%|percent|bar(?:g|a)?|kpa|mpa|psi(?:g|a)?|"
    r"deg\s?c|degc|°c|celsius|deg\s?f|degf|°f|"
    r"kg/h|kg/hr|t/h|t/d|tpd|nm3/h|nm\*\*3/h|m3/h|"
    r"hours?|hrs?|minutes?|mins?|days?)\b",
    re.IGNORECASE,
)

# A date in any of the forms this corpus uses. Its presence makes a claim
# temporal, and temporal claims never contradict one another.
_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})\b",
    re.IGNORECASE,
)

# Unit spellings that Pint does not accept as written.
_UNIT_ALIASES = {
    "degc": "degC", "deg c": "degC", "°c": "degC", "celsius": "degC",
    "degf": "degF", "deg f": "degF", "°f": "degF",
    "percent": "percent", "%": "percent",
    "kg/hr": "kg/hour", "kg/h": "kg/hour",
    "hrs": "hour", "hr": "hour", "hours": "hour", "mins": "minute",
    "nm**3/h": "m**3/hour", "nm3/h": "m**3/hour", "m3/h": "m**3/hour",
    "barg": "bar", "bara": "bar", "psig": "psi", "psia": "psi",
    "t/d": "tonne/day", "tpd": "tonne/day", "t/h": "tonne/hour",
}


# How much context around a figure identifies what it is about.
# Asymmetric: English places the subject before the number.
_SUBJECT_WORDS_BEFORE = 6
_SUBJECT_WORDS_AFTER = 2


class Claim(BaseModel):
    subject: str  # what the claim is about, e.g. "kero merox sulphur"
    value: float
    unit: str
    kind: ClaimKind
    source_document: str
    sentence: str
    has_date: bool = False


class Contradiction(BaseModel):
    subject: str
    kind: ClaimKind
    claims: list[Claim]
    values_seen: list[str]
    severity: Literal["high", "medium"]
    explanation: str


def _normalize_subject(text: str) -> str:
    """The phrase a claim is about, normalized for comparison.

    Equipment tags are preserved (V-204 stays V-204) because they are
    exactly what distinguishes one subject from another. Stopwords and
    the claim's own marker words are dropped so that "the maximum WABT
    for HCU-2" and "HCU-2 WABT" match.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-/ ]+", " ", text)
    drop = set(_LIMIT_MARKERS) | set(_READING_MARKERS) | {
        "the", "a", "an", "of", "for", "is", "are", "at", "on", "to", "be",
        "shall", "must", "not", "exceed", "this", "that", "it", "value",
    }
    words = [w for w in text.split() if w and w not in drop and not w.isdigit()]
    return " ".join(words).strip()


def _classify(sentence: str) -> ClaimKind:
    lowered = sentence.lower()
    for marker in _LIMIT_MARKERS:
        if marker in lowered:
            return "limit"
    for marker in _READING_MARKERS:
        if marker in lowered:
            return "reading"
    return "unknown"


def _to_pint_unit(unit: str) -> str:
    key = unit.strip().lower()
    return _UNIT_ALIASES.get(key, key)


def extract_claims_by_pattern(text: str, source_document: str) -> list[Claim]:
    """Deterministic claim extraction over the phrasings these documents use.

    Sentence-level: a claim's subject is the rest of its own sentence,
    which is what keeps "HCU-2 WABT" attached to its number instead of
    drifting to a neighbouring one.
    """
    claims: list[Claim] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        for match in _VALUE_PATTERN.finditer(sentence):
            # A BOUNDED WINDOW around the value, not the whole sentence.
            # Measured on the real corpus: whole-sentence subjects work
            # for short declaratives ("The sulphur limit is 10 ppm" ->
            # "sulphur") but collapse on long ones, producing subjects
            # like "short-term exposure stel ppm area evacuation personal
            # monitoring ..." — twenty words of noise that two documents
            # would have to phrase identically to ever match. Since
            # matching across documents is the entire point, a subject
            # that cannot match is a claim that cannot be checked.
            #
            # Asymmetric because English puts the subject before the
            # figure ("benzene TWA limit is 1 ppm"), so what follows is
            # usually qualification rather than identity.
            before = sentence[: match.start()].split()[-_SUBJECT_WORDS_BEFORE:]
            after = sentence[match.end() :].split()[:_SUBJECT_WORDS_AFTER]
            subject = _normalize_subject(" ".join(before + after))
            if not subject:
                continue
            claims.append(
                Claim(
                    subject=subject,
                    value=float(match.group("value")),
                    unit=_to_pint_unit(match.group("unit")),
                    kind=_classify(sentence),
                    source_document=source_document,
                    sentence=sentence,
                    has_date=bool(_DATE_PATTERN.search(sentence)),
                )
            )
    return claims


def values_are_equivalent(a: Claim, b: Claim) -> bool:
    """Do two claims state the SAME quantity, allowing for units?

    "10 ppm" and "0.001 %" are the same limit, and flagging that pair
    would be the kind of false positive that gets the whole detector
    switched off. Conversion goes through Pint; if the two units are not
    convertible at all (ppm against degC), the claims are about different
    quantities and cannot contradict each other either.
    """
    # Relative tolerance, applied to BOTH paths. An earlier version used
    # an absolute 1e-9 for same-unit pairs and a relative 1e-6 across
    # units, which made the same-unit comparison the STRICTER of the two —
    # backwards. It flagged "1.0 bar" against "0.9999999 bar" while
    # accepting "1.0 bar" against "99.99999 kPa", so whether a
    # precision artifact was reported depended on how the two documents
    # happened to write their units.
    #
    # 1e-6 relative is far below any real disagreement in a process
    # document (10 ppm against 10.1 ppm is 1% apart and is still caught)
    # while absorbing float noise and trailing-digit differences.
    def _close(x: float, y: float) -> bool:
        return abs(x - y) / max(abs(x), abs(y), 1e-9) < 1e-6

    if a.unit == b.unit:
        return _close(a.value, b.value)

    try:
        from backend.tools.math.unit_calc import evaluate_unit_expression

        result = evaluate_unit_expression(f"({a.value} {a.unit}) - ({b.value} {b.unit})")
        difference = float(getattr(result, "value", 0.0))
        scale = max(abs(a.value), abs(b.value), 1e-9)
        return abs(difference) / scale < 1e-6
    except Exception:  # noqa: BLE001 — incompatible units are not a contradiction
        return True


def find_contradictions(
    chunks,
    extract_fn: Callable[[str, str], list[Claim]] | None = None,
    min_documents: int = 2,
) -> list[Contradiction]:
    """Find claims that disagree about the same thing.

    Args:
        chunks: ingested or retrieved chunks. Anything with `.text` and
            either `.source_document` or `.metadata.source_document`.
        extract_fn: (text, source_document) -> claims. Defaults to the
            deterministic pattern extractor; pass an LLM-backed one for
            better recall at the cost of reproducibility.
        min_documents: a contradiction must span at least this many
            DOCUMENTS. Two differing numbers inside one document are
            usually a table of readings, not a disagreement — and a
            document is free to contradict itself in ways only its author
            can resolve.
    """
    extractor = extract_fn or extract_claims_by_pattern

    claims: list[Claim] = []
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None)
        source = (
            getattr(metadata, "source_document", None)
            or getattr(chunk, "source_document", None)
            or "unknown"
        )
        claims.extend(extractor(getattr(chunk, "text", ""), source))

    grouped: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        # Only like is compared with like: a reading never contradicts a
        # limit, and a dated reading is part of a series rather than a
        # competing assertion.
        if claim.has_date:
            continue
        grouped.setdefault((claim.subject, claim.kind), []).append(claim)

    contradictions: list[Contradiction] = []
    for (subject, kind), group in grouped.items():
        if len({c.source_document for c in group}) < min_documents:
            continue

        conflicting: list[Claim] = []
        for claim in group:
            if not any(values_are_equivalent(claim, other) for other in conflicting):
                conflicting.append(claim)
        if len(conflicting) < 2:
            continue
        if len({c.source_document for c in conflicting}) < min_documents:
            continue

        # A disagreement about a LIMIT is the dangerous case: someone
        # will operate to whichever one they read. Anything else is
        # reported, but not at the same volume.
        severity = "high" if kind == "limit" else "medium"
        documents = sorted({c.source_document for c in conflicting})

        contradictions.append(
            Contradiction(
                subject=subject,
                kind=kind,
                claims=conflicting,
                values_seen=[f"{c.value:g} {c.unit}" for c in conflicting],
                severity=severity,
                explanation=(
                    f"{len(documents)} documents state different "
                    f"{'limits' if kind == 'limit' else 'values'} for \"{subject}\": "
                    + "; ".join(f"{c.value:g} {c.unit} ({c.source_document})" for c in conflicting)
                    + (
                        ". Operating to the wrong one is a safety risk — resolve which "
                        "document is authoritative before relying on either."
                        if kind == "limit"
                        else ". Check which is current."
                    )
                ),
            )
        )

    # Highest-stakes first: a limit disagreement buried under a list of
    # medium findings is a limit disagreement nobody reads.
    contradictions.sort(key=lambda c: (c.severity != "high", c.subject))
    return contradictions
