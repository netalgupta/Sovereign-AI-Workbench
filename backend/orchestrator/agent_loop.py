"""The agent actually calling tools, and narrating while it does.

WHAT THIS REPLACES.

`dispatch_node` in graph.py executes steps with a hardcoded if/elif on
`assigned_agent`: retrieval runs hybrid search, math runs
evaluate_expression, code runs the sandbox. The model never CHOOSES a
tool. Seventeen tools are registered with derived JSON schemas and the
agent cannot reach sixteen of them, because nothing ever puts the
schemas in front of it.

That is why a question needing `lookup_thermophysical_property` or
`project_to_threshold` gets answered from retrieved text instead of from
an executed calculation -- the tool exists, is tested, and is
unreachable. It is also how CLAUDE.md hard constraint #3 gets quietly
weakened: "no math without a tool call" holds only for the one arithmetic
path that was wired by hand.

This module gives the model the registry and lets it work:

    user request
      -> model emits narration and/or a tool call
      -> tool executes, result goes back into the conversation
      -> model continues, narrating
      -> ... until it answers

which is the interleaved shape a person recognises as an agent doing
something rather than returning a paragraph after a long silence.

WHY OLLAMA'S NATIVE TOOL CALLING, NOT JSON-IN-A-PROMPT.

Verified working with qwen2.5:7b before this was written:

    tool_calls: [{"function": {"name": "evaluate_expression",
                               "arguments": {"expression": "381.95 - 400"}}}]

Asking a model to emit a JSON tool call inside prose means parsing it
back out, and this repo has already been bitten twice by exactly that:
the verifier wrapped valid JSON in prose that broke json.loads, and the
generation model copied a "[N]" placeholder out of its own instructions.
The native path returns a structured field that cannot be corrupted by
surrounding chatter.

EVERY STEP IS AN EVENT.

The loop yields events rather than returning a result, so the caller can
stream them to a UI as they happen. The event stream IS the contract
with the frontend; see AGENT_STREAM_PROTOCOL.md. Nothing is emitted that
did not happen: a `tool_result` carries the tool's real return value, a
`text_delta` carries tokens the model actually produced.

APPROVAL IS ENFORCED HERE TOO.

A gated tool does not execute. The loop emits `approval_required` and
stops. It does not "ask the model to confirm", it does not proceed on a
model's say-so, and there is no flag to skip it -- hard constraint #4 is
a property of the dispatcher and of this loop, not of the caller's
politeness.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import requests

from backend.models.ollama_client import OLLAMA_HOST, default_options
from backend.models.registry import resolve_model_name

# A turn that cannot finish in this many model round-trips is looping.
# Each iteration is a model call, so this is also the worst-case latency
# bound the user is exposed to.
MAX_ITERATIONS = 8

# A CURATED SET, NOT EVERY REGISTERED TOOL.
#
# This is what AGENTS_SPEC §6's "closed tool sets" are actually for, and
# the reason is measurable rather than architectural. Offering all 19
# registered tools to a 7B model produced, on a question whose answer is
# printed in the corpus:
#
#   - find_contradictions called with empty arguments (it accepts a
#     `chunks` parameter, so an empty call is well-formed and returns
#     [], which reads to the model as "nothing found")
#   - lookup_thermophysical_property called five times with different
#     wrong arguments, drifting into the density of methane
#   - search_documents emitted as literal TEXT rather than as a call
#
# Selection accuracy falls off with the number of options, and an agent
# loop compounds it: a wrong first choice becomes the context for every
# choice after it. Narrowing the set is the fix that actually works;
# prompt wording alone did not.
#
# What is deliberately EXCLUDED from a chat turn, and why:
#   run_in_sandbox       executes arbitrary code — belongs to the code
#                        agent's closed set, never to open chat
#   draft_docx           approval-gated; it is reached through an
#                        explicit request, not chosen mid-answer
#   find_contradictions  a specialist analysis over chunks the caller
#                        supplies; an empty call looks successful
#   lookup_thermophysical_property
#                        CoolProp physics. Recorded plant values (MFI,
#                        purity, spec limits) live in documents, and this
#                        tool's description reads as if it would know
#                        them
#   plot_series, describe_chart_image, transcribe_voice_note
#                        need a file or a series the chat turn does not
#                        have; they are reached from their own surfaces
#
# Anything excluded here is still registered, still tested, and still
# callable through POST /api/tools/call. It is not disabled — it is not
# OFFERED as a free choice mid-conversation.
CHAT_TOOLS = (
    "search_documents",       # first, and the answer to most questions
    "list_documents",
    "evaluate_expression",
    "evaluate_unit_expression",
    "analyse_trend",
    "project_to_threshold",
    "describe_series",
    "select_images_for_request",
    "extract_printed_text",
)

# ORDERED AND EXPLICIT, because a 7B model choosing among 19 tools picks
# on surface similarity. Measured three times on the same question,
# whose answer is printed verbatim in the corpus:
#
#   "What is the average MFI for Homopolymer H030SG?"
#     1. called find_contradictions, got [], reported that no documents
#        contain it  (there was no search tool at all)
#     2. after search_documents was added, called
#        lookup_thermophysical_property -- a CoolProp lookup for fluids --
#        because its description mentions "properties"
#     3. called it FIVE times with different wrong arguments, drifted
#        into computing the density of methane, and asked the user for
#        clarification
#
# The model was not being stupid: "MFI" reads like a thermophysical
# property, and nothing told it that documentation questions begin with
# a search. An agent loop makes a weak tool-selection signal much worse
# than a single call does, because a wrong first choice becomes the
# context for every choice after it.
#
# So the rule is the first instruction, states the tool by name, and
# names the specific wrong turn. search_documents is also sorted first
# in the tool list -- a weak signal, but free.
_SYSTEM_PROMPT = (
    "You are an engineering assistant for a refinery, working strictly "
    "from tools and retrieved documents.\n\n"
    "FIRST RULE. For ANY question about equipment, procedures, "
    "specifications, incidents, batches, lab results, or anything that "
    "might be written down in a plant document, your FIRST action is to "
    "call search_documents. Do not guess which tool matches the subject "
    "matter -- search first, then decide.\n"
    "Values such as MFI, purity, temperature limits, spec ranges and "
    "catalyst life are RECORDED IN DOCUMENTS. They are not computed from "
    "physics, so never reach for a property-lookup tool to find them.\n\n"
    "How to work:\n"
    "- Say what you are about to do in one short sentence, then do it.\n"
    "- After a tool returns, say what it gave you before moving on.\n"
    "- Never do arithmetic yourself; call the calculation tool.\n"
    "- Name the source document when you use a retrieved passage.\n"
    "- When you have enough, give the final answer and stop.\n"
    "- If a tool call fails twice, stop calling it and say what is "
    "missing. Do not keep retrying with different arguments.\n"
    "- If search_documents finds nothing, say so plainly. Do not fill "
    "the gap from general knowledge, and do not substitute a different "
    "tool to manufacture a number.\n"
)


def _tools_for_chat() -> list[dict]:
    from backend.tools import catalog  # noqa: F401  (registers everything)
    from backend.tools.registry import get_tool_schemas

    by_name = {s["function"]["name"]: s for s in get_tool_schemas()}

    # Built in CHAT_TOOLS order, so search_documents is first. Position
    # is a weak signal but a free one. A name in the list that is not in
    # the registry is skipped silently rather than raising: a tool being
    # renamed should degrade the agent's options, not break every turn.
    return [by_name[name] for name in CHAT_TOOLS if name in by_name]


def _requires_approval(name: str) -> bool:
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    spec = _REGISTRY.get(name)
    return bool(spec and spec.requires_approval)


def _chat_once(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """One non-streaming round-trip. Returns the assistant message."""
    response = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": default_options(),
        },
        timeout=600,
    )
    response.raise_for_status()
    return response.json().get("message", {}) or {}


def _stream_once(model: str, messages: list[dict], tools: list[dict]) -> Iterator[dict]:
    """One streaming round-trip, yielding raw Ollama message fragments.

    Streaming matters for the narration specifically. A tool call arrives
    as one structured chunk either way, but the sentence explaining what
    the agent is about to do should appear WHILE it is being written --
    that is the whole difference between watching something work and
    staring at a spinner.
    """
    with requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "options": default_options(),
        },
        timeout=600,
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A malformed frame is dropped rather than killing the
                # turn. Ollama occasionally emits keep-alive noise, and
                # losing one fragment degrades the narration; raising
                # would lose the whole answer.
                continue


def run_agent_loop(
    request: str,
    session_id: str = "default",
    model_id: str = "reasoning-model",
    max_iterations: int = MAX_ITERATIONS,
) -> Iterator[dict]:
    """Work on `request`, yielding events as it goes.

    Event types (the contract with the UI — see
    docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md):

        {"type": "start",      "request": str}
        {"type": "text_delta", "text": str}
        {"type": "tool_call",  "id": str, "name": str, "arguments": dict}
        {"type": "tool_result","id": str, "name": str, "output": Any,
                               "status": "done"|"failed", "seconds": float}
        {"type": "approval_required", "id": str, "name": str,
                               "arguments": dict, "effect": str}
        {"type": "done",       "reply": str, "tool_calls": int,
                               "iterations": int, "seconds": float}
        {"type": "error",      "message": str}

    Yields rather than returns so a caller can stream. Callers that just
    want the answer can drain it and keep the final `done` event.
    """
    from backend.observability import turn_log as T

    started = time.perf_counter()
    model = resolve_model_name(model_id)
    tools = _tools_for_chat()

    T.section("AGENT LOOP")
    T.kv("request", repr(request))
    T.kv("model", f"{model_id} -> {model}")
    T.kv("tools offered", len(tools))

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]

    yield {"type": "start", "request": request}

    full_text: list[str] = []
    tool_call_count = 0

    for iteration in range(1, max_iterations + 1):
        assistant_text: list[str] = []
        tool_calls: list[dict] = []

        try:
            for frame in _stream_once(model, messages, tools):
                message = frame.get("message") or {}

                chunk = message.get("content") or ""
                if chunk:
                    assistant_text.append(chunk)
                    full_text.append(chunk)
                    yield {"type": "text_delta", "text": chunk}

                for call in message.get("tool_calls") or []:
                    tool_calls.append(call)

                if frame.get("done"):
                    break
        except Exception as exc:  # noqa: BLE001
            T.error(f"model call failed: {type(exc).__name__}: {exc}")
            yield {
                "type": "error",
                "message": f"The model call failed: {type(exc).__name__}: {exc}",
            }
            return

        text_so_far = "".join(assistant_text)

        # No tool wanted -> the model is answering. Done.
        if not tool_calls:
            T.kv(f"iteration {iteration}", "final answer")
            break

        # Record the assistant's turn verbatim, including the tool calls,
        # so the model sees its own decision on the next round-trip.
        messages.append(
            {"role": "assistant", "content": text_so_far, "tool_calls": tool_calls}
        )

        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name") or ""
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                # Some builds return the arguments JSON-encoded.
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            call_id = call.get("id") or f"call-{iteration}-{tool_call_count}"
            tool_call_count += 1

            T.note(f"    tool: {name}({json.dumps(arguments)[:70]})")
            yield {
                "type": "tool_call",
                "id": call_id,
                "name": name,
                "arguments": arguments,
            }

            # HARD CONSTRAINT #4. A gated tool stops the loop. It is not
            # executed, the model is not asked whether it should be, and
            # there is no parameter that skips this.
            if _requires_approval(name):
                from backend.tools import catalog  # noqa: F401
                from backend.tools.registry import _REGISTRY

                spec = _REGISTRY.get(name)
                effect = getattr(spec, "description", "") or name
                T.warn(f"{name} requires approval - loop stopped")
                yield {
                    "type": "approval_required",
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                    "effect": effect,
                }
                yield {
                    "type": "done",
                    "reply": "".join(full_text).strip(),
                    "tool_calls": tool_call_count,
                    "iterations": iteration,
                    "seconds": round(time.perf_counter() - started, 2),
                    "awaiting_approval": True,
                }
                return

            call_started = time.perf_counter()
            try:
                from backend.tools.registry import call_tool

                output = call_tool(name, arguments)
                status = "done"
            except Exception as exc:  # noqa: BLE001
                # The failure goes back to the MODEL, not just to the UI.
                # A tool that failed is information the agent needs in
                # order to try something else; swallowing it leaves the
                # model to answer as though the call had succeeded.
                output = {"error": f"{type(exc).__name__}: {exc}"}
                status = "failed"

            seconds = round(time.perf_counter() - call_started, 2)
            yield {
                "type": "tool_result",
                "id": call_id,
                "name": name,
                "output": _jsonable(output),
                "status": status,
                "seconds": seconds,
            }

            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(_jsonable(output))[:4000],
                    "name": name,
                }
            )
    else:
        # Exhausted the iteration budget with the model still calling
        # tools. Reported, never presented as a finished answer.
        T.warn(f"hit the {max_iterations}-iteration limit")
        yield {
            "type": "error",
            "message": (
                f"Stopped after {max_iterations} steps without reaching an "
                f"answer. The partial work above is real, but the turn did "
                f"not finish."
            ),
        }

    reply = "".join(full_text).strip()
    T.kv("tool calls", tool_call_count)
    T.kv("elapsed", f"{time.perf_counter() - started:.2f}s")

    yield {
        "type": "done",
        "reply": reply,
        "tool_calls": tool_call_count,
        "iterations": iteration,
        "seconds": round(time.perf_counter() - started, 2),
        "awaiting_approval": False,
    }


def _jsonable(value: Any) -> Any:
    """Best-effort JSON-safe conversion, preserving structure.

    Tools return pydantic models, dataclasses and numpy scalars. Falling
    back to str() for the whole object would flatten a structured result
    into a string the UI cannot render and the model cannot read, so this
    converts recursively and only stringifies the leaves it cannot.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "__dict__"):
        try:
            return _jsonable(vars(value))
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def run_turn(
    request: str,
    session_id: str = "default",
    model_id: str = "reasoning-model",
) -> Iterator[dict]:
    """Answer `request` by whichever path suits it, as one event stream.

    THIS IS THE ENTRY POINT. Callers should use this rather than
    run_agent_loop directly, and the UI should never choose a path.

    There are two answering paths with genuinely different strengths --
    the direct grounded path has citation and refusal scaffolding tuned
    against measured failures and gives better answers to lookups; the
    agentic loop can call tools and iterate, which lookups do not need
    and multi-step work cannot do without. Making the caller pick means
    making the caller responsible for a judgement the backend is better
    placed to make: a user asking "what is the average MFI for H030SG?"
    wants the direct path and has no way to know that.

    So the routing happens here (backend/orchestrator/path_router.py)
    and EVERY path emits the same event protocol. The UI renders one
    shape regardless, and a `route` event tells it which path ran and
    why, so the decision is visible rather than mysterious.
    """
    from backend.observability import turn_log as T
    from backend.orchestrator.path_router import decide_path

    decision = decide_path(request)

    T.section("ROUTE")
    T.kv("path", decision.path)
    T.kv("reason", decision.reason)

    yield {"type": "start", "request": request}
    yield {
        "type": "route",
        "path": decision.path,
        "reason": decision.reason,
        "tools_expected": decision.tools_expected,
    }

    if decision.path == "agentic":
        # Drop the loop's own `start`; one has already been emitted, and
        # two would make a UI clear its transcript mid-turn.
        for event in run_agent_loop(request, session_id=session_id, model_id=model_id):
            if event.get("type") == "start":
                continue
            yield event
        return

    yield from _run_direct(request, decision)


def _run_direct(request: str, decision) -> Iterator[dict]:
    """The grounded path, emitted as stream events.

    Adapted rather than duplicated: the answer still comes from
    generate_grounded_answer (or the corpus index), so there is exactly
    one implementation of grounded answering and this cannot drift from
    /api/chat.

    The text arrives as a single `text_delta` rather than token by token.
    That is honest -- the direct path is not streamed, and faking a
    typewriter over an answer that already exists would be inventing
    progress, which is the failure mode the deleted "Retrieving sources
    - 21s" indicator embodied.
    """
    import time

    started = time.perf_counter()

    if decision.path == "corpus":
        from backend.retrieval.corpus_questions import answer_corpus_question

        reply = answer_corpus_question(request)
        yield {"type": "text_delta", "text": reply}
        yield {
            "type": "done",
            "reply": reply,
            "tool_calls": 0,
            "iterations": 1,
            "seconds": round(time.perf_counter() - started, 2),
            "awaiting_approval": False,
            "citations": [],
        }
        return

    from backend.api.state import get_state
    from backend.retrieval.generation import generate_grounded_answer

    try:
        store, _ = get_state().ensure_corpus()
        answer = generate_grounded_answer(store, request)
    except Exception as exc:  # noqa: BLE001
        yield {
            "type": "error",
            "message": f"Grounded generation failed: {type(exc).__name__}: {exc}",
        }
        return

    # Retrieval really happened, so it is reported as the tool call it
    # is. The UI then shows the same "what did it do" detail on both
    # paths instead of the direct path looking like magic.
    yield {
        "type": "tool_call",
        "id": "direct-retrieval",
        "name": "search_documents",
        "arguments": {"query": request},
    }
    yield {
        "type": "tool_result",
        "id": "direct-retrieval",
        "name": "search_documents",
        "output": {
            "found": answer.found,
            "passages": len(answer.sources),
            "documents": sorted({c.source_document for c in answer.sources}),
        },
        "status": "done",
        "seconds": round(time.perf_counter() - started, 2),
    }

    reply = answer.answer_text
    yield {"type": "text_delta", "text": reply}
    yield {
        "type": "done",
        "reply": reply,
        "tool_calls": 1,
        "iterations": 1,
        "seconds": round(time.perf_counter() - started, 2),
        "awaiting_approval": False,
        "citations": [
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in answer.sources
        ],
    }
