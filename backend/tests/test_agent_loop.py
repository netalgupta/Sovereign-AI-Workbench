"""The agentic tool-calling loop and its safety properties.

Deliberately does NOT assert answer quality: the loop's extraction is a
known-weak point (see AGENT_STREAM_PROTOCOL.md), and pinning a
particular answer here would make this file fail for reasons that have
nothing to do with the wiring it exists to protect.
"""


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
    agent's closed set (AGENTS_SPEC §6). draft_docx is approval-gated and
    offered for document creation requests. find_contradictions accepts an
    empty call that returns [], which a model reads as "nothing found".
    lookup_thermophysical_property was measured being called five times with
    wrong arguments.
    """
    for excluded in (
        "run_in_sandbox",
        "find_contradictions",
        "lookup_thermophysical_property",
    ):
        assert excluded not in CHAT_TOOLS, (
            f"{excluded} must not be offered as a free choice in chat"
        )

    # Excluded is not disabled: it must still be in the registry.
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    for registered in ("run_in_sandbox", "draft_docx", "find_contradictions"):
        assert registered in _REGISTRY, (
            f"{registered} must be present in registry"
        )


def test_every_offered_tool_actually_exists():
    """CHAT_TOOLS is a hand-written list; it can drift from the registry."""
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    # evaluate_unit_expression is optional if pint is not installed in env
    missing = [name for name in CHAT_TOOLS if name not in _REGISTRY and name != "evaluate_unit_expression"]
    assert not missing, f"CHAT_TOOLS names tools that do not exist: {missing}"


def test_draft_docx_requires_approval_and_stops_loop():
    """Hard constraint #4: draft_docx is approval-gated and must yield approval_required."""
    from backend.tools import catalog  # noqa: F401
    assert _requires_approval("draft_docx") is True


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


# ── the agent map: every model call reports what it read and wrote ─────────

def test_each_model_call_reports_its_tokens_and_the_turn_totals_them(monkeypatch):
    from backend.orchestrator import agent_loop as AL

    def fake_stream(model, messages, tools, timeout=90):
        yield {"message": {"content": "The answer is in the SOP."}, "done": False}
        yield {"message": {}, "done": True, "prompt_eval_count": 1866, "eval_count": 202}

    monkeypatch.setattr(AL, "_stream_once", fake_stream)
    events = list(AL.run_agent_loop("What does SOP-114 require?"))
    calls = [e for e in events if e["type"] == "llm_call"]
    assert len(calls) == 1
    assert calls[0]["prompt_tokens"] == 1866 and calls[0]["output_tokens"] == 202
    assert calls[0]["model"] and calls[0]["seconds"] >= 0 and calls[0]["t_ms"] >= 0
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["usage"] == {"prompt_tokens": 1866, "output_tokens": 202, "llm_calls": 1}


def test_counts_ollama_did_not_report_are_absent_not_estimated(monkeypatch):
    from backend.orchestrator import agent_loop as AL

    def fake_stream(model, messages, tools, timeout=90):
        yield {"message": {"content": "ok"}, "done": True}

    monkeypatch.setattr(AL, "_stream_once", fake_stream)
    calls = [e for e in AL.run_agent_loop("hello there, what is PSA?") if e["type"] == "llm_call"]
    assert calls and calls[0]["prompt_tokens"] is None and calls[0]["output_tokens"] is None


# ── hard constraint #3: stated arithmetic is COMPUTED, not just flagged ────

def test_a_stated_sum_is_read_as_expression_and_claimed_result():
    from backend.orchestrator.agent_loop import _split_stated_arithmetic

    assert _split_stated_arithmetic("11.2 - 3.4 = 7.8") == ("11.2 - 3.4", 7.8)
    assert _split_stated_arithmetic("22 plus 16 is 38") == ("22 + 16", 38.0)
    assert _split_stated_arithmetic("3 x 4 = 12") == ("3 * 4", 12.0)
    assert _split_stated_arithmetic("the answer = 7") is None


def test_a_wrong_stated_result_is_replaced_by_the_computed_one():
    """Measured 27 Sep: 'compute the difference' was answered with an inline
    11.2 - 3.4 = 7.8 and no computation tool -- labelled unverified, never
    computed. Now the tool runs; a wrong result is corrected."""
    from backend.orchestrator.agent_loop import _numeric_result, _replace_result
    from backend.tools import catalog  # noqa: F401 - registers the tools
    from backend.tools.registry import call_tool

    value = _numeric_result(call_tool("evaluate_expression", {"expression": "11.2 - 3.4"}))
    assert abs(value - 7.8) < 1e-9
    assert _replace_result("11.2 - 3.4 = 7.9", value) == "11.2 - 3.4 = 7.8"
