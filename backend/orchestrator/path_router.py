"""Decide which path answers a request, and say why.

THE PROBLEM. There are two answering paths with genuinely different
strengths, and making the caller choose between them is making the
caller responsible for something they cannot know.

    DIRECT  (/api/chat)          one retrieval, one grounded answer with
                                 a prompt tuned against measured
                                 failures. 17-25s. Best answers for
                                 lookups, and the only path with the
                                 citation and refusal scaffolding.

    AGENTIC (/api/chat/stream)   the model chooses tools, calls them,
                                 reads results, continues. Necessary for
                                 anything needing computation or several
                                 steps. Currently under-extracts on plain
                                 lookups.

A user asking "what is the average MFI for H030SG?" wants the direct
path and has no way to know that. A user asking "project when Bed 2
delta-P crosses the limit" needs tools and likewise has no way to know.
Exposing two endpoints pushes a routing decision onto a frontend that
has strictly less information than the backend does.

So: one entry point, and this decides.

WHY THIS REUSES is_simple_lookup RATHER THAN A NEW CLASSIFIER.

`simple_intent.is_simple_lookup` already separates "one retrieval and an
answer" from "this needs work", was built for the planner-skip
optimisation, and scored 12/12 on its cases. The same distinction
answers this question, and having two classifiers that could disagree
about the same property is how a system develops a split personality.

WHY NOT ASK A MODEL TO ROUTE.

A model call to decide which path to take costs as much as a short
answer and adds a failure mode where the router itself is wrong or
unreachable. The signal here is structural -- conjunctions, action
verbs, arithmetic, comparatives -- and structure is exactly what
regexes are good at. CARD 03's router exists for task TYPE, which is a
different question.

FAILS TOWARDS DIRECT. An unclear request goes to the path with better
answer quality and full grounding scaffolding. The cost of a wrong
direct routing is an answer that could have used a tool; the cost of a
wrong agentic routing is a worse answer to a simple question, plus a
tool-selection gamble. Those are not symmetric.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PathDecision:
    path: str          # greeting | closing | capability | arithmetic
                       # | corpus | direct | agentic
    reason: str        # shown in the trace and to the UI
    tools_expected: bool


def decide_path(request: str) -> PathDecision:
    """Which path should answer this, and why.

    The reason is returned, not just the path, because a routing
    decision nobody can see is a routing decision nobody can debug --
    and the first question anyone asks about a bad answer will be "why
    did it do it that way?".
    """
    from backend.orchestrator.intent import classify
    from backend.orchestrator.simple_intent import is_simple_lookup
    from backend.retrieval.corpus_questions import carries_attached_file, is_corpus_question

    text = (request or "").strip()
    if not text:
        return PathDecision("direct", "Empty request.", False)

    # Safety-critical commands to change setpoints, files, or write to external systems
    # must be intercepted before executing any model or tool step (FR-15 / Hard constraint #4).
    # Safety gate runs BEFORE cheap intent — an operator command that
    # looks like a greeting must still be gated, not fast-pathed.
    from backend.orchestrator.graph import classify_action_request
    action_kind = classify_action_request(text)
    if action_kind is not None:
        return PathDecision(
            "approval",
            f"Safety Interlock Gate [FR-15 / §3.12]: Intercepted operator-requested {action_kind}.",
            False,
        )

    # CHEAP INTENTS NEXT -- after the safety gate above, never before
    # it. "HolA aMIGO" previously ran the LLM planner
    # (10.5s), a three-step fallback plan about safety envelopes, a
    # corpus search, and a grounding refusal naming the three documents
    # closest to a Spanish greeting -- 46.56 seconds to say "not found".
    #
    # Peeled off here because they provably need no corpus. The
    # classifier vetoes on any plant vocabulary, so a question that
    # deserves a citation can never land in one of these.
    # A file attached to this message: answered from that file by the agent,
    # never by a shortcut ("hi" + a spreadsheet is not a greeting).
    if carries_attached_file(text):
        return PathDecision("agentic", "The message carries an attached file; it is answered from that file.", True)

    intent = classify(text)
    if not intent.needs_corpus:
        return PathDecision(intent.kind, intent.reason, intent.kind == "arithmetic")

    # Questions ABOUT the collection are answered from the document
    # registry: no retrieval, no model, nothing that can be fabricated.
    if is_corpus_question(text):
        return PathDecision(
            "corpus",
            "Asks what the system holds, not what a document says — "
            "answered from the source index.",
            False,
        )

    if is_simple_lookup(text):
        return PathDecision(
            "direct",
            "Single-intent lookup — one retrieval and a grounded answer. "
            "The direct path has the citation and refusal scaffolding and "
            "gives better answers here.",
            False,
        )

    # A bare topic ("phishing", "nitrogen blanketing") names one thing to
    # look up and asks for no work. It went to the agentic path -- 14.7 s
    # against ~5 s direct -- because is_simple_lookup keys on question
    # shape, and a topic has none.
    words = text.split()
    # A standalone number suggests work to do; a digit inside a tag or
    # grade ("H030SG", "HCU-2") is just a name.
    if len(words) <= 3 and not re.search(r"(?<![A-Za-z0-9-])\d+(?:\.\d+)?(?![A-Za-z0-9])", text):
        return PathDecision(
            "direct",
            "A bare topic — one retrieval and a grounded answer about it.",
            False,
        )

    return PathDecision(
        "agentic",
        "Multi-step or needs computation — the agent will choose tools, "
        "run them, and work through it.",
        True,
    )
