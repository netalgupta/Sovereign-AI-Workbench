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
import re
import time
from collections.abc import Iterator
from typing import Any

import requests

from backend.models.ollama_client import DEFAULT_TIMEOUT, OLLAMA_HOST, default_options
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
    "draft_docx",
    "draft_xlsx",
    "generate_pdf",
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
    "TOOL DISAMBIGUATION & DOCUMENT CREATION RULES:\n"
    "- If asked to build, draft, create, or generate a spreadsheet, Excel file, "
    "comparison table, matrix, or .xlsx file, or if the request specifies an output "
    "filename ending in .xlsx, you MUST call draft_xlsx with title, sheets (headers, "
    "rows with sources or marked unsourced, live Excel formulas), and output_path "
    "(e.g. \"storage/outputs/filename.xlsx\").\n"
    "- If asked to draft, create, write, or generate a Word document, text report, memo, "
    "or .docx file, or if the request specifies a .docx filename, call draft_docx with title, "
    "sections (including source citations), and output_path (e.g. \"storage/outputs/filename.docx\").\n"
    "- If asked to draft, create, write, generate, or export a PDF document, report, or .pdf file, "
    "call generate_pdf with title, sections (including source citations), and output_path "
    "(e.g. \"storage/outputs/filename.pdf\").\n"
    "- An explicit filename ending in .xlsx is a HARD SIGNAL to call draft_xlsx.\n"
    "- An explicit filename ending in .pdf is a HARD SIGNAL to call generate_pdf.\n"
    "- INSUFFICIENT OR MISSING SOURCE DATA IS NOT A REASON TO SKIP CALLING THE TOOL OR REFUSE THE REQUEST. "
    "You MUST ALWAYS call draft_xlsx to generate the requested file structure. "
    "For any requested values or cells that cannot be found in the sources, leave the cell value empty "
    "and mark it unsourced (is_unsourced: true). NEVER fabricate, guess, infer, or invent numeric figures "
    "(such as MFI values, flow rates, temperatures) to fill cells.\n\n"
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
    "- There is NO defect/anomaly detector. If asked whether an image "
    "or photo shows a defect (corrosion, crack, leak, anomaly), say "
    "defect detection is not available. The only image-region boxes "
    "available are OCR text regions — locations of printed text, never "
    "defect findings. Do not present them as such.\n"
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


# A request whose subject is a spreadsheet or Word build should NOT be
# offered the whole CHAT_TOOLS menu. Each tool schema is several thousand
# characters of JSON, and a 7B model weighs every offered schema every
# turn. Locking a drafting turn to search_documents + the one drafting
# tool it can possibly mean cuts the per-request schema payload ~70%
# (measured: 7421 -> 2179 chars) and removes an entire class of
# "model picked the wrong drafting tool" misroutes.
#
# The spreadsheet signal lives in action_resolver.is_spreadsheet_request:
# the interceptor resolves an Excel request to draft_xlsx with the SAME
# decision, and the two must not drift (review rule #6 -- one
# implementation on every path that reaches it).
_DOCX_SIGNAL = re.compile(
    r"(?:\.docx|word document|text report|\bmemo\b|(?:build|draft|create|write)\b.*(?:document|report|memo))",
    re.IGNORECASE,
)


def _tools_for_request(request: str) -> list[dict]:
    """The tool schemas suited to one `request`.

    Drafting requests (spreadsheet / Word) get exactly the two tools they
    can use; everything else gets the full curated chat set.
    """
    from backend.orchestrator.action_resolver import is_spreadsheet_request, is_pdf_request
    from backend.tools import catalog  # noqa: F401  (registers everything)
    from backend.tools.registry import get_tool_schemas

    by_name = {s["function"]["name"]: s for s in get_tool_schemas()}

    def offer(*names: str) -> list[dict]:
        return [by_name[n] for n in names if n in by_name]

    if is_spreadsheet_request(request):
        return offer("search_documents", "draft_xlsx")
    if is_pdf_request(request):
        return offer("search_documents", "generate_pdf")
    if _DOCX_SIGNAL.search(request):
        return offer("search_documents", "draft_docx")

    return _tools_for_chat()


# Arithmetic stated WITH ITS RESULT: "22 + 16 = 38", "22+16 is 38".
# Requires the operands AND the answer, so a number quoted from a
# document ("22 batches") is not matched -- only a claim that a
# calculation was performed.
_STATED_ARITHMETIC = re.compile(
    r"\d+(?:\.\d+)?\s*(?:[-+*/x×]|plus|minus|times|divided by)\s*"
    r"\d+(?:\.\d+)?(?:\s*(?:[-+*/x×]|plus|minus|times|divided by)\s*\d+(?:\.\d+)?)*"
    r"\s*(?:=|is|equals|gives|totals?|comes to)\s*\d+(?:\.\d+)?",
    re.I,
)

# Tools whose output is a computed number.
_COMPUTATION_TOOLS = frozenset({
    "evaluate_expression",
    "evaluate_unit_expression",
    "analyse_trend",
    "project_to_threshold",
    "describe_series",
    "lookup_thermophysical_property",
})


def _unverified_arithmetic(reply: str, tools_used: set[str]) -> list[str]:
    """Arithmetic the model stated without any tool having computed it.

    CLAUDE.md hard constraint #3: no numeric result may come from an LLM
    without an executed tool call. The registry, the dispatcher and the
    tool set all enforce that a tool CAN be called. None of them enforce
    that the model actually called one before writing a sum down.

    Measured on the same question across three runs: two correctly
    called evaluate_expression("22 + 16"); one wrote
    "22 + 16 = 38" inline with no computation tool in the turn at all.
    It was right. The constraint exists because the next one might not
    be, and an inline sum carries no tool-call receipt for anyone to
    check.

    This does not block the answer -- the arithmetic may be quoted from
    a source, and refusing on a regex would be worse than the problem.
    It surfaces the claim so a reader knows which numbers were computed
    and which were asserted.
    """
    if not reply or tools_used & _COMPUTATION_TOOLS:
        return []
    return [m.group(0).strip() for m in _STATED_ARITHMETIC.finditer(reply)]


def _normalise_query(arguments: dict) -> str:
    """A search's identity, for spotting repeats.

    Lowercased, stripped of the boolean noise the model adds, and
    word-sorted -- so "H030SG AND 'batches'" and "batches for H030SG"
    are recognised as the same search, because against a semantic
    retriever they ARE the same search.
    """
    import re as _re

    raw = " ".join(str(v) for v in arguments.values() if isinstance(v, (str, int)))
    raw = _re.sub(r"[\"\'()]", " ", raw.lower())
    raw = _re.sub(r"\b(and|or|not)\b", " ", raw)
    return " ".join(sorted(w for w in _re.split(r"\W+", raw) if len(w) > 2))


def _requires_approval(name: str) -> bool:
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import _REGISTRY

    spec = _REGISTRY.get(name)
    return bool(spec and spec.requires_approval)


def _chat_once(model: str, messages: list[dict], tools: list[dict], timeout: int = 90) -> dict:
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
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("message", {}) or {}


def _stream_once(model: str, messages: list[dict], tools: list[dict], timeout: int = 90) -> Iterator[dict]:
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
        timeout=timeout,
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
    active_documents: list[str] | None = None,
    memory=None,
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

    # Instrument tool schema construction
    t_schema_start = time.perf_counter()
    tools = _tools_for_request(request)
    t_schema_ms = round((time.perf_counter() - t_schema_start) * 1000, 2)

    tool_names = [t["function"]["name"] for t in tools]

    T.section("AGENT LOOP")
    T.kv("request", repr(request))
    T.kv("model", f"{model_id} -> {model}")
    T.kv("step: tool_schema_construction (ms)", t_schema_ms)
    T.kv("tools offered count", len(tools))
    T.kv("tools offered names", ", ".join(tool_names))
    T.kv("tool schema payload (chars)", len(json.dumps(tools)))

    # Conversation context goes in the SYSTEM message, not the user
    # message. Appending it to the request makes the model answer the
    # history; keeping it in the system role makes it background the
    # request is interpreted against, which is what it is. It arrives
    # already labelled "context only - NOT a source".
    system = _SYSTEM_PROMPT
    context = getattr(memory, "context_block", "") or ""
    if context:
        system = _SYSTEM_PROMPT + "\n" + context
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": request},
    ]

    yield {"type": "start", "request": request}

    final_reply_chunks: list[str] = []
    tool_call_count = 0

    seen_searches: dict[str, int] = {}
    tools_used: set[str] = set()

    for iteration in range(1, max_iterations + 1):
        assistant_text: list[str] = []
        tool_calls: list[dict] = []

        t_llm_start = time.perf_counter()
        try:
            for frame in _stream_once(model, messages, tools, timeout=DEFAULT_TIMEOUT):
                message = frame.get("message") or {}

                chunk = message.get("content") or ""
                if chunk:
                    assistant_text.append(chunk)

                for call in message.get("tool_calls") or []:
                    tool_calls.append(call)

                if frame.get("done"):
                    break
            t_llm_ms = round((time.perf_counter() - t_llm_start) * 1000, 2)
            T.kv(f"iteration {iteration} step: llm_call (ms)", t_llm_ms)
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as exc:
            t_llm_ms = round((time.perf_counter() - t_llm_start) * 1000, 2)
            T.error(f"iteration {iteration} step: llm_call TIMEOUT after {t_llm_ms}ms: {exc}")
            yield {
                "type": "error",
                "message": f"LLM call timed out ({t_llm_ms:.0f}ms). The model turn exceeded the {DEFAULT_TIMEOUT}s per-step limit.",
            }
            return
        except Exception as exc:  # noqa: BLE001
            t_llm_ms = round((time.perf_counter() - t_llm_start) * 1000, 2)
            T.error(f"iteration {iteration} step: llm_call failed after {t_llm_ms}ms: {type(exc).__name__}: {exc}")
            yield {
                "type": "error",
                "message": f"The model call failed: {type(exc).__name__}: {exc}",
            }
            return

        text_so_far = "".join(assistant_text).strip()

        # If tools were called, this text is tool-selection reasoning / process narration.
        # It belongs inside the thinking block, NEVER in the final reply body!
        if tool_calls:
            T.kv(f"iteration {iteration}", f"tool call reasoning ({len(text_so_far)} chars)")
            if text_so_far:
                yield {
                    "type": "thought",
                    "text": text_so_far,
                    "iteration": iteration,
                }

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

                tools_used.add(name)
                T.note(f"    tool: {name}({json.dumps(arguments)[:70]})")
                yield {
                    "type": "tool_call",
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                    "reasoning": text_so_far,
                }

            # HARD CONSTRAINT #4. A gated tool stops the loop. It is not
            # executed, the model is not asked whether it should be, and
            # there is no parameter that skips this.
            if _requires_approval(name):
                t_gate_start = time.perf_counter()
                from backend.audit.approval_gate import ApprovalGate
                from backend.tools import catalog  # noqa: F401
                from backend.tools.registry import _REGISTRY
                from backend.audit.approval_gate import ApprovalGate

                spec = _REGISTRY.get(name)
                effect = getattr(spec, "description", "") or name
                if name == "draft_docx":
                    from backend.tools.documents.draft_docx import describe_effect

                    try:
                        effect = describe_effect(
                            arguments.get("title", ""),
                            arguments.get("sections", []),
                            arguments.get("output_path", ""),
                        )
                    except Exception:  # noqa: BLE001
                        pass
                elif name == "draft_xlsx":
                    from backend.tools.documents.draft_xlsx import describe_effect

                    try:
                        effect = describe_effect(
                            arguments.get("title", ""),
                            arguments.get("sheets", []),
                            arguments.get("output_path", ""),
                        )
                    except Exception:  # noqa: BLE001
                        pass

                gate = ApprovalGate()
                app_req = gate.request(tool_name=name, arguments=arguments, effect=effect)
                t_gate_ms = round((time.perf_counter() - t_gate_start) * 1000, 2)

                T.kv(f"step: approval_gate_request ({name}) (ms)", t_gate_ms)
                T.warn(f"{name} requires approval - loop stopped in {t_gate_ms}ms (request {app_req.request_id})")
                yield {
                    "type": "approval_required",
                    "id": app_req.request_id,
                    "name": name,
                    "arguments": arguments,
                    "effect": app_req.effect,
                }
                yield {
                    "type": "done",
                    "reply": "".join(final_reply_chunks).strip(),
                    "tool_calls": tool_call_count,
                    "iterations": iteration,
                    "seconds": round(time.perf_counter() - started, 2),
                    "awaiting_approval": True,
                }
                return

            call_started = time.perf_counter()
            step_category = "retrieval" if name in ("search_documents", "list_documents") else ("file_write" if name in ("draft_docx", "draft_xlsx") else "tool_execution")

            signature = f"{name}:{_normalise_query(arguments)}"
            repeat_count = seen_searches.get(signature, 0)
            seen_searches[signature] = repeat_count + 1

            if repeat_count >= 1:
                # Answer with the fact of the repeat rather than the same
                # passages again. The model needs to know its retry
                # changed nothing, which the passages alone do not say.
                T.warn(f"repeated search ({repeat_count + 1}x): {name}")
                output = {
                    "repeated_search": True,
                    "message": (
                        "You have already run this search and received the "
                        "results above. Rewording it returns the same "
                        "passages, because this is a meaning-based search "
                        "and the rewording means the same thing. Answer "
                        "from what you already have, or say what is "
                        "missing from it."
                    ),
                }
                status = "done"
                yield {
                    "type": "tool_result",
                    "id": call_id,
                    "name": name,
                    "output": output,
                    "status": status,
                    "seconds": 0.0,
                }
                messages.append(
                    {"role": "tool", "content": json.dumps(output), "name": name}
                )
                continue

            try:
                from backend.tools.registry import call_tool

                output = call_tool(name, arguments)
                status = "done"
            except Exception as exc:  # noqa: BLE001
                output = {"error": f"{type(exc).__name__}: {exc}"}
                status = "failed"

            seconds = round(time.perf_counter() - call_started, 2)
            t_step_ms = round(seconds * 1000, 2)
            T.kv(f"step: {step_category} ({name}) (ms)", t_step_ms)
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
            # No tool wanted -> the model is delivering its FINAL ANSWER!
            T.kv(f"iteration {iteration}", "final answer")

            clean_answer = text_so_far
            if "<think>" in clean_answer:
                if "</think>" in clean_answer:
                    thought_matches = re.findall(r"<think>(.*?)</think>", clean_answer, flags=re.DOTALL)
                    for tb in thought_matches:
                        tb_strip = tb.strip()
                        if tb_strip:
                            yield {
                                "type": "thought",
                                "text": tb_strip,
                                "iteration": iteration,
                            }
                    clean_answer = re.sub(r"<think>.*?</think>", "", clean_answer, flags=re.DOTALL).strip()
                else:
                    parts = clean_answer.split("<think>", 1)
                    clean_answer = parts[0].strip()
                    thought_body = parts[1].strip()
                    if thought_body:
                        yield {
                            "type": "thought",
                            "text": thought_body,
                            "iteration": iteration,
                        }

            final_reply_chunks.append(clean_answer)
            yield {"type": "text_delta", "text": clean_answer}
            break
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

    reply = "".join(final_reply_chunks).strip()

    # HARD CONSTRAINT #3, checked on the way out.
    unverified = _unverified_arithmetic(reply, tools_used)
    if unverified:
        T.warn(
            "arithmetic stated without a computation tool: "
            + "; ".join(unverified[:3])
        )
        reply += (
            "\n\n> **Note:** the arithmetic above was written by the model "
            "rather than computed by a tool. Values quoted from documents are "
            "still cited; the calculation itself is unverified."
        )
        yield {
            "type": "unverified_arithmetic",
            "expressions": unverified,
            "message": (
                "The answer states a calculation that no computation tool "
                "performed."
            ),
        }

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
    active_documents: list[str] | None = None,
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
    from backend.memory.turn import close_turn, open_turn
    from backend.observability import turn_log as T
    from backend.orchestrator.path_router import decide_path

    decision = decide_path(request)

    T.section("ROUTE")
    T.kv("path", decision.path)
    T.kv("reason", decision.reason)

    # MEMORY, ON THIS PATH TOO.
    #
    # It was wired into graph.py's synthesize_node and nowhere else, so
    # this endpoint neither remembered a conversation nor RECORDED one --
    # which also left holes in the session for later turns answered by
    # the other endpoint. Both paths now go through the same pair of
    # functions; see backend/memory/turn.py.
    memory = open_turn(session_id, request)
    if memory.degraded:
        T.warn(f"memory unavailable ({memory.degraded}); answering statelessly")
    elif memory.has_context:
        T.kv("memory", f"context {len(memory.context_block)} chars")
        if memory.added_terms:
            T.kv("resolved follow-up", f"+{memory.added_terms}")
        if memory.focus_documents:
            T.kv("focus documents", memory.focus_documents[:3])

    # WHAT THE SYSTEM REMEMBERED, AS AN EVENT.
    #
    # Memory changed what was retrieved -- a follow-up gets rewritten,
    # focus documents steer the search -- and none of that was visible.
    # An answer that differs because of something remembered two turns
    # ago, with no indication that anything was remembered, is the kind
    # of behaviour a user reads as the system being inconsistent.
    #
    # Emitted before any work so the UI can show it while the turn runs,
    # and carrying counts rather than contents; see TurnMemory.summary().
    yield {"type": "memory", **memory.summary()}

    reply_text = ""
    citations: list = []
    documents: list = []
    tool_calls: list = []
    try:
        for event in _answer(
            request,
            decision,
            memory,
            session_id=session_id,
            model_id=model_id,
            active_documents=active_documents,
        ):
            kind = event.get("type")
            if kind == "done":
                reply_text = event.get("reply") or ""
                citations = event.get("citations") or []
                documents = _documents_from_citations(citations)
            elif kind == "tool_result":
                tool_calls.append({
                    "tool_name": event.get("name"),
                    "status": event.get("status"),
                })
                documents.extend(_documents_from_tool_result(event))
            elif kind == "error":
                reply_text = event.get("message") or reply_text
            yield event
    finally:
        # Recorded in a finally block deliberately: a turn that crashed
        # or was disconnected mid-stream still happened, and a session
        # that silently drops it leaves the next turn interpreting a
        # conversation with a hole in it.
        close_turn(
            session_id,
            reply_text,
            route=decision.path,
            citations=citations,
            documents=_dedupe(documents),
            tool_calls=tool_calls,
            entities=_entities_from_citations(citations),
        )


def _dedupe(values: list) -> list:
    seen: list = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _documents_from_citations(citations: list) -> list:
    return _dedupe([c.get("source_document") for c in citations if isinstance(c, dict)])


def _documents_from_tool_result(event: dict) -> list:
    output = event.get("output")
    if isinstance(output, dict):
        docs = output.get("documents")
        if isinstance(docs, list):
            return [d for d in docs if isinstance(d, str)]
    return []


def _entities_from_citations(citations: list) -> list:
    """Equipment tags and segment names present in the cited passages.

    Deterministic pattern matching, not a model call. An entity in this
    list steers the NEXT turn's retrieval, so a hallucinated one would
    silently bias a later answer -- and the tags this matches (HCU-2,
    FFC-201, SOP-114-Rev3) have a shape that does not need inference.
    """
    found: list = []
    for citation in citations:
        text = citation.get("text") if isinstance(citation, dict) else None
        if not text:
            continue
        for match in _ENTITY_RE.finditer(text):
            token = match.group(0).strip()
            if token and token not in found:
                found.append(token)
            if len(found) >= 12:
                return found
    return found


# Equipment tags, instrument tags, document numbers and named pipeline
# segments. Anchored on shape, so ordinary prose cannot match.
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{2,5}-\d{1,4}(?:-[A-Za-z0-9]{1,6})?"
    r"|SOP-\d{2,4}(?:-Rev\d+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+){1,3}\s+(?:segment|pipeline|line))\b"
)


def _answer(
    request: str,
    decision,
    memory,
    *,
    session_id: str,
    model_id: str,
    active_documents: list[str] | None,
) -> Iterator[dict]:
    """The turn itself. Split out of run_turn so that memory is opened
    and closed around EVERY path, including the ones that return early."""
    from backend.observability import turn_log as T

    yield {"type": "start", "request": request}
    from backend.orchestrator.model_select import select as select_model

    selection = select_model(request)
    yield {
        "type": "route",
        "path": decision.path,
        "reason": decision.reason,
        "tools_expected": decision.tools_expected,
        # MODEL AUTO-SELECTION, visible. The problem statement's expected
        # demo is "model auto selection across at least two different task
        # types"; the turn now says which model it chose and why.
        "task": selection.task,
        "model_id": selection.model_id,
        "model": selection.model,
        "model_reason": selection.reason,
    }

    if decision.path == "approval":
        # INTERCEPTION ON THIS PATH IS RIGHT. THE PAYLOAD WAS NOT.
        #
        # The streaming endpoint had no action gate at all, so a write
        # request reached the tool loop -- catching that here is a real
        # fix and it stays.
        #
        # What arrived with it was the fabricated approval payload,
        # hardcoded in the backend for EVERY intercepted action:
        #
        #     action_type   DCS_SETPOINT_WRITE
        #     target        HCU-2 / FFC-201
        #     current       100% (1,450 m3/h)
        #     proposed      115% (1,667 m3/h)
        #     risk_level    CRITICAL
        #     warning       "Operating above 110% reduces catalyst
        #                    residence time (LHSV > 1.8 h-1)..."
        #
        # So "Draft an approval note and save it" asked an operator to
        # authorise a feed-rate change on FFC-201. This is the same
        # defect fixed in 879a8ef, and this time it is WORSE: it was
        # removed from ApprovalModal.jsx and moved into the backend, so
        # the frontend now renders invented figures as authoritative
        # backend data. A visible fallback became an invisible claim.
        #
        # An approval screen that describes a different action than the
        # pending one is not a safety control. It is consent obtained
        # under a false description, and it produces a signed audit
        # record for something nobody approved.
        #
        # The action is resolved instead -- same resolver the
        # non-streaming path uses, so the two cannot describe the same
        # request differently.
        from backend.audit.approval_gate import ApprovalGate
        from backend.orchestrator.action_resolver import resolve as resolve_action
        from backend.orchestrator.graph import classify_action_request

        action_kind = classify_action_request(request) or "operator action"
        resolved = resolve_action(request, action_kind, session_id=session_id)
        if resolved.job_id:
            from backend.orchestrator import output_jobs as deck_jobs
            from backend.orchestrator.action_resolver import deck_job_reply

            reply = deck_job_reply(resolved)
            job = deck_jobs.get(resolved.job_id)
            yield {"type": "deck_job", "job": job.public() if job else {"job_id": resolved.job_id}}
            yield {"type": "text_delta", "text": reply}
            yield {"type": "done", "reply": reply, "tool_calls": 0, "iterations": 1,
                   "seconds": 0.05, "awaiting_approval": False, "deck_job_id": resolved.job_id,
                   "citations": []}
            return

        gate = ApprovalGate()
        app_req = gate.request(
            tool_name=resolved.tool_name or "unsupported_action",
            arguments=(
                resolved.arguments
                if resolved.executable
                else {"command": request, "category": action_kind}
            ),
            effect=resolved.effect,
        )

        # Only fields the system actually knows. A field it cannot know
        # is ABSENT, never filled with a plausible placeholder: an empty
        # field reads as unknown, a plausible one reads as measured.
        approval_action = {
            "id": app_req.request_id,
            "title": f"Confirm {action_kind}",
            "action_type": action_kind,
            "description": app_req.effect,
            "detail": request.strip(),
            "executable": resolved.executable,
            "tool_name": resolved.tool_name,
            "preview": resolved.preview,
            "reason": resolved.reason,
        }

        lines = [
            "**Action intercepted — human approval required.**",
            "",
            f"This request was classified as a **{action_kind}**, which hard "
            f"constraint #4 does not permit the system to perform unattended.",
            "",
        ]
        if resolved.executable:
            lines += ["> 🛑 **Approval gate [FR-15 / §3.12]** — nothing has been "
                      "executed yet. Approving carries this out:", ""]
            lines += [f"- {line}" for line in resolved.preview]
        else:
            lines += ["> 🛑 **Approval gate [FR-15 / §3.12]** — nothing has been "
                      "executed, and nothing can be:", "", resolved.reason]
        reply = "\n".join(lines)

        yield {
            "type": "plan",
            "steps": [{
                "step_id": "approval",
                "description": f"Human approval for: {action_kind}",
                "assigned_agent": "reasoning",
                "status": "pending",
                "depends_on": [],
            }],
            "path": "approval",
        }
        yield {
            "type": "approval_required",
            "id": app_req.request_id,
            "name": resolved.tool_name or "unsupported_action",
            "arguments": app_req.arguments,
            "effect": app_req.effect,
            "action": approval_action,
        }
        yield {"type": "text_delta", "text": reply}
        yield {
            "type": "done",
            "reply": reply,
            "tool_calls": 0,
            "iterations": 1,
            "seconds": 0.05,
            "awaiting_approval": True,
            "approval_action": approval_action,
            "citations": [],
        }
        return

    # THE PLAN, EMITTED BEFORE ANY WORK STARTS.
    #
    # The Plan Graph rendered empty on every live turn: this endpoint
    # runs a tool-calling loop and never called the planner, so no plan
    # event was ever sent. POST /api/plan existed and nothing invoked
    # it.
    #
    # The plan is built from the same planner the non-streaming path
    # uses, so the two cannot show different plans for the same request.
    # A failure here degrades to a single-step plan rather than breaking
    # the turn -- the plan is a description of the work, not a
    # prerequisite for it.
    yield from _emit_plan(request, decision)

    # Instant paths: no retrieval, no model, no planner.
    if decision.path in ("greeting", "closing", "capability"):
        from backend.orchestrator.intent import (
            CLOSING_REPLY,
            GREETING_REPLY,
            capability_reply,
        )

        reply = {
            "greeting": GREETING_REPLY,
            "closing": CLOSING_REPLY,
            "capability": capability_reply(),
        }[decision.path]
        yield {"type": "text_delta", "text": reply}
        yield {
            "type": "done",
            "reply": reply,
            "tool_calls": 0,
            "iterations": 1,
            "seconds": 0.0,
            "awaiting_approval": False,
            "citations": [],
        }
        return

    if selection.task == "code_generation" and decision.path in ("agentic", "direct"):
        yield from _run_code(request, selection, session_id=session_id)
        return

    if decision.path == "agentic" or decision.path == "arithmetic":
        # Drop the loop's own `start`; one has already been emitted, and
        # two would make a UI clear its transcript mid-turn.
        for event in run_agent_loop(
            request,
            session_id=session_id,
            model_id=model_id,
            active_documents=active_documents,
            memory=memory,
        ):
            if event.get("type") == "start":
                continue
            yield event
        return

    yield from _run_direct(
        request, decision, active_documents=active_documents, memory=memory
    )


def _run_code(request: str, selection, *, session_id: str) -> Iterator[dict]:
    """A coding task: written by the code model, run in the sandbox, verified.

    The SAME function the graph path uses (code_generation.run_generated_code),
    so the two chat paths cannot disagree about how code is written or what
    counts as verified (review rule 6). Before this, a code request on the
    streaming path was written by the chat model inside the tool loop -- one
    model for everything, which is the thing the problem statement asks us
    not to be.
    """
    import time

    from backend.orchestrator.code_generation import CodeGenerationError, run_generated_code
    from backend.orchestrator.state import PlanStep

    step = PlanStep(step_id="code", description=request, assigned_agent="code")
    yield {"type": "plan", "path": "code", "steps": [{
        "step_id": "code", "description": f"Write the program with {selection.model}, run it in the sandbox",
        "assigned_agent": "code", "status": "running", "depends_on": [],
    }]}
    yield {"type": "tool_call", "id": "code-1", "name": "run_generated_code",
           "arguments": {"task": request, "model": selection.model}}
    started = time.time()
    try:
        event = run_generated_code(step, request, session_id=session_id, model_id=selection.model_id)
    except CodeGenerationError as exc:
        reply = f"**The code model did not return a program.** {exc}"
        yield {"type": "tool_result", "id": "code-1", "status": "failed", "output": {"error": str(exc)},
               "seconds": round(time.time() - started, 1)}
        yield {"type": "text_delta", "text": reply}
        yield {"type": "done", "reply": reply, "tool_calls": 1, "iterations": 1,
               "seconds": round(time.time() - started, 1), "citations": []}
        return
    except Exception as exc:  # noqa: BLE001 - the sandbox being down is said, not hidden
        reply = (f"**The program could not be run:** {type(exc).__name__}: {exc}. The sandbox "
                 "(Docker) must be running for code to execute; nothing was run outside it.")
        yield {"type": "tool_result", "id": "code-1", "status": "failed", "output": {"error": reply},
               "seconds": round(time.time() - started, 1)}
        yield {"type": "text_delta", "text": reply}
        yield {"type": "done", "reply": reply, "tool_calls": 1, "iterations": 1,
               "seconds": round(time.time() - started, 1), "citations": []}
        return

    output = event.output or {}
    code = (event.input_params or {}).get("code", "")
    seconds = round(time.time() - started, 1)
    yield {"type": "tool_result", "id": "code-1", "status": event.status,
           "output": {**output, "code": code, "model": selection.model}, "seconds": seconds}

    verified = event.status == "done"
    lines = [
        f"**{'Verified' if verified else 'Not verified'}** — written by `{selection.model}` "
        f"(chosen for {selection.task.replace('_', ' ')}), run in the offline sandbox.",
        "",
        "```python",
        code.strip(),
        "```",
        "",
        "**Output:**",
        "```",
        (output.get("stdout") or "").strip() or "(no output)",
        "```",
    ]
    if output.get("stderr"):
        lines += ["", "**Errors:**", "```", str(output["stderr"]).strip()[:1500], "```"]
    if output.get("verification"):
        lines += ["", f"_{output['verification']}_"]
    reply = "\n".join(lines)
    yield {"type": "text_delta", "text": reply}
    yield {"type": "done", "reply": reply, "tool_calls": 1, "iterations": 1, "seconds": seconds,
           "citations": [], "model": selection.model, "task": selection.task}


def _emit_plan(request: str, decision) -> Iterator[dict]:
    """The step DAG for this turn, as a `plan` event.

    Shape matches /api/chat's `plan` field exactly, so the Plan Graph
    renders one thing regardless of which endpoint produced it.
    """
    from backend.observability import turn_log as T
    from backend.orchestrator.simple_intent import is_simple_lookup, simple_plan

    # THE PLANNER MUST NOT RUN FOR A TURN THAT NEEDS NO PLAN.
    #
    # This is the 3.5s greeting from HANDOFF.md 3a, measured and now
    # explained. Routing was never the cost -- decide_path and classify
    # really do take 0.0001s. The cost was HERE, three lines above the
    # instant-path check: a greeting is not a simple lookup (no question
    # opener), so it fell through to the LLM planner and spent 10.5s
    # planning work that the next statement was about to skip.
    #
    # It also explains why capability looked FASTER than greeting
    # through the same path, which made no sense at the time: "what can
    # you do" starts with "what", matches the question opener, and got
    # the deterministic plan for free.
    #
    # An instant path still emits a plan -- the Plan Graph should not go
    # blank because the answer was cheap -- but it describes the one
    # thing that actually happens.
    if decision.path in ("greeting", "closing", "capability", "arithmetic"):
        steps = [{
            "step_id": decision.path,
            "description": decision.reason,
            "assigned_agent": "math" if decision.path == "arithmetic" else "reasoning",
            "status": "pending",
            "depends_on": [],
        }]
        T.kv("plan steps", len(steps))
        yield {"type": "plan", "steps": steps, "path": decision.path}
        return

    t_plan_start = time.perf_counter()
    steps = []
    try:
        if decision.path == "corpus":
            steps = [{
                "step_id": "inventory",
                "description": "Read the source index",
                "assigned_agent": "retrieval",
                "status": "pending",
                "depends_on": [],
            }]
        elif is_simple_lookup(request):
            steps = [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "assigned_agent": s.assigned_agent,
                    "status": "pending",
                    "depends_on": list(s.depends_on),
                }
                for s in simple_plan(request)
            ]
        else:
            from backend.orchestrator.planner import plan_request
            from backend.orchestrator.state import AgentState

            planned = plan_request(AgentState(session_id="plan", original_request=request))
            steps = [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "assigned_agent": s.assigned_agent,
                    "status": "pending",
                    "depends_on": list(s.depends_on),
                }
                for s in planned.plan
            ]
    except Exception as exc:  # noqa: BLE001
        # A plan is a description of the work, not a prerequisite for
        # it. Degrade to one honest step rather than failing the turn.
        T.warn(f"planner unavailable ({type(exc).__name__}); single-step plan")
        steps = [{
            "step_id": "answer",
            "description": f"Answer: {request[:110]}",
            "assigned_agent": "reasoning",
            "status": "pending",
            "depends_on": [],
        }]

    t_plan_ms = round((time.perf_counter() - t_plan_start) * 1000, 2)
    T.kv("step: plan_generation (ms)", t_plan_ms)

    T.kv("plan steps", len(steps))
    yield {"type": "plan", "steps": steps, "path": decision.path}


def _run_direct(
    request: str,
    decision,
    active_documents: list[str] | None = None,
    memory=None,
) -> Iterator[dict]:
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
        answer = generate_grounded_answer(
            store,
            request,
            active_documents=active_documents,
            search_query=getattr(memory, "search_query", None),
            conversation_context=getattr(memory, "context_block", "") or "",
        )
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
