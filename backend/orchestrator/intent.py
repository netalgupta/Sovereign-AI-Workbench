"""What kind of request is this, before any expensive machinery runs.

THE PROBLEM. "HolA aMIGO" took 46.56 seconds and produced a refusal.

The trace shows the whole pipeline ran on it: the LLM planner (10.5s,
which then failed to parse), a three-step fallback plan about
"operational parameters and safety envelopes", a corpus search, and a
grounding refusal naming the three documents that came closest to
matching a Spanish greeting.

Nothing there was wrong individually. Every stage did its job. The
mistake was upstream: a greeting was handed to a pipeline built for
grounded document questions, because nothing looked at it first.

This costs more than time. A user who says hello and waits 46 seconds
for "not found in the corpus" learns the product is broken, and they
learn it in the first ten seconds of a demo.

WHAT THIS IS NOT. It is not a chatbot layer bolted on the side, and it
must never answer a question about the plant. The whole value of this
system is that factual claims come from documents with citations.
Intents that could touch plant data go straight to retrieval, exactly
as before. What is peeled off here is the small set of requests that
provably need no corpus at all:

    greeting        "hola", "hey there", "good morning"
    capability      "what can you do", "how do you work"
    arithmetic      "what is 47 * 3.2", "convert 5 bar to kPa"
    thanks/bye      "thanks", "that's all"

Each is answered from something real -- the live tool registry, an
executed calculation, or a fixed honest sentence -- never from a model
guessing.

WHY RULES AND NOT A CLASSIFIER MODEL. A model call to decide whether
"hi" is a greeting costs as much as answering a real question, and adds
a failure mode where the classifier itself is wrong or unreachable. The
signals here are short, closed and structural. FAILS TOWARDS THE FULL
PIPELINE: anything not clearly in one of these classes is treated as a
document question, because the cost of over-triaging (a plant question
answered without sources) is far worse than the cost of under-triaging
(a greeting takes the slow path).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    kind: str          # greeting | capability | arithmetic | closing | document
    reason: str
    needs_corpus: bool


# Deliberately anchored and short. "hi" matches; "hint at the HCU-2
# limits" does not, because the pattern requires the whole message to be
# the greeting plus optional pleasantries.
_GREETING = re.compile(
    r"^\s*(hi|hey|hello|hola|yo|sup|namaste|good\s+(morning|afternoon|evening)|"
    r"greetings|howdy|hiya)\b[\s!.,]*"
    r"(there|amigo|friend|buddy|mate|team|all|everyone)?[\s!.,]*"
    r"(how\s+(are|r)\s+(you|u)[\s?!.]*)?$",
    re.I,
)

# A closing may be TWO acknowledgements in a row. "thanks, that's all"
# matched neither branch of the first version of this pattern -- it
# anchored the end of the message immediately after the first word --
# and so took the full document pipeline. Written as "one or more
# acknowledgement phrases, separated by punctuation, and nothing else".
_CLOSING_PHRASE = (
    r"(?:thanks|thank\s+you|thx|ty|cheers|bye|goodbye|see\s+you|"
    r"no\s+that'?s\s+(?:all|it)|that'?s\s+(?:all|it)|ok(?:ay)?|"
    r"got\s+it|understood|great|perfect|nice|awesome|cool|"
    r"appreciate\s+it|much\s+appreciated|for\s+now)"
)
_CLOSING = re.compile(
    r"^\s*" + _CLOSING_PHRASE + r"\b"
    r"(?:[\s!.,]*" + _CLOSING_PHRASE + r"\b)*"
    r"[\s!.,]*$",
    re.I,
)

_CAPABILITY = re.compile(
    r"\b(what\s+(can|do)\s+you\s+do|what\s+are\s+you|who\s+are\s+you|"
    r"how\s+do\s+you\s+work|what\s+can\s+you\s+help|help\s+me\s+understand\s+you|"
    r"what\s+are\s+your\s+(capabilities|features|tools)|"
    r"how\s+can\s+you\s+help|what\s+is\s+this\s+(app|tool|system))\b",
    re.I,
)

# Pure arithmetic or unit conversion with no subject matter attached.
_ARITHMETIC = re.compile(
    r"\d+(?:\.\d+)?\s*(?:[-+*/^x×]|plus|minus|times|divided\s+by)\s*\d",
    re.I,
)
_CONVERSION = re.compile(
    r"\bconvert\b.*\bto\b|\b\d+(?:\.\d+)?\s*[a-zA-Z°/³²]+\s+(?:to|in)\s+[a-zA-Z°/³²]+",
    re.I,
)

# Words that mean the request is about the PLANT, so it must go to
# retrieval even if it also contains a number or looks conversational.
# This is the guard that keeps the fast paths from ever answering a
# question that deserves a citation.
_DOMAIN = re.compile(
    r"\b(mrpl|refinery|hydrocracker|hcu|ccr|psa|merox|novolen|catalyst|"
    r"reactor|sop|batch|mfi|purity|sulphur|sulfur|pipeline|incident|"
    r"maintenance|downtime|spec|inspection|depot|document|report|"
    r"procedure|equipment|valve|pump|interlock|setpoint|corpus|source)\b",
    re.I,
)


def classify(request: str) -> Intent:
    """The kind of request this is."""
    text = (request or "").strip()
    if not text:
        return Intent("document", "Empty request.", True)

    # A domain word anywhere means this belongs to retrieval, full stop.
    # Checked FIRST so "convert the MFI spec to metric" cannot be
    # triaged as a bare unit conversion.
    domain = bool(_DOMAIN.search(text))

    if not domain and _GREETING.match(text):
        return Intent("greeting", "A greeting — no corpus needed.", False)

    if not domain and _CLOSING.match(text):
        return Intent("closing", "An acknowledgement — no corpus needed.", False)

    if _CAPABILITY.search(text):
        return Intent(
            "capability",
            "Asks what the system can do — answered from the live tool "
            "registry, not from documents.",
            False,
        )

    if not domain and (_ARITHMETIC.search(text) or _CONVERSION.search(text)):
        return Intent(
            "arithmetic",
            "A calculation with no plant subject — computed by a tool, "
            "no retrieval needed.",
            False,
        )

    return Intent("document", "Treated as a question about the sources.", True)


GREETING_REPLY = (
    "Hello. I answer questions about the documents loaded under **Sources** "
    "— procedures, specifications, batch and lab records, incidents, "
    "maintenance logs.\n\n"
    "Every factual claim I make comes from a document and carries a "
    "citation you can open. If the sources do not cover something, I will "
    "say so rather than guess.\n\n"
    "I can also run calculations, read charts and scanned pages, and work "
    "through multi-step questions using tools.\n\n"
    "What would you like to look at?"
)

CLOSING_REPLY = "Happy to help. Ask whenever you need something from the sources."


def capability_reply() -> str:
    """What the system can do, read from the live registry.

    Built from the actual registered tools and the actual corpus rather
    than a written-out list. A hardcoded capability blurb is a claim that
    drifts the moment a tool is added or removed -- and this codebase has
    already shipped a UI that listed two plant connectors which did not
    exist.
    """
    lines = [
        "I am a workbench for MRPL's own documents. Everything I state as "
        "fact comes from a source you can open.",
        "",
    ]

    try:
        from backend.api.routes import get_corpus

        corpus = get_corpus()
        sources = corpus.get("sources") or []
        if sources:
            lines.append(
                f"**Loaded right now:** {len(sources)} documents "
                f"({corpus.get('totalSizeDisplay', 'unknown size')}). "
                f"The Sources panel lists every one."
            )
        else:
            lines.append(
                "**No documents are loaded yet.** Add a file or folder under "
                "Sources and I can answer from it."
            )
        lines.append("")
    except Exception:  # noqa: BLE001
        pass

    lines += [
        "**What I can do**",
        "",
        "- Answer questions from the loaded documents, with a citation per claim",
        "- Refuse when the sources do not support an answer, instead of guessing",
        "- Run calculations, unit conversions and trend projections with real tools "
        "(never arithmetic in my head)",
        "- Read scanned pages and charts, and tell you when a chart reading is an "
        "estimate rather than a printed value",
        "- Follow connections between documents, equipment and incidents in the "
        "knowledge graph",
        "- Work through multi-step requests, showing each tool call and its result",
        "",
    ]

    try:
        from backend.orchestrator.agent_loop import CHAT_TOOLS

        lines.append(f"**Tools available in chat:** {', '.join(CHAT_TOOLS)}")
        lines.append("")
    except Exception:  # noqa: BLE001
        pass

    lines += [
        "**What needs your approval**",
        "",
        "Anything that writes a file, sends something, or changes a plant "
        "system stops and asks you first. That is a design rule, not a "
        "setting.",
    ]
    return "\n".join(lines)
