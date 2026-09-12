# AGENT_STREAM_PROTOCOL.md — the contract between the agent loop and the UI

**Owners:** Aryan (backend, `backend/orchestrator/agent_loop.py`) ·
Netal (frontend rendering)

This is the wire format for the interleaved "text, work, text, work"
experience — the agent saying what it is about to do, doing it, saying
what it got, and continuing. It is a contract: neither side changes an
event shape without changing this file.

---

## Endpoint

```
POST /api/chat/stream
Content-Type: application/json
{ "message": "...", "session_id": "..." }

-> text/event-stream
   data: {"type": "...", ...}\n\n
```

Standard SSE. Each `data:` line is one complete JSON event. The stream
ends after a `done` or `error` event.

---

## Events

### `start`
```json
{"type": "start", "request": "What is the SOP for catalyst changeout?"}
```
First event, always. Use it to clear any previous state.

### `text_delta`
```json
{"type": "text_delta", "text": " the SOP for"}
```
A fragment of the agent's narration, as the model produces it. Append
in order. These arrive **between** tool calls as well as at the end —
that interleaving is the whole point of this endpoint.

Fragments are token-level, so expect many (a measured turn produced 173
events). Buffer before rendering if that is too many React updates.

### `tool_call`
```json
{"type": "tool_call", "id": "call_287cqkr5",
 "name": "search_documents",
 "arguments": {"query": "SOP hydrocracker catalyst changeout", "top_k": 5}}
```
Emitted **before** the tool runs, so the UI can show it as in-flight.

**Render the arguments. This is a safety feature, not a debug detail.**
Measured: asked for "381.95 minus 400", the model called
`evaluate_expression` with `"-381.95 - 400"` — a spurious leading minus
— and the tool correctly returned `-781.95` for the expression it was
given. Hard constraint #3 guarantees the number came from an executed
tool. It does **not** guarantee the model asked the right question, and
nothing downstream can tell the difference: the wrong answer arrives
with a genuine tool-call receipt attached.

The only thing that catches this is a human seeing `-381.95 - 400` on
screen. Show the arguments.

### `tool_result`
```json
{"type": "tool_result", "id": "call_287cqkr5", "name": "search_documents",
 "output": {"found": true, "passages": [...]},
 "status": "done", "seconds": 0.14}
```
`status` is `done` or `failed`. A `failed` result carries
`output.error` and is fed back to the model, which may retry — so
expect repeated calls to the same tool, and render them as a sequence
rather than replacing the previous one.

`output` is the tool's real return value, converted to JSON without
flattening structure. Collapse it by default; an engineer wants it on
demand, not in their face.

### `approval_required`
```json
{"type": "approval_required", "id": "call_x", "name": "draft_docx",
 "arguments": {...}, "effect": "Draft a DOCX report..."}
```
The loop **stops here**. The tool has not run. Hard constraint #4: no
file write, send, or SAP write without a human gate.

A `done` event with `"awaiting_approval": true` follows immediately.
Show the approval modal; do not render the turn as finished.

### `done`
```json
{"type": "done", "reply": "full narration text", "tool_calls": 3,
 "iterations": 2, "seconds": 48.17, "awaiting_approval": false}
```
`reply` is the concatenation of every `text_delta`. Use it to replace
your accumulated buffer once, rather than trusting your own
concatenation.

### `error`
```json
{"type": "error", "message": "The model call failed: ..."}
```
Render it. A stream that stops without an event is indistinguishable
from a slow one, so a silent truncation leaves the UI spinning forever
— which is why a crash mid-stream is converted into this event.

---

## Rendering guidance

1. **Interleave in arrival order.** Narration, then the call, then the
   result, then more narration. Do not group all tool calls together at
   the end; the order is the explanation.
2. **Show the tool call before the result**, in a pending state. The
   gap between them is where the work happens and is often seconds.
3. **Show arguments always, output on demand.** See `tool_call` above.
4. **A failed tool is not a failed turn.** The agent frequently
   recovers. Style it as an event, not an error state.
5. **Do not invent progress.** No fake percentage, no synthetic steps.
   This codebase shipped a "Retrieving sources · 21s" indicator that
   counted forever with no request behind it; that is the failure mode
   to avoid.

---

## Routing — the backend chooses the path, not the UI

**`POST /api/chat/stream` is the only endpoint the UI needs.** It routes
the request and emits the same event protocol whichever path answers, so
the frontend renders one shape and never decides anything.

The `route` event, second in every stream, says which path ran and why:

```json
{"type": "route", "path": "direct",
 "reason": "Single-intent lookup — one retrieval and a grounded answer...",
 "tools_expected": false}
```

| `path` | When | What happens |
|---|---|---|
| `corpus` | "what documents do you have", "summarise your data" | Answered from the source index. No model, no retrieval, nothing that can be fabricated |
| `direct` | Single-intent lookup — "what is the MFI for H030SG?", "what is the SOP for catalyst changeout?" | One retrieval, one grounded answer with the tuned citation/refusal scaffolding. Emits a `search_documents` tool call so the UI shows the same detail as the agentic path |
| `agentic` | Multi-step, comparison, computation, actions — "project when delta-P crosses the trigger", "compare these and draft a report" | The loop: model chooses tools, runs them, reads results, continues |

Routing is structural (`backend/orchestrator/path_router.py`) — it reuses
`is_simple_lookup`, the same classifier that decides whether to skip the
planner, so the two cannot disagree about the same property. It is not a
model call: that would cost as much as a short answer and add a failure
mode where the router itself is unreachable. **It fails towards
`direct`**, the path with better answer quality and full grounding
scaffolding.

Measured 10/10 on the routing cases.

**Why this matters for your UI:** `direct` and `corpus` answers arrive as
one `text_delta`, not token by token, because those paths are not
streamed. That is deliberate — faking a typewriter over an answer that
already exists is inventing progress, which is the failure mode the
deleted "Retrieving sources · 21s" indicator embodied. Render a single
delta as a complete message; do not wait for more.

### Consider showing the route

The `reason` is written to be shown. A user who sees *"multi-step or
needs computation — the agent will choose tools"* understands why this
answer is taking 40 seconds when the last one took 8. A routing decision
nobody can see is one nobody can question.

### Answer quality, honestly

The agentic loop under-extracts on plain lookups — it retrieves the
right documents and then fails to pull the value out. **Routing largely
removes this in practice**, because lookups now go to `direct`, which is
where the grounding scaffolding lives.

It still applies to genuinely multi-step requests, which have no
alternative path. Closing that gap is Aryan's, tracked in
`docs/STATUS.md`.

## Tool set offered in chat

Curated, not the whole registry — `CHAT_TOOLS` in `agent_loop.py`:

```
search_documents  list_documents  evaluate_expression
evaluate_unit_expression  analyse_trend  project_to_threshold
describe_series  select_images_for_request  extract_printed_text
```

Offering all 19 registered tools to a 7B model was measured producing:
`find_contradictions` called with empty arguments (it returns `[]`,
which reads as "nothing found"); `lookup_thermophysical_property`
called five times with wrong arguments, drifting into the density of
methane; and `search_documents` emitted as literal text instead of as a
call. Selection accuracy falls off with option count, and a loop
compounds it — a wrong first choice becomes the context for every
choice after it.

Excluded tools are **not disabled**. They remain registered, tested,
and callable through `POST /api/tools/call`. They are simply not
offered as a free choice mid-conversation.
