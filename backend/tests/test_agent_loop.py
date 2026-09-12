"""The agentic tool-calling loop and its safety properties.

Deliberately does NOT assert answer quality: the loop's extraction is a
known-weak point (see AGENT_STREAM_PROTOCOL.md), and pinning a
particular answer here would make this file fail for reasons that have
nothing to do with the wiring it exists to protect.
"""

import pytest

from backend.orchestrator.agent_loop import CHAT_TOOLS, _requires_approval, _tools_for_chat


def test_search_documents_is_offered_and_is_first():
    """The retrieval tool must exist and lead.

    Both halves were real failures. The registry had NO search tool at
    all -- "retrieval" contained only find_contradictions and
    select_images_for_request -- so asked for a value printed in the
    corpus, the model called find_contradictions, got [], and reported
    that no document contained it.

    Position matters separately: with search present but not first, the
    model reached for lookup_thermophysical_property because "MFI" reads
    like a thermophysical property.
    """
    names = [t["function"]["name"] for t in _tools_for_chat()]
    assert names, "no tools offered to the chat agent"
    assert "search_documents" in names, (
        "the agent has no way to search the corpus"
    )
    assert names[0] == "search_documents", (
        f"search_documents must lead the tool list, got {names[0]!r}"
    )


def test_chat_tool_set_excludes_the_dangerous_and_the_confusing():
    """A curated set, for measured reasons.

    run_in_sandbox executes arbitrary code and belongs to the code
    agent's closed set (AGENTS_SPEC §6). draft_docx is approval-gated.
    find_contradictions accepts an empty call that returns [], which a
    model reads as "nothing found". lookup_thermophysical_property was
    measured being called five times with wrong arguments, drifting into
    the density of methane.
    """
    for excluded in (
        "run_in_sandbox",
        "draft_docx",
        "find_contradictions",
        "lookup_thermophysical_property",
    ):
        assert excluded not in CHAT_TOOLS, (
            f"{excluded} must not be offered as a free choice in chat"
        )

    # Excluded is not disabled: it must still be in the registry.
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    for excluded in ("run_in_sandbox", "draft_docx", "find_contradictions"):
        assert excluded in _REGISTRY, (
            f"{excluded} was removed from the registry, not just from chat"
        )


def test_every_offered_tool_actually_exists():
    """CHAT_TOOLS is a hand-written list; it can drift from the registry."""
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    missing = [name for name in CHAT_TOOLS if name not in _REGISTRY]
    assert not missing, f"CHAT_TOOLS names tools that do not exist: {missing}"


def test_no_offered_chat_tool_requires_approval():
    """Hard constraint #4, enforced at the point of OFFERING.

    The loop stops and emits approval_required if a gated tool is
    chosen, so a gated tool in the chat set is not a breach -- but it
    is a dead end that wastes a turn and confuses the user. Gated tools
    are reached deliberately, not chosen mid-answer.
    """
    gated = [name for name in CHAT_TOOLS if _requires_approval(name)]
    assert not gated, (
        f"approval-gated tools offered as a free chat choice: {gated}"
    )


def test_search_documents_returns_the_grounding_decision():
    """A refusal must reach the MODEL, not be smoothed into results.

    A search tool that returned its best matches regardless of
    confidence would hand a model plausible chunks for an out-of-corpus
    question and invite the ungrounded answer NFR-4 exists to prevent.
    """
    from backend.tools.retrieval_tools import search_documents

    result = search_documents("What is the plot of Pride and Prejudice?")
    assert result["found"] is False
    assert result["passages"] == []
    assert "reason" in result
    # The near-miss documents let the model tell "not in the corpus"
    # from "my wording missed" and retry rather than invent.
    assert "closest_documents" in result


def test_search_documents_finds_what_is_there():
    from backend.tools.retrieval_tools import search_documents

    result = search_documents("average MFI Homopolymer H030SG")
    assert result["found"] is True
    assert result["passages"], "found=True with no passages"
    assert all(p.get("source_document") for p in result["passages"]), (
        "every passage must name the document it came from"
    )


def test_the_grounded_prompt_fits_the_context_window_with_headroom():
    """A built prompt must leave room for the answer.

    THIS TEST EXISTS BECAUSE A COMMENT DID NOT WORK.

    GENERATION_NUM_CTX was set to 3072 against a measured ~2000-token
    prompt, with a comment warning that any change growing the prompt
    must raise it deliberately. Two commits later neighbour expansion
    doubled the retrieved chunks (5 -> 10) and the prompt reached 2986
    tokens against that 3072 window.

    It did not overflow, which is why nothing caught it. It left ~86
    tokens for the answer, and when the window fills Ollama drops from
    the START of the prompt -- where the grounding instructions and the
    first sources live. The measured symptom was "The information
    provided does not contain any data related to MFI for Homopolymer
    H030SG" while the trace showed 10 passages retrieved with the value
    present in them.

    Retrieval was right. The prompt the model actually saw was not the
    prompt that was built.

    So this asserts headroom rather than mere fit: a prompt that exactly
    fills the window is already broken.
    """
    from backend.api.state import get_state
    from backend.models.ollama_client import GENERATION_NUM_CTX
    from backend.retrieval.generation import _build_prompt, _format_sources
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    store, _ = get_state().ensure_corpus()
    question = "What is the SOP for Hydrocracker catalyst changeout?"

    grounding = retrieve_with_grounding_check(store, question, 5)
    assert grounding.found, "fixture question must retrieve, or this proves nothing"

    prompt = _build_prompt(_format_sources(grounding.chunks), question)

    # ~4 chars/token is rough, and deliberately so: being precise about
    # the tokeniser would make this test fragile about the wrong thing.
    # What matters is the order of magnitude of the headroom.
    approx_tokens = len(prompt) / 4
    reserved_for_answer = 1024

    assert approx_tokens + reserved_for_answer < GENERATION_NUM_CTX, (
        f"prompt is ~{approx_tokens:.0f} tokens and the window is "
        f"{GENERATION_NUM_CTX}, leaving under {reserved_for_answer} for the "
        f"answer. Ollama drops from the START when the window fills, which "
        f"silently removes the grounding instructions and the first sources. "
        f"Raise WORKBENCH_GEN_CTX or retrieve fewer chunks."
    )
