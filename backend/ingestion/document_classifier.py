"""What KIND of document this is, and therefore how to process it.

TOOLS.md row 9. Distinct from document_types.py, which answers a
different question: that module reports the FORMAT (pdf, docx, png) by
reconciling the extension against the byte signature. This one reports
the KIND -- an SOP, an inspection report, a lab sheet, a P&ID -- which
is what decides the pipeline.

WHY THE PIPELINE DEPENDS ON IT. A scanned P&ID and a scanned inspection
checklist are both PNGs and both go to OCR, and after that they need
opposite treatment: the checklist is a table whose rows are findings,
the P&ID is a diagram whose value is the connections between tags.
Sending the diagram down the table path yields a column of stray
labels, and sending the checklist down the diagram path yields
relationships between nothing. Format alone cannot separate them.

WHY RULES, AND WHY THEY REPORT EVIDENCE.

A model could classify these, and on this hardware that costs a model
call per document at ingestion time -- on a corpus of any size, the
dominant cost of ingesting it. Worse, it would be unexplainable: an
operator asking "why was my document treated as correspondence" would
get no answer. Every classification here names the phrases it matched,
so a wrong one can be corrected by looking at it.

UNKNOWN IS A REAL ANSWER. A document that matches nothing is returned
as `unknown` with the generic pipeline, not as the best of a bad set.
Forcing a guess is how a P&ID ends up parsed as a spreadsheet: the
system was never in doubt, so nothing downstream knew to be careful.

CONFIDENCE IS NOT A PROBABILITY, and is not presented as one. It is the
margin between the winning class and the runner-up, normalised. A
document that matches two classes almost equally is genuinely ambiguous
and says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# How each class is handled downstream. This is the reason the classifier
# exists, so it travels with the answer rather than being looked up
# somewhere else and drifting.
PIPELINES = {
    "sop_procedure": "text + step segmentation; keep numbered steps contiguous",
    "inspection_report": "text + table extraction; findings are rows",
    "maintenance_log": "tabular; each row is an event with a date",
    "lab_quality_data": "tabular; values compared against spec limits",
    "sap_export": "tabular; treat as structured records, not prose",
    "correspondence": "thread segmentation; who said what, and any action requested",
    "diagram_schematic": "vision + graph extraction; tags and the connections between them",
    "scanned_form": "OCR + table extraction; a form is a table with a checklist",
    "unknown": "generic text pipeline",
}


@dataclass
class DocumentClass:
    kind: str
    confidence: float
    pipeline: str
    # The phrases that decided it. An unexplainable classification
    # cannot be corrected by the person it is wrong for.
    evidence: list[str] = field(default_factory=list)
    runner_up: str | None = None

    @property
    def is_confident(self) -> bool:
        return self.kind != "unknown" and self.confidence >= 0.5


# Signals per class. Weighted: a document NUMBER is far stronger
# evidence than a bare topic word, because numbering schemes are how
# these document sets are actually organised.
_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "sop_procedure": [
        (r"\bSOP[-\s]?\d", 5),
        (r"\bstandard\s+operating\s+procedure\b", 5),
        (r"\brev(?:ision)?\s*[-.]?\s*\d", 2),
        (r"\bwork\s+instruction\b", 3),
        (r"\bsafety\s+circular\b", 4),
        (r"\bprocedure\b", 1),
        (r"\bstep\s+\d+\b", 1),
        (r"\bprecautions?\b", 1),
        (r"\bscope\s+and\s+purpose\b", 2),
    ],
    "inspection_report": [
        (r"\binspection\s+report\b", 5),
        (r"\bincident\s+report\b", 5),
        (r"\breport\s+no\.?\s*[:#]?\s*\w", 3),
        (r"\bfindings?\b", 2),
        (r"\bobservations?\b", 1),
        (r"\binspected\s+by\b", 3),
        (r"\broot\s+cause\b", 2),
        (r"\bcorrective\s+action\b", 2),
    ],
    "maintenance_log": [
        (r"\bmaintenance\s+log\b", 5),
        (r"\bwork\s+order\b", 3),
        (r"\bdowntime\b", 2),
        (r"\bequipment\s+tag\b", 2),
        (r"\bbreakdown\b", 1),
        (r"\bpreventive\s+maintenance\b", 3),
    ],
    "lab_quality_data": [
        (r"\blab(?:oratory)?\s+(?:sheet|report|result)", 5),
        (r"\bbatch\s+(?:qa|quality|report)\b", 4),
        (r"\bspec(?:ification)?\s+limits?\b", 3),
        (r"\bwithin\s+spec\b", 3),
        (r"\bmfi\b", 2),
        (r"\bpurity\b", 2),
        (r"\bsulphur|sulfur\b", 1),
        (r"\bppm\b", 1),
        (r"\btest\s+method\b", 2),
        (r"\btrend\s+log\b", 4),
        (r"\btarget\s*\(%\)", 3),
    ],
    "sap_export": [
        (r"\bsap\b", 4),
        (r"\bmaterial\s+master\b", 5),
        (r"\bplant\s+code\b", 3),
        (r"\bmovement\s+type\b", 3),
        (r"\bpurchase\s+requisition\b", 3),
        (r"\bmaterial\s+(?:no|number|code)\b", 2),
    ],
    "correspondence": [
        (r"\bcorrespondence\b", 4),
        (r"\bthread\s+id\b", 4),
        (r"\bfrom\s*:.*\bto\s*:", 4),
        (r"\bsubject\s*:", 3),
        (r"\bdear\s+(?:sir|madam|mr|ms)\b", 3),
        (r"\bregards\b", 2),
        (r"\bemail\b", 1),
        (r"\bawaiting\s+your\b", 2),
    ],
    "diagram_schematic": [
        (r"\bp\s*&\s*id\b", 5),
        (r"\bpiping\s+and\s+instrument", 5),
        (r"\bschematic\b", 4),
        (r"\bsegment\s+map\b", 4),
        (r"\blegend\b", 1),
        (r"\bline\s+no\.?\b", 2),
        (r"\bdrawing\s+no\.?\b", 3),
    ],
    "scanned_form": [
        (r"\bchecklist\b", 5),
        (r"\bsign(?:ed|ature)\s*(?:off)?\b", 1),
        (r"\btick\b|\[\s*[xX✓]\s*\]", 2),
        (r"\byes\s*/\s*no\b", 2),
        (r"\bcompleted\s+by\b", 2),
    ],
}

_COMPILED = {
    kind: [(re.compile(pattern, re.I), weight) for pattern, weight in signals]
    for kind, signals in _SIGNALS.items()
}

# The filename carries real signal and is treated as such, but it is
# weaker than content while there IS content: a file can be renamed.
_FILENAME_WEIGHT = 2

# Below this total score nothing is claimed. A single weak topic word is
# not a classification.
_MIN_SCORE = 4

# A signal appearing repeatedly is stronger evidence than one appearing
# once, up to a point.
#
# MEASURED, on PSA_Hydrogen_Purity_Trend_Log.xlsx. It is a purity trend
# table followed by a small downtime-cause table, so it matched
# "purity" (lab) and "downtime" (maintenance) once each under binary
# scoring, tied at 2, and came out UNKNOWN. But "Purity (%)" is five
# column headers and "Downtime" is one row label -- the document is
# plainly about purity, and counting says so while presence does not.
#
# Capped at three, because past that the count says more about document
# length than about subject.
_MAX_COUNTED = 3

# When a document has NO TEXT YET -- an image before OCR -- the filename
# is not weak evidence, it is the ONLY evidence, and the classification
# still matters: this is exactly the case row 9 exists for, since
# "diagram" and "scanned form" are both PNGs that need opposite
# handling. So the filename scores at full weight there, and the result
# says plainly that it came from the filename alone and carries a
# capped confidence. A caller re-running this after OCR gets a better
# answer; one routing an un-OCR'd scan gets a usable one instead of
# nothing.
_FILENAME_ONLY_CONFIDENCE_CAP = 0.4


def classify_document(text: str, filename: str = "") -> DocumentClass:
    """The kind of document this is, with the evidence that decided it.

    Args:
        text: the document's extracted text. May be empty for an image
            that has not been OCR'd, in which case the filename and the
            format are all there is.
        filename: the file's name, used as weaker corroborating
            evidence.

    Returns:
        DocumentClass, with `kind` "unknown" when nothing matched
        strongly enough. Unknown is a real answer -- forcing a guess is
        how a P&ID ends up parsed as a spreadsheet.
    """
    haystack = text or ""
    name = Path(filename or "").stem.replace("_", " ").replace("-", " ")
    # No text at all means this is an image that has not been OCR'd.
    text_only_from_name = not haystack.strip()
    filename_cap = weight_cap = None if text_only_from_name else _FILENAME_WEIGHT

    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}

    for kind, signals in _COMPILED.items():
        total = 0
        matched: list[str] = []
        for pattern, weight in signals:
            hits = pattern.findall(haystack) if haystack else []
            if hits:
                total += weight * min(len(hits), _MAX_COUNTED)
                first = pattern.search(haystack)
                label = first.group(0).strip()[:40] if first else pattern.pattern[:28]
                matched.append(f"{label} x{len(hits)}" if len(hits) > 1 else label)
            elif name and pattern.search(name):
                total += weight if filename_cap is None else min(weight, filename_cap)
                matched.append(f"filename: {pattern.pattern[:28]}")
        if total:
            scores[kind] = total
            evidence[kind] = matched[:6]

    if not scores:
        return DocumentClass("unknown", 0.0, PIPELINES["unknown"], [])

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner_up, runner_score = (ranked[1] if len(ranked) > 1 else (None, 0))

    if best_score < _MIN_SCORE:
        return DocumentClass(
            "unknown",
            0.0,
            PIPELINES["unknown"],
            evidence.get(best, []),
            runner_up=best,
        )

    if text_only_from_name:
        # Said plainly rather than presented as a reading of the
        # document, because it is not one.
        margin = (best_score - runner_score) / best_score
        return DocumentClass(
            kind=best,
            confidence=round(min(margin, _FILENAME_ONLY_CONFIDENCE_CAP), 2),
            pipeline=PIPELINES[best],
            evidence=["classified from the filename alone (no text yet)"]
            + evidence.get(best, []),
            runner_up=runner_up,
        )

    # Confidence is the MARGIN over the runner-up, not a probability and
    # not presented as one. Two classes matching almost equally means
    # the document is genuinely ambiguous, and saying so is more useful
    # than a number that looks decisive.
    confidence = round((best_score - runner_score) / best_score, 2)

    return DocumentClass(
        kind=best,
        confidence=confidence,
        pipeline=PIPELINES[best],
        evidence=evidence.get(best, []),
        runner_up=runner_up,
    )
